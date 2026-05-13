"""Regression tests for OSC Sync engine bug-fix pass (2026-05-12).

Covers two bugs reported in Projects/steam-deck-midi/TODO.md P5:

1. **Pre-drop ordering.** The wiggle/sync pass must drop comp master
   opacity to 0 BEFORE any wiggle write (and before the sync-indicator
   force-transition dance), hold it at 0 across the whole pass, and
   restore it in a try/finally so the screen returns even if a wiggle
   step raises.
2. **Audio-engine bypass toggle.** Wiggling the audio engine's
   `engineenable` bool flip-flopped the engine on/off — visible as a
   perceptible drop-out even with master masked, because the
   audio_opacity bridge engine listens for the resulting CC and resets
   its state machine. Fix: exclude `engineenable` (and the wrapper
   `bypassed` path) from the wiggle iteration by default.

Mirrors the fakes + helpers from tests/test_engines.py so the asserts
match the existing patterns operators rely on.
"""

from __future__ import annotations

import threading
import unittest
from typing import Any

from windows.engines.osc_preset import (
    KIND_BOOL,
    KIND_FLOAT,
    SyncTarget,
)
from windows.engines.osc_sync import (
    DEFAULT_ENGINE_ENABLE_EXCLUDES,
    OscSyncEngine,
)
from windows.engines.resolume_rest import ResolumeRestError
from windows.midi import DryRunMidiOut


# ---------------------------------------------------------------------------
# Fakes mirrored from tests/test_engines.py — copy rather than import so the
# new test module isn't coupled to the old one's internals.


class RecordingMidiOut(DryRunMidiOut):
    def __init__(self) -> None:
        super().__init__(selected_port_name="recording")
        self.events: list[tuple[str, int, int, int]] = []

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.events.append(("cc", channel, control, value))

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.events.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.events.append(("note_off", channel, note, velocity))


class FakeRestClient:
    def __init__(self, composition: dict | None = None, *, fail_get: bool = False) -> None:
        self._composition = composition or {}
        self._fail_get = fail_get
        self.put_calls: list[tuple[int, Any]] = []
        self.get_composition_calls = 0

    def get_composition(self) -> dict:
        self.get_composition_calls += 1
        if self._fail_get:
            raise ResolumeRestError("simulated GET failure")
        return self._composition

    def get_parameter(self, param_id: int) -> dict:
        return {"id": param_id, "value": 0.0}

    def put_parameter(self, param_id: int, value) -> None:
        self.put_calls.append((param_id, value))


class FakeOscClient:
    """Records every OSC send so tests can assert on the message order."""

    def __init__(self) -> None:
        self.sends: list[tuple[str, Any]] = []
        self._closed = False
        self._error_on: set[str] = set()

    def fail_on(self, path: str) -> None:
        """Make a future `send(path, ...)` raise — used to test try/finally."""
        self._error_on.add(path)

    def send(self, address: str, value) -> None:
        self.sends.append((address, value))
        if address in self._error_on:
            raise RuntimeError(f"simulated OSC send failure for {address}")

    def close(self) -> None:
        self._closed = True


def _osc_sync_config(**overrides) -> dict:
    cfg = {
        "name": "OSC Sync",
        "type": "osc_sync",
        "enabled": True,
        "epsilon_float": 0.001,
        "inter_message_delay_ms": 0,  # zero-delay for fast tests
        "mask_with_master": True,
        "inputs": {"channel": 14, "cc_sync": 90},
        "rest": {"base_url": "http://127.0.0.1:8080", "timeout_seconds": 1.5},
        "osc": {"host": "127.0.0.1", "port": 7000},
    }
    cfg.update(overrides)
    return cfg


def _build_osc_sync(
    *,
    targets: list[SyncTarget] | None = None,
    composition: dict | None = None,
    fail_get: bool = False,
    config_overrides: dict | None = None,
    osc_client: FakeOscClient | None = None,
    sleep=lambda _t: None,
):
    midi = RecordingMidiOut()
    rest = FakeRestClient(composition=composition, fail_get=fail_get)
    osc = osc_client or FakeOscClient()
    cfg = _osc_sync_config(**(config_overrides or {}))
    engine = OscSyncEngine(
        name="OSC Sync",
        config=cfg,
        midi_out=midi,
        rest_client=rest,
        osc_client=osc,
        sleep=sleep,
    )
    if targets is not None:
        engine._targets = targets  # bypass XML parse
    return engine, rest, osc, midi


def _wait_for_pass(engine: OscSyncEngine, timeout: float = 2.0) -> None:
    worker = engine._worker
    if worker is not None:
        worker.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Bug 1: comp master must drop FIRST, hold, and always restore in try/finally.


class CompMasterMaskOrderTests(unittest.TestCase):
    """Verifies the bug 1 fix: master at 0 before any other visible-impact
    write, restored in a finally block."""

    def test_master_dropped_before_indicator_dance_and_wiggle(self) -> None:
        """The first three OSC sends, in order, must be:
        1. /composition/master -> 0.0  (mask drop)
        2. /composition/video/effects/oscsync/effect/sync/sync -> 0.0  (dance start)
        3. ...   -> 1.0  (dance latch high)
        ... only then can wiggle writes go out.
        """
        composition = {
            "master": {"id": 1, "value": 0.8, "valuerange": {"min": 0, "max": 1}},
            "layers": [{"master": {"id": 99, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        targets = [
            SyncTarget(
                osc_path="/composition/layers/1/master",
                kind=KIND_FLOAT,
                param_node_name="ParamRange",
            )
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        # First three sends in order
        first_three = osc.sends[:3]
        self.assertEqual(
            first_three,
            [
                ("/composition/master", 0.0),
                ("/composition/video/effects/oscsync/effect/sync/sync", 0.0),
                ("/composition/video/effects/oscsync/effect/sync/sync", 1.0),
            ],
        )
        # And only AFTER all three does the wiggle write land
        first_layer_send_index = next(
            i for i, (path, _) in enumerate(osc.sends)
            if path == "/composition/layers/1/master"
        )
        self.assertGreater(first_layer_send_index, 2)

    def test_master_at_zero_throughout_wiggle_iteration(self) -> None:
        """Comp master must not be re-written to non-zero between the
        initial mask and the final restore."""
        composition = {
            "master": {"id": 1, "value": 0.8, "valuerange": {"min": 0, "max": 1}},
            "layers": [
                {"master": {"id": 11, "value": 0.5, "valuerange": {"min": 0, "max": 1}}},
                {"master": {"id": 22, "value": 0.5, "valuerange": {"min": 0, "max": 1}}},
                {"master": {"id": 33, "value": 0.5, "valuerange": {"min": 0, "max": 1}}},
            ],
        }
        targets = [
            SyncTarget(osc_path=f"/composition/layers/{i}/master", kind=KIND_FLOAT, param_node_name="ParamRange")
            for i in (1, 2, 3)
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        master_sends = [v for path, v in osc.sends if path == "/composition/master"]
        # Exactly two writes: drop at start, restore at end. No mid-pass writes.
        self.assertEqual(master_sends, [0.0, 0.8])

    def test_master_restored_when_wiggle_raises(self) -> None:
        """If a wiggle write raises mid-loop, the finally clause must
        still restore master so the operator's screen comes back."""
        composition = {
            "master": {"id": 1, "value": 0.6, "valuerange": {"min": 0, "max": 1}},
            "layers": [
                {"master": {"id": 11, "value": 0.5, "valuerange": {"min": 0, "max": 1}}},
                {"master": {"id": 22, "value": 0.5, "valuerange": {"min": 0, "max": 1}}},
            ],
        }
        targets = [
            SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange"),
            SyncTarget(osc_path="/composition/layers/2/master", kind=KIND_FLOAT, param_node_name="ParamRange"),
        ]
        osc = FakeOscClient()
        # Sabotage the second layer's wiggle so it raises mid-pass
        osc.fail_on("/composition/layers/2/master")
        engine, _rest, _osc, _midi = _build_osc_sync(
            targets=targets, composition=composition, osc_client=osc,
        )
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        master_sends = [v for path, v in osc.sends if path == "/composition/master"]
        # Restore must still happen even though /layers/2/master raised
        self.assertEqual(master_sends, [0.0, 0.6])
        # And the sync indicator release also runs (operator's button un-highlights)
        indicator_sends = [
            v for path, v in osc.sends
            if path == "/composition/video/effects/oscsync/effect/sync/sync"
        ]
        # 0.0 (dance start), 1.0 (dance latch), 0.0 (release)
        self.assertEqual(indicator_sends, [0.0, 1.0, 0.0])

    def test_master_restored_when_no_targets(self) -> None:
        """If all targets are excluded, mask should NOT happen — no point
        masking when nothing will be wiggled. But indicator dance still
        runs (UX feedback) and there must be no orphaned master writes."""
        composition = {"master": {"id": 1, "value": 0.9, "valuerange": {"min": 0, "max": 1}}}
        # Only the indicator path — excluded by default
        targets = [
            SyncTarget(
                osc_path="/composition/video/effects/oscsync/effect/sync/sync",
                kind=KIND_BOOL,
                param_node_name="RangedParam[bool]",
            )
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        master_sends = [v for path, v in osc.sends if path == "/composition/master"]
        # No mask, no restore — pass was a no-op for the comp master.
        self.assertEqual(master_sends, [])

    def test_mask_with_master_disabled_still_wiggles(self) -> None:
        """When `mask_with_master=False`, the pass skips the mask
        entirely but still wiggles targets."""
        composition = {
            "master": {"id": 1, "value": 0.7, "valuerange": {"min": 0, "max": 1}},
            "layers": [{"master": {"id": 99, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        targets = [
            SyncTarget(
                osc_path="/composition/layers/1/master",
                kind=KIND_FLOAT,
                param_node_name="ParamRange",
            )
        ]
        engine, _rest, osc, _midi = _build_osc_sync(
            targets=targets,
            composition=composition,
            config_overrides={"mask_with_master": False},
        )
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        master_sends = [v for path, v in osc.sends if path == "/composition/master"]
        self.assertEqual(master_sends, [])
        # And the layer master wiggle did happen
        layer_sends = [v for path, v in osc.sends if path == "/composition/layers/1/master"]
        self.assertEqual(len(layer_sends), 2)  # nudge + restore


# ---------------------------------------------------------------------------
# Bug 2: audio engine on/off bypass paths must NOT be wiggled.


class EngineEnableExclusionTests(unittest.TestCase):
    """Verifies the bug 2 fix: bool-wiggle on the audio engine's
    `engineenable` (and the wrapper `bypassed` path) is skipped by
    default, so the wiggle pass never visibly toggles the audio engine
    on/off mid-show."""

    def test_default_excludes_contain_audio_engine_enable(self) -> None:
        """Belt-and-suspenders: the module-level default list contains
        the known audio-engine on/off paths."""
        self.assertIn(
            "/composition/video/effects/audioengine/effect/engine/engineenable",
            DEFAULT_ENGINE_ENABLE_EXCLUDES,
        )
        self.assertIn(
            "/composition/video/effects/audioengine/bypassed",
            DEFAULT_ENGINE_ENABLE_EXCLUDES,
        )

    def test_engineenable_not_wiggled_by_default(self) -> None:
        """`engineenable` is in the default exclude list — the wiggle
        pass MUST NOT send any OSC write to that path."""
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "video": {
                "effects": [
                    {
                        "name": {"value": "AudioEngine"},
                        "params": {
                            # The wire dashboard input the bridge listens for.
                            "ENGINE ENABLE": {"id": 100, "value": True},
                        },
                    }
                ]
            },
        }
        engine_enable_path = (
            "/composition/video/effects/audioengine/effect/engine/engineenable"
        )
        targets = [
            SyncTarget(
                osc_path=engine_enable_path,
                kind=KIND_BOOL,
                param_node_name="RangedParam[bool]",
            )
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        # No OSC writes to the engineenable path — neither flip-to-False
        # nor flip-back-to-True.
        engine_enable_sends = [v for path, v in osc.sends if path == engine_enable_path]
        self.assertEqual(engine_enable_sends, [])
        # And the pass logged it as skipped, not wiggled.
        self.assertEqual(engine._last_pass_wiggle_count, 0)

    def test_audioengine_bypassed_wrapper_path_also_excluded(self) -> None:
        """The wrapper `/composition/video/effects/audioengine/bypassed`
        path is excluded too (belt-and-suspenders — Resolume already
        usually filters it via allowedTranslationTypes=-1, but if it
        ever appears in the target list we still skip it)."""
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "video": {
                "effects": [
                    {
                        "name": {"value": "AudioEngine"},
                        "bypassed": {"id": 200, "value": False},
                    }
                ]
            },
        }
        bypassed_path = "/composition/video/effects/audioengine/bypassed"
        targets = [
            SyncTarget(
                osc_path=bypassed_path,
                kind=KIND_BOOL,
                param_node_name="RangedParam[bool]",
            )
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        bypassed_sends = [v for path, v in osc.sends if path == bypassed_path]
        self.assertEqual(bypassed_sends, [])
        self.assertEqual(engine._last_pass_wiggle_count, 0)

    def test_other_audio_engine_bools_still_wiggled(self) -> None:
        """Non-on/off bool toggles on the audio engine (VIDEO ALWAYS,
        LOGO ALWAYS) are behaviour overrides, not bypass — they MUST
        still be wiggled so TouchOSC stays in sync."""
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "video": {
                "effects": [
                    {
                        "name": {"value": "AudioEngine"},
                        "params": {
                            "VIDEO ALWAYS": {"id": 100, "value": True},
                            "LOGO ALWAYS": {"id": 101, "value": False},
                        },
                    }
                ]
            },
        }
        video_always_path = "/composition/video/effects/audioengine/effect/engine/videoalways"
        logo_always_path = "/composition/video/effects/audioengine/effect/engine/logoalways"
        targets = [
            SyncTarget(osc_path=video_always_path, kind=KIND_BOOL, param_node_name="RangedParam[bool]"),
            SyncTarget(osc_path=logo_always_path, kind=KIND_BOOL, param_node_name="RangedParam[bool]"),
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        # Both bools should have wiggled (flip + restore)
        va_sends = [v for path, v in osc.sends if path == video_always_path]
        la_sends = [v for path, v in osc.sends if path == logo_always_path]
        self.assertEqual(va_sends, [False, True])  # flip from True, back
        self.assertEqual(la_sends, [True, False])  # flip from False, back
        self.assertEqual(engine._last_pass_wiggle_count, 2)

    def test_engine_enable_excludes_configurable(self) -> None:
        """Operator can override the default list via the config field.
        Empty list = no exclusions (engineenable will be wiggled again);
        custom list = only those paths skipped."""
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "video": {
                "effects": [
                    {
                        "name": {"value": "AudioEngine"},
                        "params": {
                            "ENGINE ENABLE": {"id": 100, "value": True},
                        },
                    }
                ]
            },
        }
        engine_enable_path = "/composition/video/effects/audioengine/effect/engine/engineenable"
        targets = [
            SyncTarget(osc_path=engine_enable_path, kind=KIND_BOOL, param_node_name="RangedParam[bool]"),
        ]
        # Empty exclude list -> engineenable is no longer excluded.
        engine, _rest, osc, _midi = _build_osc_sync(
            targets=targets,
            composition=composition,
            config_overrides={"engine_enable_excludes": []},
        )
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        engine_enable_sends = [v for path, v in osc.sends if path == engine_enable_path]
        self.assertEqual(engine_enable_sends, [False, True])  # flip + restore
        self.assertEqual(engine._last_pass_wiggle_count, 1)

    def test_engine_enable_excludes_custom_list(self) -> None:
        """A non-default custom list excludes ONLY the paths given —
        the default audio-engine paths are no longer auto-excluded."""
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "video": {
                "effects": [
                    {
                        "name": {"value": "AudioEngine"},
                        "params": {"ENGINE ENABLE": {"id": 100, "value": True}},
                    },
                    {
                        "name": {"value": "MyCustomFx"},
                        "params": {"FX ENABLE": {"id": 200, "value": True}},
                    },
                ]
            },
        }
        engine_enable_path = "/composition/video/effects/audioengine/effect/engine/engineenable"
        my_fx_path = "/composition/video/effects/mycustomfx/effect/fx/fxenable"
        targets = [
            SyncTarget(osc_path=engine_enable_path, kind=KIND_BOOL, param_node_name="RangedParam[bool]"),
            SyncTarget(osc_path=my_fx_path, kind=KIND_BOOL, param_node_name="RangedParam[bool]"),
        ]
        engine, _rest, osc, _midi = _build_osc_sync(
            targets=targets,
            composition=composition,
            config_overrides={"engine_enable_excludes": [my_fx_path]},
        )
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        # engineenable IS wiggled (no longer in the override list)
        engine_enable_sends = [v for path, v in osc.sends if path == engine_enable_path]
        self.assertEqual(engine_enable_sends, [False, True])
        # my_fx_path is the custom exclude — NOT wiggled
        my_fx_sends = [v for path, v in osc.sends if path == my_fx_path]
        self.assertEqual(my_fx_sends, [])


if __name__ == "__main__":
    unittest.main()
