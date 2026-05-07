"""Tests for v0.3.0 engines (audio_opacity + auto_bypass)."""

from __future__ import annotations

import unittest
from collections import deque
from typing import Iterable

from windows.engines.audio_opacity import AudioOpacityEngine
from windows.engines.registry import EngineRegistry
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

    def test_video_stomp_masks_logo(self) -> None:
        """VIDEO STOMP held → output mask zeroes the logo channel without
        touching the natural goal computation. Mirrors the v0.2.0 wire patch
        piano-mode mapping of VIDEO STOMP → LOGO group bypass."""
        clock = FakeClock()
        engine = _audio_engine(clock=clock)
        engine.tick(clock.now)
        engine.on_midi_in(14, 101, 127, clock.now)  # enable
        # No audio → natural settles to LOGO (0, 1) at release=0.
        clock.advance(0.1)
        engine.tick(clock.now)
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_logo, 127)
        # VIDEO STOMP held → mask kills logo.
        engine.on_midi_in(14, 102, 127, clock.now)
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
        self.assertEqual(last_logo, 0)
        # Release → natural state revealed instantly (no recovery sequence).
        engine.on_midi_in(14, 102, 0, clock.now)
        last_logo = [v for ch, ctl, v in engine.midi_out.cc_events() if ctl == 111][-1]  # type: ignore[attr-defined]
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


if __name__ == "__main__":
    unittest.main()
