"""Tests for v0.3.x+ engines (audio_opacity, osc_sync)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
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

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.events.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.events.append(("note_off", channel, note, velocity))

    def cc_events(self) -> list[tuple[int, int, int]]:
        return [(c, ctl, v) for kind, c, ctl, v in self.events if kind == "cc"]

    def note_on_events(self) -> list[tuple[int, int, int]]:
        return [(c, n, v) for kind, c, n, v in self.events if kind == "note_on"]


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
    """Verify load_engines auto-merges factory defaults for missing engine types.

    v0.4.0+: configs live as `<type>.json` files inside `engines/` (user) and
    `engines.factory/` (factory). Legacy single-file `engines.json` is
    auto-migrated on first encounter.
    """

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

    def _write_dir(self, dir_path: Path, stanzas: list[dict]) -> None:
        dir_path.mkdir(parents=True, exist_ok=True)
        for stanza in stanzas:
            (dir_path / f"{stanza['type']}.json").write_text(
                json.dumps(stanza, indent=2), encoding="utf-8"
            )

    def test_factory_engine_merged_when_missing_from_user_dir(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user_dir = cfg_dir / "engines"
            factory_dir = cfg_dir / "engines.factory"
            self._write_dir(user_dir, [self._audio_stanza()])
            self._write_dir(factory_dir, [self._audio_stanza(), self._osc_sync_stanza()])
            midi = RecordingMidiOut()
            registry = load_engines(user_dir, midi)
            types = {e.type_name for e in registry.engines}
            self.assertEqual(types, {"audio_opacity", "osc_sync"})

    def test_user_customization_preserved_for_existing_type(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user_dir = cfg_dir / "engines"
            factory_dir = cfg_dir / "engines.factory"
            self._write_dir(user_dir, [self._audio_stanza(name="Custom Audio")])
            self._write_dir(factory_dir, [self._audio_stanza(name="Audio Engine")])
            midi = RecordingMidiOut()
            registry = load_engines(user_dir, midi)
            self.assertEqual(len(registry.engines), 1)
            # User's name wins, factory does NOT overwrite
            self.assertEqual(registry.engines[0].name, "Custom Audio")

    def test_user_disabled_engine_stays_disabled(self) -> None:
        # User explicitly disables an engine in their dir; factory-merge must
        # respect their `enabled: false` and not re-add via the factory entry.
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user_dir = cfg_dir / "engines"
            factory_dir = cfg_dir / "engines.factory"
            self._write_dir(
                user_dir,
                [self._audio_stanza(), self._osc_sync_stanza(enabled=False)],
            )
            self._write_dir(factory_dir, [self._audio_stanza(), self._osc_sync_stanza()])
            midi = RecordingMidiOut()
            registry = load_engines(user_dir, midi)
            types = {e.type_name for e in registry.engines}
            self.assertEqual(types, {"audio_opacity"})

    def test_no_factory_dir_works(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user_dir = cfg_dir / "engines"
            self._write_dir(user_dir, [self._audio_stanza()])
            midi = RecordingMidiOut()
            registry = load_engines(user_dir, midi)
            self.assertEqual(len(registry.engines), 1)

    def test_empty_user_dir_loads_full_factory(self) -> None:
        # Fresh install: user dir is empty (or only contains README.md), all
        # engines come from factory-merge.
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user_dir = cfg_dir / "engines"
            user_dir.mkdir()
            (user_dir / "README.md").write_text("docs", encoding="utf-8")
            factory_dir = cfg_dir / "engines.factory"
            self._write_dir(factory_dir, [self._audio_stanza(), self._osc_sync_stanza()])
            midi = RecordingMidiOut()
            registry = load_engines(user_dir, midi)
            types = {e.type_name for e in registry.engines}
            self.assertEqual(types, {"audio_opacity", "osc_sync"})

    def test_one_per_type_collision_keeps_alphabetical_first(self) -> None:
        # Two files declaring the same `type` — alphabetical-first filename
        # wins, the other is skipped with a warning.
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user_dir = cfg_dir / "engines"
            user_dir.mkdir()
            (user_dir / "audio_opacity.json").write_text(
                json.dumps(self._audio_stanza(name="Alpha")), encoding="utf-8"
            )
            (user_dir / "z_audio_variant.json").write_text(
                json.dumps(self._audio_stanza(name="Zeta")), encoding="utf-8"
            )
            midi = RecordingMidiOut()
            registry = load_engines(user_dir, midi)
            self.assertEqual(len(registry.engines), 1)
            self.assertEqual(registry.engines[0].name, "Alpha")

    def test_legacy_engines_json_auto_migrates_to_dir(self) -> None:
        # v0.3.x → v0.4.0 upgrade: legacy single-file engines.json is the only
        # engine config on disk. CLI defaults to engines/ dir which doesn't
        # exist. Loader migrates legacy file into the dir, archives the original.
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            legacy = cfg_dir / "engines.json"
            legacy.write_text(
                json.dumps(
                    {"engines": [self._audio_stanza(name="My Audio"), self._osc_sync_stanza()]}
                ),
                encoding="utf-8",
            )
            midi = RecordingMidiOut()
            registry = load_engines(cfg_dir / "engines", midi)
            types = {e.type_name for e in registry.engines}
            self.assertEqual(types, {"audio_opacity", "osc_sync"})
            # User's customization survived the migration.
            audio = next(e for e in registry.engines if e.type_name == "audio_opacity")
            self.assertEqual(audio.name, "My Audio")
            # Legacy file archived, dir populated.
            self.assertFalse(legacy.exists())
            self.assertTrue((cfg_dir / "engines.json.migrated").exists())
            self.assertTrue((cfg_dir / "engines" / "audio_opacity.json").exists())
            self.assertTrue((cfg_dir / "engines" / "osc_sync.json").exists())

    def test_legacy_factory_json_auto_migrates(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            (cfg_dir / "engines.factory.json").write_text(
                json.dumps(
                    {"engines": [self._audio_stanza(), self._osc_sync_stanza()]}
                ),
                encoding="utf-8",
            )
            midi = RecordingMidiOut()
            registry = load_engines(cfg_dir / "engines", midi)
            types = {e.type_name for e in registry.engines}
            self.assertEqual(types, {"audio_opacity", "osc_sync"})
            self.assertTrue((cfg_dir / "engines.factory.json.migrated").exists())
            self.assertTrue((cfg_dir / "engines.factory" / "audio_opacity.json").exists())

    def test_legacy_user_skipped_for_types_already_in_dir(self) -> None:
        # User upgraded post-v0.4.0 install but legacy engines.json was still
        # sitting alongside (e.g. they manually copied it back). User dir has
        # already-customized files. Migration must NOT clobber those.
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            user_dir = cfg_dir / "engines"
            self._write_dir(user_dir, [self._audio_stanza(name="Recent Custom")])
            (cfg_dir / "engines.json").write_text(
                json.dumps({"engines": [self._audio_stanza(name="Old Legacy")]}),
                encoding="utf-8",
            )
            midi = RecordingMidiOut()
            registry = load_engines(user_dir, midi)
            self.assertEqual(len(registry.engines), 1)
            self.assertEqual(registry.engines[0].name, "Recent Custom")
            # Legacy still archived (idempotency).
            self.assertTrue((cfg_dir / "engines.json.migrated").exists())

    def test_missing_path_yields_empty_registry(self) -> None:
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            midi = RecordingMidiOut()
            registry = load_engines(cfg_dir / "does-not-exist", midi)
            self.assertEqual(registry.engines, [])

    def test_legacy_file_path_argument_still_works(self) -> None:
        # Back-compat: caller passes path to `engines.json` directly. Loader
        # still resolves the sibling dir and uses the legacy file as input.
        from windows.engines.registry import load_engines
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            legacy = cfg_dir / "engines.json"
            legacy.write_text(
                json.dumps({"engines": [self._audio_stanza()]}), encoding="utf-8"
            )
            midi = RecordingMidiOut()
            registry = load_engines(legacy, midi)
            self.assertEqual(len(registry.engines), 1)
            self.assertTrue((cfg_dir / "engines" / "audio_opacity.json").exists())


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
            "layers": [{"master": {"id": 2, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        # Layer-master target (not excluded) so the pass exercises REST.
        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
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

    def test_float_wiggle_normalizes_against_param_range(self) -> None:
        """Regression for the OSC saturation bug (TODO 2026-05-07).

        Resolume's OSC :7000 normalizes 0-1 over the actual range for
        Wire-patch dashboard inputs (confirmed via live probe 2026-05-08:
        sending 0.5 to a [0, 5]-range param landed at 2.5).
        REST reports raw values, so the wiggle must convert raw -> 0..1
        before sending via OSC. Audio Engine tuning params (DURATION,
        RELEASE TIME, LOGO DELAY) all have range [0, 5] and were
        saturating to MAX before this fix.
        """
        # Real Resolume effects emit `name` as a string and put min/max
        # at the top level of each param (not nested in `valuerange`).
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "video": {
                "effects": [
                    {
                        "name": "AudioEngine",
                        "params": {
                            "DURATION": {
                                "id": 200,
                                "value": 2.5,
                                "min": 0.0,
                                "max": 5.0,
                            },
                        },
                    }
                ]
            },
        }
        # Path matches the OSC preset convention: effects/<slug>/effect/<param>
        path = "/composition/video/effects/audioengine/effect/duration"
        targets = [SyncTarget(osc_path=path, kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        sends = [s for s in osc.sends if s[0] == path]
        self.assertEqual(len(sends), 2)
        nudge, original = sends
        # Raw 2.5 over [0, 5] -> normalized 0.5; nudge is 0.5 + epsilon
        self.assertAlmostEqual(nudge[1], 0.501, places=4)
        self.assertAlmostEqual(original[1], 0.5, places=4)
        # Critical: the restore must NOT be the raw 2.5 (which would saturate)
        self.assertNotAlmostEqual(original[1], 2.5, places=4)

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
            "layers": [{"master": {"id": 2, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        # Use a layer master as the target (comp master is now excluded from wiggling).
        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)

        master_sends = [s for s in osc.sends if s[0] == "/composition/master"]
        # Comp master is masked at start (0.0) and restored at end (0.7) only.
        self.assertEqual(master_sends, [("/composition/master", 0.0), ("/composition/master", 0.7)])

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

    def test_indicator_force_transition_then_released(self) -> None:
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
        # Force a fresh 0 -> 1 transition at start so Resolume broadcasts to
        # TouchOSC even if the wire bool was already at 1 from button press.
        # Then 0 again at end to release.
        self.assertEqual(indicator_sends, [0.0, 1.0, 0.0])

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
        # Indicator path should appear ONLY for the start force-transition
        # (0.0 then 1.0) and the release (0.0). Not for a wiggle flip-flop.
        indicator_sends = [v for path, v in osc.sends if path == indicator_path]
        self.assertEqual(indicator_sends, [0.0, 1.0, 0.0])

    def test_comp_master_excluded_from_wiggle_iteration(self) -> None:
        # If /composition/master is in the OSC preset, it must NOT be wiggled
        # because the wiggle would pull master back to its cached value
        # mid-pass, undoing the mask.
        composition = {
            "master": {"id": 1, "value": 1.0, "valuerange": {"min": 0, "max": 1}},
            "layers": [{"master": {"id": 2, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        # Both master AND a layer master are wigglable in the preset.
        # Master must be skipped from the wiggle loop; only layer master gets wiggled.
        targets = [
            SyncTarget(osc_path="/composition/master", kind=KIND_FLOAT, param_node_name="ParamRange"),
            SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange"),
        ]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        # master_sends should be exactly [mask=0.0, restore=1.0] — no wiggle pair
        master_sends = [v for path, v in osc.sends if path == "/composition/master"]
        self.assertEqual(master_sends, [0.0, 1.0])
        # Layer master IS wiggled (not excluded)
        self.assertEqual(engine._last_pass_wiggle_count, 1)

    def test_fuzzy_resolver_matches_effect_group_param_pattern(self) -> None:
        # Resolume's OSC path for Wire patch dashboard params includes the
        # dashboard group as an extra segment. JSON tree's params dict is flat.
        # The path-walker emits effect/<param-slug>; the resolver must find it
        # when the target uses effect/<group>/<param-slug>.
        #
        # Uses VIDEO ALWAYS (a behaviour-toggle bool) rather than ENGINE
        # ENABLE because ENGINE ENABLE is now in the default engine-enable
        # excludes list (would be skipped from the wiggle iteration).
        composition = {
            "master": {"id": 1, "value": 1.0},
            "video": {
                "effects": [
                    {
                        "name": {"value": "AudioEngine"},
                        "params": {
                            "VIDEO ALWAYS": {"id": 100, "value": True},
                        },
                    }
                ]
            },
        }
        # XML target uses the full path with "engine" group segment
        target_path = "/composition/video/effects/audioengine/effect/engine/videoalways"
        targets = [SyncTarget(osc_path=target_path, kind=KIND_BOOL, param_node_name="RangedParam[bool]")]
        engine, _rest, osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        # The bool should have been wiggled (flipped to False then back to True)
        target_sends = [v for path, v in osc.sends if path == target_path]
        self.assertEqual(target_sends, [False, True])
        self.assertEqual(engine._last_pass_wiggle_count, 1)

    def test_skipped_paths_surfaced_in_status(self) -> None:
        composition = {
            "master": {"id": 1, "value": 1.0},
            "layers": [{"master": {"id": 2, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        }
        # Layer master resolves; missing path doesn't.
        targets = [
            SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange"),
            SyncTarget(osc_path="/composition/totally/missing/path", kind=KIND_FLOAT, param_node_name="ParamRange"),
        ]
        engine, _rest, _osc, _midi = _build_osc_sync(targets=targets, composition=composition)
        engine.on_midi_in(channel=14, cc=90, value=127, now=0.0)
        _wait_for_pass(engine)
        status = engine.status()
        self.assertEqual(status["last_pass_skipped_count"], 1)
        self.assertEqual(status["last_pass_skipped_paths"], ["/composition/totally/missing/path"])

    def test_concurrent_press_does_not_stack_workers(self) -> None:
        # Slow REST GET → first pass is still running when second press fires
        slow_event = threading.Event()

        class SlowRest(FakeRestClient):
            def get_composition(self) -> dict:
                slow_event.wait(timeout=0.5)
                return self._composition

        targets = [SyncTarget(osc_path="/composition/layers/1/master", kind=KIND_FLOAT, param_node_name="ParamRange")]
        midi = RecordingMidiOut()
        rest = SlowRest(composition={
            "master": {"id": 1, "value": 1.0},
            "layers": [{"master": {"id": 2, "value": 0.5, "valuerange": {"min": 0, "max": 1}}}],
        })
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


# ---------------------------------------------------------------------------
# Autopilot engine tests
# ---------------------------------------------------------------------------


class FakeOscClient:
    """Records OSC sends instead of hitting a socket."""

    def __init__(self) -> None:
        self.sends: list[tuple[str, Any]] = []
        self.closed = False

    def send(self, address: str, value: Any) -> None:
        self.sends.append((address, value))

    def close(self) -> None:
        self.closed = True


class FakeResolumeRest:
    """Hand-rolled stub of `ResolumeRestClient`."""

    def __init__(self, comp: dict | None = None) -> None:
        self._comp = comp or {"layers": []}
        self.calls: list[str] = []

    def set_comp(self, comp: dict) -> None:
        self._comp = comp

    def get_composition(self) -> dict:
        self.calls.append("composition")
        return self._comp


def _autopilot_config() -> dict:
    return {
        "name": "Autopilot",
        "type": "autopilot",
        "enabled": True,
        "update_hz": 30,
        "column_quantize": True,
        "enable_override_poll": False,  # disable the worker thread in tests
        "tempo_source": {"kind": "midi_clock", "port": "PULSE_OUT", "ppqn": 24},
        "inputs": {
            "channel": 14,
            "video": {
                "cc_enable": 60, "cc_beats": 61, "cc_transition": 62, "cc_mode": 63,
                "layer_ccs": {"1": 64, "2": 65, "3": 66, "4": 67},
            },
            "fx": {
                "cc_enable": 70, "cc_beats": 71, "cc_transition": 72, "cc_mode": 73,
                "layer_ccs": {"5": 74},
            },
            "logo": {
                "cc_enable": 80, "cc_beats": 81, "cc_transition": 82, "cc_mode": 83,
                "layer_ccs": {"6": 84, "7": 85},
            },
            "transition_max_seconds": 5.0,
            "beats_lookup": [1, 4, 8, 16, 32, 64, 128],
        },
        "outputs": {
            "osc": {"host": "127.0.0.1", "port": 7000},
            "rest": {"base_url": "http://127.0.0.1:8080", "timeout_seconds": 1.5},
        },
        "defaults": {
            "video": {"beats_per_clip": 4, "transition_seconds": 0.0, "clip_mode": 0},
            "fx": {"beats_per_clip": 4, "transition_seconds": 0.0, "clip_mode": 0},
            "logo": {"beats_per_clip": 4, "transition_seconds": 0.0, "clip_mode": 0},
        },
    }


def _make_autopilot(
    *,
    midi_out: "RecordingMidiOut | None" = None,
    osc: "FakeOscClient | None" = None,
    rest: "FakeResolumeRest | None" = None,
    overrides: dict | None = None,
) -> tuple["AutopilotEngine", RecordingMidiOut, FakeOscClient, FakeResolumeRest]:
    from windows.engines.autopilot import AutopilotEngine
    import random as _random

    cfg = _autopilot_config()
    if overrides:
        cfg.update(overrides)
    midi = midi_out or RecordingMidiOut()
    osc_client = osc or FakeOscClient()
    rest_client = rest or FakeResolumeRest()
    engine = AutopilotEngine(
        cfg["name"],
        cfg,
        midi,
        clock=time.monotonic,  # not used heavily in these tests; cross-fade uses tick spread
        rest_client=rest_client,
        osc_client=osc_client,
        rng=_random.Random(0),
    )
    return engine, midi, osc_client, rest_client


def _send_clock_beat(engine, beats: int = 1, *, now_start: float = 1.0, tick_dt: float = 0.020833) -> None:
    """Send `beats` worth of MIDI clock messages (24 ticks per beat)."""
    now = now_start
    for _ in range(beats * 24):
        engine.on_midi_clock("clock", now)
        now += tick_dt


def _enable_video_layers(engine, *layers: int) -> None:
    cfg = engine._channels["video"]
    for layer in layers:
        cc = cfg.layer_ccs[layer]
        engine.on_midi_in(14, cc, 127, 0.0)
    # Enable channel.
    engine.on_midi_in(14, cfg.cc_enable, 127, 0.0)


class AutopilotEngineCcTests(unittest.TestCase):
    """CC handling: enable / beats / transition / mode / layer toggles."""

    def test_enable_cc_toggles_state(self) -> None:
        engine, _, _, _ = _make_autopilot()
        engine.on_midi_in(14, 60, 127, 0.0)
        self.assertTrue(engine._states["video"].enabled)
        engine.on_midi_in(14, 60, 0, 0.0)
        self.assertFalse(engine._states["video"].enabled)

    def test_beats_cc_picks_lookup_value(self) -> None:
        engine, _, _, _ = _make_autopilot()
        engine.on_midi_in(14, 61, 0, 0.0)  # → beats_lookup[0] = 1
        self.assertEqual(engine._states["video"].beats_per_clip, 1)
        engine.on_midi_in(14, 61, 4, 0.0)  # → beats_lookup[4] = 32
        self.assertEqual(engine._states["video"].beats_per_clip, 32)
        engine.on_midi_in(14, 61, 6, 0.0)  # → beats_lookup[6] = 128
        self.assertEqual(engine._states["video"].beats_per_clip, 128)

    def test_transition_cc_scales_to_max_seconds(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        engine.on_midi_in(14, 62, 127, 0.0)
        self.assertAlmostEqual(engine._states["video"].transition_seconds, 5.0)
        engine.on_midi_in(14, 62, 64, 0.0)
        self.assertAlmostEqual(
            engine._states["video"].transition_seconds, (64 / 127.0) * 5.0
        )

    def test_mode_cc_picks_clip_mode_enum(self) -> None:
        from windows.engines.autopilot import ClipMode
        engine, _, _, _ = _make_autopilot()
        engine.on_midi_in(14, 63, 0, 0.0)
        self.assertEqual(engine._states["video"].clip_mode, ClipMode.NONE)
        engine.on_midi_in(14, 63, 1, 0.0)
        self.assertEqual(engine._states["video"].clip_mode, ClipMode.LINEAR)
        engine.on_midi_in(14, 63, 2, 0.0)
        self.assertEqual(engine._states["video"].clip_mode, ClipMode.RANDOM)

    def test_mode_transition_clears_bag(self) -> None:
        engine, _, _, _ = _make_autopilot()
        # Enter RANDOM and seed a bag.
        engine.on_midi_in(14, 63, 2, 0.0)
        engine._states["video"].bag[1] = [1, 2, 3]
        # Leave RANDOM → bag must clear.
        engine.on_midi_in(14, 63, 1, 0.0)
        self.assertNotIn(1, engine._states["video"].bag)

    def test_layer_ccs_toggle_membership(self) -> None:
        engine, _, _, _ = _make_autopilot()
        engine.on_midi_in(14, 64, 127, 0.0)  # video L1 on
        engine.on_midi_in(14, 66, 127, 0.0)  # video L3 on
        self.assertEqual(engine._states["video"].selected_layers(), [1, 3])
        engine.on_midi_in(14, 64, 0, 0.0)
        self.assertEqual(engine._states["video"].selected_layers(), [3])

    def test_other_channel_cc_ignored(self) -> None:
        engine, _, _, _ = _make_autopilot()
        engine.on_midi_in(0, 60, 127, 0.0)  # wrong channel
        self.assertFalse(engine._states["video"].enabled)


class AutopilotEngineTransitionDurationTests(unittest.TestCase):
    """Resolume's /composition/layers/N/transition/duration is normalized 0-1
    over a 0-10s range. Bridge stores transition in seconds and divides before
    sending OSC. Regression test for the v0.4.2 fix where 1s was landing as 10s
    (saturated) in Resolume's Trans Time UI control."""

    def test_send_layer_transition_normalizes_seconds_to_resolume_range(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        engine._send_layer_transition(3, 1.0)
        # 1 second should map to 0.1 (1/10) of Resolume's normalized range.
        sends = [(p, v) for p, v in osc.sends if p == "/composition/layers/3/transition/duration"]
        self.assertTrue(sends)
        path, value = sends[-1]
        self.assertAlmostEqual(value, 0.1, places=4)

    def test_send_layer_transition_clamps_above_max(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        engine._send_layer_transition(3, 50.0)  # absurd value
        sends = [(p, v) for p, v in osc.sends if p == "/composition/layers/3/transition/duration"]
        self.assertEqual(sends[-1][1], 1.0)


class AutopilotEngineCycleTests(unittest.TestCase):
    """Beat-driven cycle algorithm."""

    def test_single_layer_holds_master_at_one(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1)
        # Snap-to-first-selected on enable should already drive layer 1 → 1.0
        sends = [s for s in osc.sends if s[0] == "/composition/layers/1/master"]
        self.assertTrue(sends)
        self.assertEqual(sends[-1][1], 1.0)

    def test_two_layers_alternate_on_cycle(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        # beats_per_clip = 4 (default). One full beat-set per layer.
        # After 4 beats: cycle_index advances from 0 to 1 → layer 2 becomes target.
        _send_clock_beat(engine, beats=4)
        # transition=0 means instant snap on cycle advance, so visible_layer should be 2.
        self.assertEqual(engine._states["video"].visible_layer, 2)
        # Layer 2 master should have been driven to 1.0 at some point.
        master_2 = [v for path, v in osc.sends if path == "/composition/layers/2/master"]
        self.assertIn(1.0, master_2)

    def test_mode_none_does_not_advance_clips(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        # Default clip_mode = NONE. Two layers × 4 beats = 8 beats → one full cycle.
        _send_clock_beat(engine, beats=8)
        clip_sends = [path for path, _ in osc.sends if "/clips/" in path]
        # No clip writes whatsoever in NONE mode.
        self.assertEqual(clip_sends, [])

    def test_mode_linear_uses_clips_M_connect_path(self) -> None:
        comp = {
            "layers": [
                {"clips": [{"source": {"value": "a.mov"}}, {"source": {"value": "b.mov"}}]},
                {"clips": [{"source": {"value": "x.mov"}}, {"source": {"value": "y.mov"}}]},
            ]
        }
        engine, _, osc, _ = _make_autopilot(rest=FakeResolumeRest(comp))
        _enable_video_layers(engine, 1, 2)
        engine.on_midi_in(14, 63, 1, 0.0)  # LINEAR mode
        _send_clock_beat(engine, beats=8)
        clip_sends = [path for path, _ in osc.sends if "/clips/" in path and path.endswith("/connect")]
        # Indexed-clip path only; old /connect_next_clip is gone.
        self.assertTrue(all("/connect_next_clip" not in p for p in clip_sends))
        self.assertTrue(any("/composition/layers/1/clips/" in p for p in clip_sends))

    def test_mode_linear_advances_clips_in_order_with_wrap(self) -> None:
        # Layer 1 has exactly 2 loaded clips; LINEAR should fire 1, 2, 1, 2 ...
        comp = {
            "layers": [
                {"clips": [{"source": {"value": "a.mov"}}, {"source": {"value": "b.mov"}}]}
            ]
        }
        engine, _, osc, _ = _make_autopilot(rest=FakeResolumeRest(comp))
        _enable_video_layers(engine, 1)
        engine.on_midi_in(14, 63, 1, 0.0)  # LINEAR
        # Single layer; cycle wraps each beats_per_clip=4 beats. 4 wraps = 4 clip fires.
        seen: list[int] = []
        for _ in range(4):
            _send_clock_beat(engine, beats=4)
            for path, _ in reversed(osc.sends):
                if "/clips/" in path and path.endswith("/connect"):
                    seen.append(int(path.split("/")[-2]))
                    break
            osc.sends.clear()
        self.assertEqual(seen, [1, 2, 1, 2])

    def test_disabled_channel_does_not_touch_masters(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        # Layers selected but channel not enabled.
        cfg = engine._channels["video"]
        engine.on_midi_in(14, cfg.layer_ccs[1], 127, 0.0)
        engine.on_midi_in(14, cfg.layer_ccs[2], 127, 0.0)
        osc.sends.clear()
        _send_clock_beat(engine, beats=10)
        # No layer master writes should happen for an unenabled channel.
        master_writes = [s for s in osc.sends if "master" in s[0]]
        self.assertEqual(master_writes, [])


class AutopilotEngineCrossfadeTests(unittest.TestCase):
    def test_zero_transition_collapses_to_instant_snap(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        # transition stays at 0 from defaults.
        _send_clock_beat(engine, beats=4)
        # After the beat that advances cycle, target should already be cleared
        # (transition <= 0 collapses to instant snap inside _on_beat_boundary).
        self.assertIsNone(engine._states["video"].target_layer)
        self.assertEqual(engine._states["video"].visible_layer, 2)

    def test_nonzero_transition_holds_target_until_tick_completes(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        # Set a big transition so the cross-fade is still in flight after one beat.
        engine.on_midi_in(14, 62, 127, 0.0)  # 5 second transition
        # _send_clock_beat starts at now=1.0 with tick_dt=0.020833. After 4 beats
        # (96 ticks) the 4th beat boundary fires at now ≈ 1.0 + 95*0.020833 ≈ 2.979.
        _send_clock_beat(engine, beats=4)
        self.assertEqual(engine._states["video"].target_layer, 2)
        # Cross-fade now uses wall-clock elapsed (since v0.4.2). Pass a fake `now`
        # that matches the cross-fade-start instant so elapsed ≈ 0 → progress ≈ 0.
        engine.tick(3.0)
        # Visible layer is still 1, target is still 2 (fade barely started).
        self.assertEqual(engine._states["video"].visible_layer, 1)
        self.assertEqual(engine._states["video"].target_layer, 2)

    def test_wall_clock_progress_drives_crossfade(self) -> None:
        # New in v0.4.2: cross-fade uses now - crossfade_start_time, not tick deltas.
        # Verifies progress at a known wall-clock offset.
        engine, _, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        engine.on_midi_in(14, 62, 127, 0.0)  # 5s transition
        _send_clock_beat(engine, beats=4)
        # Halfway through the 5s fade.
        engine.tick(3.0 + 2.5)
        # Fade is in flight; both masters were written at progress=0.5.
        master_writes = [(p, v) for p, v in osc.sends if p.endswith("/master")]
        self.assertTrue(any(p == "/composition/layers/1/master" and 0.4 < v < 0.6 for p, v in master_writes))
        self.assertTrue(any(p == "/composition/layers/2/master" and 0.4 < v < 0.6 for p, v in master_writes))


class AutopilotEngineColumnQuantizeTests(unittest.TestCase):
    """Column trigger interception + replay on next beat. Channel 0, notes
    {82, 83, 86, 87} per Resolume's MIDI shortcut bindings (decoded 2026-05-07)."""

    def test_filter_passes_through_unrelated_notes(self) -> None:
        engine, _, _, _ = _make_autopilot()
        _enable_video_layers(engine, 1)
        # Unrelated note on the trigger channel passes through.
        self.assertTrue(engine._note_emit_filter(0, 50, 127, 0.0))
        # Column notes on a non-trigger channel pass through.
        self.assertTrue(engine._note_emit_filter(1, 86, 127, 0.0))

    def test_filter_passes_when_no_channel_enabled(self) -> None:
        engine, _, _, _ = _make_autopilot()
        # No layers selected, no channels enabled.
        self.assertTrue(engine._note_emit_filter(0, 86, 127, 0.0))
        self.assertTrue(engine._note_emit_filter(0, 87, 127, 0.0))

    def test_filter_defers_when_channel_enabled(self) -> None:
        engine, _, _, _ = _make_autopilot()
        _enable_video_layers(engine, 1)
        self.assertFalse(engine._note_emit_filter(0, 86, 127, 0.0))
        self.assertEqual(engine._pending_column_note, 86)

    def test_column_trigger_filter_intercepts_short_press_notes_82_83(self) -> None:
        engine, _, _, _ = _make_autopilot()
        _enable_video_layers(engine, 1)
        # Short-press LEFT.
        self.assertFalse(engine._note_emit_filter(0, 82, 127, 0.0))
        self.assertEqual(engine._pending_column_note, 82)
        # Drain pending and try short-press RIGHT.
        engine._pending_column_note = None
        self.assertFalse(engine._note_emit_filter(0, 83, 127, 0.0))
        self.assertEqual(engine._pending_column_note, 83)

    def test_pending_column_replays_on_next_beat(self) -> None:
        engine, midi, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        # User long-presses L_PAD_LEFT mid-cycle.
        engine._note_emit_filter(0, 86, 127, 0.0)
        # Advance one beat — should fire the deferred note.
        _send_clock_beat(engine, beats=1)
        column_notes = [
            (ch, note) for ch, note, _ in midi.note_on_events() if note in (82, 83, 86, 87)
        ]
        self.assertIn((0, 86), column_notes)
        # Pending cleared.
        self.assertIsNone(engine._pending_column_note)
        # Cycle reset to first selected layer.
        self.assertEqual(engine._states["video"].visible_layer, 1)
        self.assertEqual(engine._states["video"].cycle_index, 0)
        self.assertEqual(engine._states["video"].beat_in_clip, 0)

    def test_column_trigger_replays_resets_to_lowest_indexed_layer(self) -> None:
        engine, midi, _, _ = _make_autopilot()
        # Enable in non-sorted order; selected_layers() returns sorted.
        _enable_video_layers(engine, 3, 1, 2)
        # Spin the cycle a few beats so visible_layer drifts off the bottom.
        _send_clock_beat(engine, beats=5)
        self.assertNotEqual(engine._states["video"].visible_layer, 1)
        # Column trigger arrives, defer + replay on next beat.
        engine._note_emit_filter(0, 87, 127, 0.0)
        _send_clock_beat(engine, beats=1)
        # Lowest-indexed selected layer = 1.
        self.assertEqual(engine._states["video"].visible_layer, 1)

    def test_second_pending_press_drops(self) -> None:
        engine, _, _, _ = _make_autopilot()
        _enable_video_layers(engine, 1)
        engine._note_emit_filter(0, 86, 127, 0.0)
        # Second press while one is pending — drop it.
        self.assertFalse(engine._note_emit_filter(0, 87, 127, 0.0))
        self.assertEqual(engine._pending_column_note, 86)


class AutopilotEngineClockTests(unittest.TestCase):
    def test_start_resets_state(self) -> None:
        engine, _, _, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        _send_clock_beat(engine, beats=2)
        engine.on_midi_clock("start", 0.0)
        self.assertEqual(engine._tick_count, 0)
        self.assertEqual(engine._states["video"].beat_in_clip, 0)
        self.assertEqual(engine._states["video"].cycle_index, 0)

    def test_stop_pauses_continue_resumes(self) -> None:
        engine, _, _, _ = _make_autopilot()
        _enable_video_layers(engine, 1, 2)
        engine.on_midi_clock("stop", 0.0)
        ticks_before = engine._tick_count
        # Clock messages while stopped should be ignored.
        engine.on_midi_clock("clock", 0.1)
        self.assertEqual(engine._tick_count, ticks_before)
        # Continue → next clock advances.
        engine.on_midi_clock("continue", 0.2)
        engine.on_midi_clock("clock", 0.3)
        self.assertEqual(engine._tick_count, ticks_before + 1)

    def test_bpm_estimate_within_tolerance(self) -> None:
        engine, _, _, _ = _make_autopilot()
        # 120 BPM = 0.5 sec/beat = 0.020833 sec/tick.
        now = 0.0
        for _ in range(48):  # two beats worth of ticks
            engine.on_midi_clock("clock", now)
            now += 0.020833
        bpm = engine._estimate_bpm()
        self.assertIsNotNone(bpm)
        assert bpm is not None  # mypy
        self.assertAlmostEqual(bpm, 120.0, delta=1.0)


class AutopilotEngineRandomTests(unittest.TestCase):
    def test_mode_random_uses_bag_pattern(self) -> None:
        comp = {
            "layers": [
                {  # layer 1 with 3 loaded clips
                    "clips": [
                        {"source": {"value": "a.mov"}},
                        {"source": {"value": "b.mov"}},
                        {"source": {"value": "c.mov"}},
                    ]
                }
            ]
        }
        engine, _, osc, _ = _make_autopilot(rest=FakeResolumeRest(comp))
        _enable_video_layers(engine, 1)
        engine.on_midi_in(14, 63, 2, 0.0)  # RANDOM
        # Single layer; cycle wraps each beats_per_clip=4 beats. 3 wraps = 3 draws.
        seen: list[int] = []
        for _ in range(3):
            _send_clock_beat(engine, beats=4)
            for path, _ in reversed(osc.sends):
                if "/clips/" in path and path.endswith("/connect"):
                    seen.append(int(path.split("/")[-2]))
                    break
        # Bag pattern: three draws is a permutation of {1, 2, 3} on first bag
        # (last_clip is None so all three are eligible).
        self.assertEqual(sorted(seen), [1, 2, 3])

    def test_random_with_no_clips_silently_skips(self) -> None:
        # /connect_next_clip fallback was removed in v0.4.1. Empty REST → no-op.
        engine, _, osc, _ = _make_autopilot(rest=FakeResolumeRest({"layers": []}))
        _enable_video_layers(engine, 1)
        engine.on_midi_in(14, 63, 2, 0.0)  # RANDOM
        _send_clock_beat(engine, beats=4)
        # No /clips/M/connect path should appear.
        clip_sends = [path for path, _ in osc.sends if "/clips/" in path and path.endswith("/connect")]
        self.assertEqual(clip_sends, [])
        # And no legacy /connect_next_clip path either.
        self.assertFalse(any(path.endswith("/connect_next_clip") for path, _ in osc.sends))


class AutopilotEngineSingleLayerTests(unittest.TestCase):
    """Single-layer fast path (v0.4.1): skip cross-fade entirely, hold master 1.0."""

    def test_single_layer_skips_master_writes(self) -> None:
        engine, _, osc, _ = _make_autopilot()
        _enable_video_layers(engine, 1)
        # Snap-to-first-selected on enable writes layer 1 → 1.0; clear and observe
        # subsequent beats (which would cross-fade in multi-layer code).
        osc.sends.clear()
        _send_clock_beat(engine, beats=12)  # 3 cycles at beats_per_clip=4
        master_writes = [s for s in osc.sends if s[0].endswith("/master")]
        # Single-layer fast path: zero master writes after the initial snap.
        self.assertEqual(master_writes, [])

    def test_single_layer_still_advances_clip_in_linear_mode(self) -> None:
        comp = {
            "layers": [
                {"clips": [{"source": {"value": "a.mov"}}, {"source": {"value": "b.mov"}}]}
            ]
        }
        engine, _, osc, _ = _make_autopilot(rest=FakeResolumeRest(comp))
        _enable_video_layers(engine, 1)
        engine.on_midi_in(14, 63, 1, 0.0)  # LINEAR
        osc.sends.clear()
        _send_clock_beat(engine, beats=4)  # one cycle wrap
        # Even with a single layer, LINEAR should still fire indexed clip connect.
        clip_sends = [path for path, _ in osc.sends if "/clips/" in path and path.endswith("/connect")]
        self.assertTrue(clip_sends, "expected at least one /clips/M/connect send")
        # And no master writes (single-layer fast path).
        master_writes = [s for s in osc.sends if s[0].endswith("/master")]
        self.assertEqual(master_writes, [])


if __name__ == "__main__":
    unittest.main()
