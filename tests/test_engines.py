"""Tests for v0.3.x+ engines (audio_opacity, osc_sync)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from collections import deque
from pathlib import Path
from typing import Any, Iterable

from windows.engines.audio_opacity import AudioOpacityEngine
from windows.engines.osc_preset import (
    KIND_BOOL,
    KIND_FLOAT,
    KIND_INT,
    SyncTarget,
    parse_osc_preset,
)
from windows.engines.osc_sync import OscSyncEngine
from windows.engines.registry import EngineRegistry
from windows.engines.resolume_rest import ResolumeRestError
from windows.midi import DryRunMidiOut


class RecordingMidiOut(DryRunMidiOut):
    def __init__(self) -> None:
        super().__init__(selected_port_name="recording")
        self.events: list[tuple[str, int, int, int]] = []

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.events.append(("cc", channel, control, value))

    def cc_events(self) -> list[tuple[int, int, int]]:
        return [(c, ctl, v) for kind, c, ctl, v in self.events if kind == "cc"]


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


def _audio_engine(clock: FakeClock | None = None, **overrides) -> AudioOpacityEngine:
    config = {
        "name": "test",
        "type": "audio_opacity",
        "sample_size": 4,
        "update_hz": 30,
        "inputs": {
            "channel": 14,
            "cc_audio": 100,
            "cc_enable": 101,
            "cc_video_stomp": 102,
            "cc_logo_stomp": 103,
            "cc_tipping": 104,
            "cc_duration": 105,
            "cc_attack": 106,
            "cc_release": 107,
            "cc_video_delay": 108,
            "cc_logo_delay": 109,
        },
        "outputs": {"protocol": "midi", "channel": 14, "cc_video_master": 110, "cc_logo_master": 111},
        "defaults": {
            "tipping_point": 0.5,
            "duration_seconds": 0.5,
            "attack_seconds": 0.0,
            "release_seconds": 0.0,
            "video_delay_seconds": 0.0,
            "logo_delay_seconds": 0.0,
        },
    }
    config.update(overrides)
    midi_out = RecordingMidiOut()
    clock = clock or FakeClock()
    engine = AudioOpacityEngine("test", config, midi_out, clock=clock)
    engine.midi_out = midi_out  # type: ignore[attr-defined]
    return engine


class AudioOpacityEngineTests(unittest.TestCase):
    def test_initial_send_pushes_full_on(self) -> None:
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)
        events = engine.midi_out.cc_events()  # type: ignore[attr-defined]
        self.assertIn((14, 110, 127), events)
        self.assertIn((14, 111, 127), events)

    def test_engine_disabled_drives_both_to_full(self) -> None:
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        # First tick = initial send (127/127)
        engine.tick(clock.now)
        clock.advance(0.1)
        # Engine off → expects masters at 127/127 (no change)
        engine.tick(clock.now)
        events = engine.midi_out.cc_events()  # type: ignore[attr-defined]
        # No new messages should be emitted (already at 127/127)
        # Only initial-send messages should be present
        self.assertEqual(len([e for e in events if e[1] == 110]), 1)
        self.assertEqual(len([e for e in events if e[1] == 111]), 1)

    def test_audio_above_threshold_drives_video_on_logo_off(self) -> None:
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)  # initial 127/127
        # Enable engine
        engine.on_midi_in(14, 101, 127, clock.now)
        # Push audio above threshold
        for _ in range(4):
            engine.on_midi_in(14, 100, 100, clock.now)  # 100/127 = 0.79 > 0.5
        clock.advance(0.1)
        engine.tick(clock.now)
        events = engine.midi_out.cc_events()  # type: ignore[attr-defined]
        # Last video should be 127, last logo should be 0
        last_video = [v for ch, ctl, v in events if ctl == 110][-1]
        last_logo = [v for ch, ctl, v in events if ctl == 111][-1]
        self.assertEqual(last_video, 127)
        self.assertEqual(last_logo, 0)

    def test_audio_below_threshold_after_duration_swaps(self) -> None:
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        # Above threshold
        for _ in range(4):
            engine.on_midi_in(14, 100, 100, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        # Now drop below
        for _ in range(4):
            engine.on_midi_in(14, 100, 0, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        # Within debounce — should still be video=on, logo=off
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        self.assertEqual(last_logo, 0)
        # Advance past debounce (0.5 sec)
        clock.advance(0.6)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 0)
        self.assertEqual(last_logo, 127)

    def test_both_stomps_held_blacks_out(self) -> None:
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)
        engine.on_midi_in(14, 102, 127, clock.now)  # video stomp held
        engine.on_midi_in(14, 103, 127, clock.now)  # logo stomp held
        clock.advance(0.1)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 0)
        self.assertEqual(last_logo, 0)

    def test_video_stomp_drives_engine_to_video(self) -> None:
        """VIDEO STOMP held does two things: (1) output mask kills the logo
        channel for the duration of the press; (2) audio override = 1 drives
        the natural state machine to VIDEO so the engine settles on VIDEO
        even though real audio is silent. Mirrors the v0.2.0 wire patch
        where VIDEO STOMP literally pinned the audio signal to 1."""
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        # No audio → natural settles on LOGO (0, 1) with release=0.
        clock.advance(0.1)
        engine.tick(clock.now)
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_logo, 127)
        # VIDEO STOMP press: avg override = 1 instantly above tipping →
        # natural-VIDEO transition runs (with attack=0 so it's instant).
        # Mask zeroes logo while held.
        engine.on_midi_in(14, 102, 127, clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        self.assertEqual(last_logo, 0)
        # Release: real audio still empty, override gone. Engine holds the
        # last natural goal (VIDEO) — logo stays at 0 because nothing drove
        # it back to 1. Wire-patch behavior.
        engine.on_midi_in(14, 102, 0, clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        self.assertEqual(last_logo, 0)

    def test_logo_stomp_drives_engine_to_logo_via_debounce(self) -> None:
        """LOGO STOMP held with loud audio: avg override = 0 starts the
        natural debounce, then transitions to LOGO via release + LOGO_DELAY +
        release pacing — exactly what the wire patch did when it pinned
        audio to 0."""
        clock = FakeClock()
        engine = _audio_engine(clock=clock, defaults={
            "tipping_point": 0.5,
            "duration_seconds": 0.5,
            "attack_seconds": 0.0,
            "release_seconds": 0.0,
            "video_delay_seconds": 0.0,
            "logo_delay_seconds": 0.0,
        })
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        # Drive audio loud → settle on VIDEO.
        for _ in range(4):
            engine.on_midi_in(14, 100, 100, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        # LOGO STOMP press → mask kills video; audio override = 0 starts the
        # debounce. Below the duration window, engine still holds VIDEO.
        engine.on_midi_in(14, 103, 127, clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 0)
        # Past the debounce, engine commits to LOGO. With delays/release at 0
        # the natural-LOGO sequence completes immediately, leaving
        # current_video=0, current_logo=1.
        clock.advance(0.6)
        engine.tick(clock.now)
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_logo, 127)
        # Release the stomp: real audio still loud, but the engine already
        # settled on LOGO during the press. Real audio takes back over →
        # back to VIDEO via natural sequence (instant with attack=0).
        engine.on_midi_in(14, 103, 0, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)

    def test_logo_stomp_skips_video_falls_phase(self) -> None:
        """Natural-LOGO sequence built while LOGO STOMP is held drops the
        first ramp ('video falls via release') because the mask is already
        zeroing video. Sequence becomes LOGO_DELAY + RELEASE instead of
        RELEASE + LOGO_DELAY + RELEASE."""
        clock = FakeClock()
        engine = _audio_engine(clock=clock, defaults={
            "tipping_point": 0.5,
            "duration_seconds": 0.2,
            "attack_seconds": 0.0,
            "release_seconds": 0.5,   # non-zero so the skip is observable
            "video_delay_seconds": 0.0,
            "logo_delay_seconds": 0.5,
        })
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        # Drive audio loud → settle on VIDEO. current_video=1, current_logo=0.
        for _ in range(4):
            engine.on_midi_in(14, 100, 100, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        # Press LOGO STOMP. Audio override=0; below_since starts.
        engine.on_midi_in(14, 103, 127, clock.now)
        # Past duration debounce, sequence is built. With LOGO STOMP held,
        # phase 1 (video falls) is skipped — just DELAY (LOGO_DELAY=0.5) and
        # RAMP logo to 1 (RELEASE=0.5). Total 1.0s.
        clock.advance(0.3)  # past 0.2s debounce
        engine.tick(clock.now)
        # We're now in the DELAY phase. After 0.5s of delay, RAMP starts.
        clock.advance(0.5)
        engine.tick(clock.now)
        # Halfway through the ramp (0.25 / 0.5).
        clock.advance(0.25)
        engine.tick(clock.now)
        # Logo should be ~halfway up. Check it's strictly between 0 and 127.
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertGreater(last_logo, 32)
        self.assertLess(last_logo, 96)
        # Past the ramp, logo should be at full.
        clock.advance(0.3)
        engine.tick(clock.now)
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_logo, 127)

    def test_logo_always_overrides_natural_video_logo_endpoint(self) -> None:
        """LOGO ALWAYS on with audio loud: natural goal is VIDEO, but the
        sequence's logo target shifts from 0 to 1 so logo stays at full."""
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        engine.on_midi_in(14, 113, 127, clock.now)  # logo_always on
        # Drive audio loud.
        for _ in range(4):
            engine.on_midi_in(14, 100, 100, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        self.assertEqual(last_logo, 127)

    def test_video_always_overrides_natural_logo_video_endpoint(self) -> None:
        """VIDEO ALWAYS on with audio quiet: natural goal is LOGO, but the
        sequence's video target shifts from 0 to 1 so video stays at full."""
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        engine.on_midi_in(14, 112, 127, clock.now)  # video_always on
        # No audio → natural goal LOGO. With v_always, video target becomes 1.
        clock.advance(0.1)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        self.assertEqual(last_logo, 127)

    def test_logo_stomp_during_debounce_releases_to_video(self) -> None:
        """Audio drops below tipping (debounce running). Operator stomps logo,
        releases while debounce still ticking. Video must come back instead of
        getting stuck on logo. Regression test for the bug Ben reported on
        2026-05-06."""
        clock = FakeClock()
        engine = _audio_engine(clock=clock, defaults={
            "tipping_point": 0.5,
            "duration_seconds": 1.0,
            "attack_seconds": 0.0,
            "release_seconds": 0.0,
            "video_delay_seconds": 0.0,
            "logo_delay_seconds": 0.0,
        })
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        # Drive audio loud → settle on VIDEO.
        for _ in range(4):
            engine.on_midi_in(14, 100, 100, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        # Audio drops → debounce starts, hold VIDEO.
        for _ in range(4):
            engine.on_midi_in(14, 100, 30, clock.now)
        clock.advance(0.3)
        engine.tick(clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)
        # LOGO STOMP press → mask kills video.
        engine.on_midi_in(14, 103, 127, clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 0)
        # Release while still in debounce window. Video should recover because
        # the natural state machine has been holding VIDEO the whole time.
        engine.on_midi_in(14, 103, 0, clock.now)
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)

    def test_filters_other_channels(self) -> None:
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        # Wrong channel should not enable
        engine.on_midi_in(0, 101, 127, clock.now)
        clock.advance(0.1)
        engine.tick(clock.now)
        # Engine still disabled, masters still at 127/127
        last_video = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 110][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_video, 127)

    def test_tunables_update_via_cc(self) -> None:
        clock = FakeClock()
        engine = _audio_engine(clock=clock, **{"defaults": {"tipping_point": 0.5}})
        engine.on_midi_in(14, 104, 38, clock.now)  # tipping = 38/127 ≈ 0.299
        engine.on_midi_in(14, 105, 64, clock.now)  # duration = 64/127 * 5 = ~2.52s
        engine.on_midi_in(14, 106, 64, clock.now)  # attack = 64/127 * 5 = ~2.52s
        engine.on_midi_in(14, 107, 25, clock.now)  # release = 25/127 * 5 = ~0.98s
        engine.on_midi_in(14, 108, 0, clock.now)   # video_delay = 0
        engine.on_midi_in(14, 109, 50, clock.now)  # logo_delay = 50/127 * 5 = ~1.97s
        status = engine.status()
        self.assertAlmostEqual(status["tipping_point"], 0.299, places=2)
        self.assertAlmostEqual(status["duration_seconds"], 2.52, places=1)
        self.assertAlmostEqual(status["attack_seconds"], 2.52, places=1)
        self.assertAlmostEqual(status["release_seconds"], 0.98, places=1)
        self.assertAlmostEqual(status["video_delay_seconds"], 0.0, places=2)
        self.assertAlmostEqual(status["logo_delay_seconds"], 1.97, places=1)


class EngineRegistryTests(unittest.TestCase):
    def test_dispatches_midi_to_all_engines(self) -> None:
        clock = FakeClock()
        e1 = _audio_engine(clock=clock)
        e2 = _audio_engine(clock=clock)
        registry = EngineRegistry([e1, e2])
        registry.on_midi_in(14, 101, 127, clock.now)
        self.assertTrue(e1._enabled)  # type: ignore[attr-defined]
        self.assertTrue(e2._enabled)  # type: ignore[attr-defined]

    def test_shortest_tick_interval(self) -> None:
        clock = FakeClock()
        e1 = _audio_engine(clock=clock, update_hz=10)
        e2 = _audio_engine(clock=clock, update_hz=30)
        registry = EngineRegistry([e1, e2])
        self.assertAlmostEqual(registry.shortest_tick_interval(), 1 / 30, places=4)


class LoadEnginesFactoryMergeTests(unittest.TestCase):
    """Verify load_engines auto-merges factory defaults for missing engine types."""

    def _audio_stanza(self, **overrides) -> dict:
        cfg = {
            "name": "Audio Engine",
            "type": "audio_opacity",
            "enabled": True,
            "inputs": {"channel": 14},
            "outputs": {"protocol": "midi", "channel": 14, "cc_video_master": 110, "cc_logo_master": 111},
            "defaults": {"tipping_point": 0.5},
        }
        cfg.update(overrides)
        return cfg

    def _osc_sync_stanza(self, **overrides) -> dict:
        cfg = {
            "name": "OSC Sync",
            "type": "osc_sync",
            "enabled": True,
            "inputs": {"channel": 14, "cc_sync": 90},
        }
        cfg.update(overrides)
        return cfg

    def test_factory_engine_merged_when_missing_from_user_config(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user = cfg_dir / "engines.json"
            factory = cfg_dir / "engines.factory.json"
            user.write_text(json.dumps({"engines": [self._audio_stanza()]}), encoding="utf-8")
            factory.write_text(
                json.dumps({"engines": [self._audio_stanza(), self._osc_sync_stanza()]}),
                encoding="utf-8",
            )
            midi = RecordingMidiOut()
            registry = load_engines(user, midi)
            types = {e.type_name for e in registry.engines}
            self.assertEqual(types, {"audio_opacity", "osc_sync"})

    def test_user_customization_preserved_for_existing_type(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user = cfg_dir / "engines.json"
            factory = cfg_dir / "engines.factory.json"
            # User has customized audio engine name
            user.write_text(
                json.dumps({"engines": [self._audio_stanza(name="Custom Audio")]}),
                encoding="utf-8",
            )
            factory.write_text(
                json.dumps({"engines": [self._audio_stanza(name="Audio Engine")]}),
                encoding="utf-8",
            )
            midi = RecordingMidiOut()
            registry = load_engines(user, midi)
            self.assertEqual(len(registry.engines), 1)
            # User's name wins, factory does NOT overwrite
            self.assertEqual(registry.engines[0].name, "Custom Audio")

    def test_user_disabled_factory_engine_stays_disabled(self) -> None:
        # If user has explicitly disabled an engine, the factory merge should
        # NOT re-add it (the user's stanza is present, we just respect enabled=false).
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user = cfg_dir / "engines.json"
            factory = cfg_dir / "engines.factory.json"
            user.write_text(
                json.dumps(
                    {"engines": [self._audio_stanza(), self._osc_sync_stanza(enabled=False)]}
                ),
                encoding="utf-8",
            )
            factory.write_text(
                json.dumps({"engines": [self._audio_stanza(), self._osc_sync_stanza()]}),
                encoding="utf-8",
            )
            midi = RecordingMidiOut()
            registry = load_engines(user, midi)
            types = {e.type_name for e in registry.engines}
            self.assertEqual(types, {"audio_opacity"})  # osc_sync respected as disabled

    def test_no_factory_file_works(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user = cfg_dir / "engines.json"
            user.write_text(json.dumps({"engines": [self._audio_stanza()]}), encoding="utf-8")
            midi = RecordingMidiOut()
            registry = load_engines(user, midi)
            self.assertEqual(len(registry.engines), 1)


# ---------------------------------------------------------------------------
# OSC sync engine tests


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
    def __init__(self) -> None:
        self.sends: list[tuple[str, Any]] = []
        self._closed = False

    def send(self, address: str, value) -> None:
        self.sends.append((address, value))

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
):
    midi = RecordingMidiOut()
    rest = FakeRestClient(composition=composition, fail_get=fail_get)
    osc = FakeOscClient()
    cfg = _osc_sync_config(**(config_overrides or {}))
    engine = OscSyncEngine(
        name="OSC Sync",
        config=cfg,
        midi_out=midi,
        rest_client=rest,
        osc_client=osc,
        sleep=lambda _t: None,
    )
    if targets is not None:
        engine._targets = targets  # bypass XML parse
    return engine, rest, osc, midi


def _wait_for_pass(engine: OscSyncEngine, timeout: float = 2.0) -> None:
    worker = engine._worker
    if worker is not None:
        worker.join(timeout=timeout)
    deadline = threading.Event()
    # Belt and suspenders — ensure status flag is set
    if engine._last_pass_completed_at is None:
        deadline.wait(0.05)


class OscSyncEngineTests(unittest.TestCase):
    def test_rising_edge_fires_pass_non_rising_does_not(self) -> None:
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
        }
        # One dummy target so the pass actually exercises REST (not the
        # "no targets" early-return).
        targets = [SyncTarget(osc_path="/composition/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, rest, osc, _midi = _build_osc_sync(
            targets=targets,
            composition=composition,
        )

        # Wrong CC → ignored
        engine.on_midi_in(channel=14, cc=99, value=127, now=0.0)
        self.assertIsNone(engine._worker)

        # Wrong channel → ignored
        engine.on_midi_in(channel=0, cc=90, value=127, now=0.0)
        self.assertIsNone(engine._worker)

        # Rising edge: 0 → 127
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        self.assertEqual(rest.get_composition_calls, 1)

        # Hold-on (127 → 127) does not retrigger
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.1)
        _wait_for_pass(engine)
        self.assertEqual(rest.get_composition_calls, 1)

        # Falling edge does not trigger; subsequent rising does
        engine.on_midi_in(channel=14, cc=90, value=0, now=0.2)
        _wait_for_pass(engine)
        self.assertEqual(rest.get_composition_calls, 1)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.3)
        _wait_for_pass(engine)
        self.assertEqual(rest.get_composition_calls, 2)

    def test_float_wiggle_writes_nudge_then_original_via_osc(self) -> None:
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "layers": [{"master": {"id": 99, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)

        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        # OSC sends: master→0, target nudge, target original, master restore
        layer_sends = [s for s in osc.sends if s[0] == "/composition/layers/1/master"]
        self.assertEqual(len(layer_sends), 2)
        nudge, original = layer_sends
        self.assertAlmostEqual(nudge[1], 0.501, places=4)
        self.assertAlmostEqual(original[1], 0.5, places=4)
        self.assertEqual(engine._last_pass_wiggle_count, 1)

    def test_float_wiggle_at_max_nudges_downward(self) -> None:
        composition = {
            "master": {"id": 1, "value": 1.0},
            "layers": [{"master": {"id": 99, "value": 1.0, "valuerange": {"min": 0, "max": 1}}}],
        }
        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        layer_sends = [s for s in osc.sends if s[0] == "/composition/layers/1/master"]
        self.assertEqual(len(layer_sends), 2)
        nudge, original = layer_sends
        self.assertAlmostEqual(nudge[1], 0.999, places=4)
        self.assertAlmostEqual(original[1], 1.0, places=4)

    def test_bool_wiggle_flip_flops(self) -> None:
        composition = {
            "master": {"id": 1, "value": 1.0},
            "video": {"effects": [{"name": {"value": "MyEffect"}, "id": 100, "value": False}]},
        }
        # The path-walker indexes both /composition/video/effects/1 and
        # /composition/video/effects/myeffect; the bool itself is the param.
        # For this test we hand-craft a target whose path matches our walker output.
        targets = [SyncTarget(osc_path="/composition/video/effects/1", kind=KIND_BOOL, param_node_name="RangedParam[bool]")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        sends = [s for s in osc.sends if s[0] == "/composition/video/effects/1"]
        self.assertEqual(len(sends), 2)
        self.assertEqual(sends[0][1], True)   # flip from False
        self.assertEqual(sends[1][1], False)  # back to original

    def test_int_wiggle_bump_and_back(self) -> None:
        composition = {
            "master": {"id": 1, "value": 1.0},
            "layers": [{"transition": {"id": 7, "value": 3, "valuerange": {"min": 0, "max": 10}}}],
        }
        targets = [SyncTarget(osc_path="/composition/layers/1/transition", kind=KIND_INT, param_node_name="ParamChoice[int]")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        sends = [s for s in osc.sends if s[0] == "/composition/layers/1/transition"]
        self.assertEqual(len(sends), 2)
        self.assertEqual(sends[0][1], 4)  # bump
        self.assertEqual(sends[1][1], 3)  # back

    def test_master_to_zero_then_restore_wraps_pass(self) -> None:
        composition = {
            "master": {"id": 1, "value": 0.7, "valuerange": {"min": 0, "max": 1}},
        }
        targets = [SyncTarget(osc_path="/composition/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        master_sends = [s for s in osc.sends if s[0] == "/composition/master"]
        # First: mask to 0. Last: restore to 0.7. Middle: nudge + original (target wiggle).
        self.assertEqual(master_sends[0][1], 0.0)
        self.assertAlmostEqual(master_sends[-1][1], 0.7, places=4)

    def test_unreachable_rest_records_error_no_crash(self) -> None:
        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, _osc, _midi = _build_osc_sync(targets=targets, fail_get=True)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        self.assertIsNotNone(engine._last_pass_error)
        self.assertIn("composition fetch failed", engine._last_pass_error or "")

    def test_skip_target_when_path_missing_in_tree(self) -> None:
        composition = {"master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}}}
        # Target points at a path that doesn't exist in our tree
        targets = [SyncTarget(osc_path="/composition/missing/path", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        self.assertEqual(engine._last_pass_wiggle_count, 0)
        self.assertEqual(engine._last_pass_skipped_count, 1)
        # The missing path was never sent
        self.assertFalse(any(addr == "/composition/missing/path" for addr, _ in osc.sends))

    def test_resync_targets_rebuilds_from_xml(self) -> None:
        # Write a tiny preset XML and verify resync_targets parses it
        xml = """<?xml version="1.0" encoding="utf-8"?>
<OSCShortcutPreset>
  <ShortcutManager>
    <Shortcut paramNodeName="ParamRange">
      <ShortcutPath name="InputPath" path="/composition/layers/1/master" allowedTranslationTypes="11"/>
      <ShortcutPath name="OutputPath" path="/composition/layers/1/master" allowedTranslationTypes="11"/>
    </Shortcut>
    <Shortcut paramNodeName="ParamEvent">
      <ShortcutPath name="InputPath" path="/composition/layers/1/connectnextclip" allowedTranslationTypes="11"/>
      <ShortcutPath name="OutputPath" path="/composition/layers/1/connectnextclip" allowedTranslationTypes="-1"/>
    </Shortcut>
  </ShortcutManager>
</OSCShortcutPreset>"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(xml)
            xml_path = f.name
        try:
            engine, _rest, _osc, _midi = _build_osc_sync(
                targets=None,
                composition={},
                config_overrides={"osc_preset_path": xml_path},
            )
            count = engine.resync_targets()
            self.assertEqual(count, 1)  # ParamEvent skipped, ParamRange kept
            self.assertEqual(engine._targets[0].kind, KIND_FLOAT)
        finally:
            os.unlink(xml_path)

    def test_indicator_held_then_released_around_pass(self) -> None:
        composition = {
            "master": {"id": 1, "value": 0.7},
            "layers": [{"master": {"id": 99, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        indicator_path = engine._sync_indicator_path
        indicator_sends = [v for path, v in osc.sends if path == indicator_path]
        # First indicator write is True (hold), last is False (release)
        self.assertEqual(indicator_sends[0], True)
        self.assertEqual(indicator_sends[-1], False)

    def test_self_induced_cc_does_not_retrigger(self) -> None:
        # Simulate the wire patch echoing the engine's own indicator write
        # back as a CC 90 = 127. Should be swallowed by the syncing flag.
        composition = {
            "master": {"id": 1, "value": 1.0},
            "layers": [{"master": {"id": 99, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        # Patch sleep so we can deterministically interleave: while syncing,
        # any extra CC 90 = 127 events should NOT spawn a new pass.
        recorded_get_calls = []

        class WatchedRest(FakeRestClient):
            def __init__(self, composition, on_get):
                super().__init__(composition=composition)
                self._on_get = on_get

            def get_composition(self):
                self._on_get()
                return super().get_composition()

        midi = RecordingMidiOut()
        rest = WatchedRest(composition=composition, on_get=lambda: recorded_get_calls.append(1))
        osc = FakeOscClient()
        engine = OscSyncEngine(
            name="OSC Sync",
            config=_osc_sync_config(),
            midi_out=midi,
            rest_client=rest,
            osc_client=osc,
            sleep=lambda _t: None,
        )
        engine._targets = targets

        # First press
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        # While the worker runs, simulate self-induced rising edges (engine writes
        # indicator=1 -> wire echoes -> CC 90 = 127). These should all be swallowed.
        for _ in range(5):
            engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        # Only one composition GET = exactly one pass ran
        self.assertEqual(len(recorded_get_calls), 1)

    def test_indicator_path_excluded_from_wiggles(self) -> None:
        # If the OSC preset includes the indicator path, the wiggle pass
        # should skip it (so the indicator doesn't briefly flicker off mid-sync).
        composition = {
            "master": {"id": 1, "value": 1.0},
            "video": {"effects": [{"name": {"value": "OSCSync"}, "id": 1, "value": True}]},
        }
        indicator_path = "/composition/video/effects/oscsync/effect/sync/sync"
        targets = [
            SyncTarget(osc_path=indicator_path, kind=KIND_BOOL, param_node_name="RangedParam[bool]"),
            SyncTarget(osc_path="/composition/master", kind=KIND_FLOAT, param_node_name="ParamRange"),
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        # Indicator path should appear ONLY for hold (True) and release (False),
        # NOT for a wiggle flip-flop pair (which would be False then True for a
        # bool currently True).
        indicator_sends = [v for path, v in osc.sends if path == indicator_path]
        self.assertEqual(indicator_sends, [True, False])

    def test_concurrent_press_does_not_stack_workers(self) -> None:
        # Slow REST GET → first pass is still running when second press fires
        slow_event = threading.Event()

        class SlowRest(FakeRestClient):
            def get_composition(self) -> dict:
                slow_event.wait(timeout=0.5)
                return self._composition

        targets = [SyncTarget(osc_path="/composition/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        midi = RecordingMidiOut()
        rest = SlowRest(composition={"master": {"id": 1, "value": 1.0}})
        osc = FakeOscClient()
        engine = OscSyncEngine(
            name="OSC Sync",
            config=_osc_sync_config(),
            midi_out=midi,
            rest_client=rest,
            osc_client=osc,
            sleep=lambda _t: None,
        )
        engine._targets = targets

        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        first_worker = engine._worker
        # Second press while first is blocked on REST
        engine.on_midi_in(channel=14, cc=90, value=0, now=0.1)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.2)
        # Should be the same worker (not replaced)
        self.assertIs(engine._worker, first_worker)
        slow_event.set()
        first_worker.join(timeout=1.0)


class OscPresetParserTests(unittest.TestCase):
    def test_skips_event_triggers_and_disabled_outputs(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<OSCShortcutPreset>
  <ShortcutManager>
    <Shortcut paramNodeName="ParamRange">
      <ShortcutPath name="InputPath" path="/keep/float" allowedTranslationTypes="11"/>
      <ShortcutPath name="OutputPath" path="/keep/float" allowedTranslationTypes="11"/>
    </Shortcut>
    <Shortcut paramNodeName="RangedParam[bool]">
      <ShortcutPath name="InputPath" path="/disabled/bool" allowedTranslationTypes="1"/>
      <ShortcutPath name="OutputPath" path="/disabled/bool" allowedTranslationTypes="-1"/>
    </Shortcut>
    <Shortcut paramNodeName="ParamEvent">
      <ShortcutPath name="InputPath" path="/event/trigger" allowedTranslationTypes="11"/>
      <ShortcutPath name="OutputPath" path="/event/trigger" allowedTranslationTypes="11"/>
    </Shortcut>
    <Shortcut paramNodeName="Parameter[std::string]">
      <ShortcutPath name="InputPath" path="/string/param" allowedTranslationTypes="11"/>
      <ShortcutPath name="OutputPath" path="/string/param" allowedTranslationTypes="11"/>
    </Shortcut>
  </ShortcutManager>
</OSCShortcutPreset>"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(xml)
            xml_path = f.name
        try:
            targets = parse_osc_preset(xml_path)
            paths = {t.osc_path for t in targets}
            self.assertEqual(paths, {"/keep/float"})
        finally:
            os.unlink(xml_path)

    def test_malformed_xml_returns_empty_list(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write("<not really xml")
            xml_path = f.name
        try:
            self.assertEqual(parse_osc_preset(xml_path), [])
        finally:
            os.unlink(xml_path)


if __name__ == "__main__":
    unittest.main()
