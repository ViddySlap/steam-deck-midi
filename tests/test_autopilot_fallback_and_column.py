"""Autopilot: fallback clock (no Pulse) + per-group column advance on cycle wrap."""

from __future__ import annotations

import unittest

from windows.engines.autopilot import AutopilotEngine, ClipMode
from windows.midi import DryRunMidiOut


class FakeOsc:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    def send(self, address: str, value: object) -> None:
        self.sent.append((address, value))

    def close(self) -> None:
        return None

    def paths(self, needle: str) -> list[str]:
        return [a for a, _ in self.sent if needle in a]


def _config(**overrides) -> dict:
    cfg = {
        "name": "Autopilot",
        "type": "autopilot",
        "update_hz": 30,
        "column_quantize": False,
        "fallback_clock": {
            "enabled": True,
            "bpm": 120.0,  # 0.5s/beat -- round numbers for tests
            "takeover_after_seconds": 2.0,
        },
        "inputs": {
            "channel": 14,
            "video": {
                "cc_enable": 60, "cc_beats": 61, "cc_transition": 62, "cc_mode": 63,
                "layer_ccs": {"1": 64, "2": 65, "3": 66},
                "group": 1,
                "column_advance": True,
            },
            "fx": {
                "cc_enable": 70, "cc_beats": 71, "cc_transition": 72, "cc_mode": 73,
                "layer_ccs": {"5": 74},
                "group": None,
                "column_advance": False,
            },
            "logo": {
                "cc_enable": 80, "cc_beats": 81, "cc_transition": 82, "cc_mode": 83,
                "layer_ccs": {"6": 84, "7": 85},
                "group": 2,
                "column_advance": True,
            },
            "beats_lookup": [1, 4, 8, 16, 32, 64, 128],
        },
        "defaults": {
            "video": {"beats_per_clip": 1, "transition_seconds": 0.0, "clip_mode": 0},
            "fx": {"beats_per_clip": 1, "transition_seconds": 0.0, "clip_mode": 0},
            "logo": {"beats_per_clip": 1, "transition_seconds": 0.0, "clip_mode": 0},
        },
    }
    cfg.update(overrides)
    return cfg


def _engine(osc: FakeOsc, **overrides) -> AutopilotEngine:
    return AutopilotEngine(
        "Autopilot", _config(**overrides), DryRunMidiOut(), osc_client=osc
    )


def _enable_video(engine: AutopilotEngine, layers=(1, 2, 3), beats: int = 1) -> None:
    """Turn the video channel on with `layers` selected, via its real CCs."""
    engine.on_midi_in(14, 60, 127, 0.0)          # enable
    for layer, cc in zip((1, 2, 3), (64, 65, 66)):
        engine.on_midi_in(14, cc, 127 if layer in layers else 0, 0.0)
    state = engine._states["video"]
    state.beats_per_clip = beats
    state.clip_mode = ClipMode.NONE


class ColumnAdvanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.osc = FakeOsc()
        self.engine = _engine(self.osc)

    def _beat(self, engine: AutopilotEngine, n: int, t0: float = 1.0) -> None:
        for i in range(n):
            engine._on_beat_boundary(t0 + i)

    def test_column_advances_once_per_full_layer_cycle(self) -> None:
        _enable_video(self.engine, layers=(1, 2, 3), beats=1)
        self.osc.sent.clear()
        # First beat latches layer 1 (visible_layer was None), then 3 beats
        # walk 1->2->3, and the 4th wraps back to layer 1 = one column advance.
        self._beat(self.engine, 5)
        advances = self.osc.paths("connectnextcolumn")
        self.assertEqual(advances, ["/composition/groups/1/connectnextcolumn"])

    def test_two_cycles_give_two_advances(self) -> None:
        _enable_video(self.engine, layers=(1, 2, 3), beats=1)
        self.osc.sent.clear()
        self._beat(self.engine, 8)
        self.assertEqual(len(self.osc.paths("connectnextcolumn")), 2)

    def test_advance_targets_the_configured_group(self) -> None:
        """Logo is group 2, not group 1."""
        self.engine.on_midi_in(14, 80, 127, 0.0)
        self.engine.on_midi_in(14, 84, 127, 0.0)
        self.engine.on_midi_in(14, 85, 127, 0.0)
        self.engine._states["logo"].beats_per_clip = 1
        self.osc.sent.clear()
        self._beat(self.engine, 4)
        self.assertIn("/composition/groups/2/connectnextcolumn", self.osc.paths("connectnextcolumn"))

    def test_ungrouped_channel_never_advances(self) -> None:
        """FX (layer 5) has no Resolume group -- must not emit a bogus path."""
        self.engine.on_midi_in(14, 70, 127, 0.0)
        self.engine.on_midi_in(14, 74, 127, 0.0)
        self.engine._states["fx"].beats_per_clip = 1
        self.osc.sent.clear()
        self._beat(self.engine, 6)
        self.assertEqual(self.osc.paths("connectnextcolumn"), [])

    def test_fx_advances_its_clip_instead_of_a_column(self) -> None:
        """FX is ungrouped, so it steps clips on layer 5 rather than columns."""
        self.engine._layer_clips[5] = [1, 2, 3]
        self.engine.on_midi_in(14, 70, 127, 0.0)   # fx enable
        self.engine.on_midi_in(14, 74, 127, 0.0)   # layer 5 on
        state = self.engine._states["fx"]
        state.beats_per_clip = 1
        state.clip_mode = ClipMode.LINEAR
        self.osc.sent.clear()
        self._beat(self.engine, 4)
        self.assertEqual(self.osc.paths("connectnextcolumn"), [])
        clip_hits = self.osc.paths("/composition/layers/5/clips/")
        self.assertGreaterEqual(len(clip_hits), 2)

    def test_column_advance_off_disables_it(self) -> None:
        cfg = _config()
        cfg["inputs"]["video"]["column_advance"] = False
        osc = FakeOsc()
        engine = AutopilotEngine("Autopilot", cfg, DryRunMidiOut(), osc_client=osc)
        _enable_video(engine, layers=(1, 2, 3), beats=1)
        osc.sent.clear()
        self._beat(engine, 8)
        self.assertEqual(osc.paths("connectnextcolumn"), [])


class FallbackClockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.osc = FakeOsc()
        self.engine = _engine(self.osc)

    def test_inactive_before_takeover_window(self) -> None:
        self.engine.tick(0.5)
        self.assertFalse(self.engine._fallback_active)

    def test_takes_over_when_no_clock_arrives(self) -> None:
        self.engine.tick(0.0)  # establishes the grace anchor
        self.engine.tick(3.0)  # past takeover_after_seconds with no ticks
        self.assertTrue(self.engine._fallback_active)
        self.assertEqual(self.engine.status()["clock_source"], "fallback")

    def test_generates_beats_at_configured_bpm(self) -> None:
        """120 BPM = 0.5s/beat, so 3s of ticks should wrap the 3-layer cycle."""
        _enable_video(self.engine, layers=(1, 2, 3), beats=1)
        self.engine.tick(0.0)
        self.engine.tick(3.0)          # takeover; first synthetic beat at 3.5
        self.osc.sent.clear()
        t = 3.0
        while t < 6.0:
            t += 1.0 / 30.0
            self.engine.tick(t)
        # 3.5,4.0,...,6.0 -> ~6 beats -> at least one full 3-layer wrap
        self.assertGreaterEqual(len(self.osc.paths("connectnextcolumn")), 1)

    def test_real_clock_preempts_fallback(self) -> None:
        self.engine.tick(0.0)
        self.engine.tick(3.0)
        self.assertTrue(self.engine._fallback_active)
        self.engine.on_midi_clock("clock", 3.1)
        self.assertFalse(self.engine._fallback_active)
        self.assertEqual(self.engine.status()["clock_source"], "midi_clock")

    def test_fallback_resumes_if_clock_stops_again(self) -> None:
        self.engine.on_midi_clock("clock", 1.0)
        self.engine.tick(1.1)
        self.assertFalse(self.engine._fallback_active)
        self.engine.tick(5.0)  # clock went quiet
        self.assertTrue(self.engine._fallback_active)

    def test_disabled_fallback_never_activates(self) -> None:
        cfg = _config()
        cfg["fallback_clock"]["enabled"] = False
        engine = AutopilotEngine("Autopilot", cfg, DryRunMidiOut(), osc_client=FakeOsc())
        engine.tick(60.0)
        self.assertFalse(engine._fallback_active)

    def test_catchup_is_capped(self) -> None:
        """A long stall must not machine-gun beats into Resolume."""
        _enable_video(self.engine, layers=(1, 2, 3), beats=1)
        self.engine.tick(3.0)
        self.osc.sent.clear()
        self.engine.tick(600.0)  # 10 minutes later in one step
        masters = [a for a in self.osc.paths("/master")]
        self.assertLessEqual(len(self.osc.paths("connectnextcolumn")), 2)
        self.assertTrue(len(masters) < 100)

    def test_invalid_bpm_disables_rather_than_crashes(self) -> None:
        cfg = _config()
        cfg["fallback_clock"]["bpm"] = 0
        engine = AutopilotEngine("Autopilot", cfg, DryRunMidiOut(), osc_client=FakeOsc())
        self.assertFalse(engine._fallback_enabled)
        engine.tick(60.0)  # must not divide by zero


if __name__ == "__main__":
    unittest.main()
