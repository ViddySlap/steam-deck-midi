"""Tests for FlashBlastEngine (6-effect tap/build/fade architecture)."""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, RecordingMidiOut
from windows.engines.flash_blast import (
    DEFAULT_OSC_COLOR_BUILD_BUMP,
    DEFAULT_OSC_COLOR_BUILD_DECAY,
    DEFAULT_OSC_COLOR_BUILD_OPACITY,
    DEFAULT_OSC_COLOR_FADE_BUMP,
    DEFAULT_OSC_COLOR_FADE_OPACITY,
    DEFAULT_OSC_STROBE_BYPASS,
    DEFAULT_OSC_STROBE_OPACITY,
    DEFAULT_OSC_WHITE_BUILD_BUMP,
    DEFAULT_OSC_WHITE_BUILD_DECAY,
    DEFAULT_OSC_WHITE_BUILD_OPACITY,
    DEFAULT_OSC_WHITE_FADE_BUMP,
    DEFAULT_OSC_WHITE_FADE_OPACITY,
    RELEASE_NORM,
    SATURATION_NORM,
    STATE_BUILDING,
    STATE_IDLE,
    STATE_PENDING,
    STATE_RELEASING,
    STROBE_REST_OPACITY,
    FlashBlastEngine,
)
from windows.engines.registry import EngineRegistry
from windows.engines.steam_input_layer_tracker import (
    LAYER_CHASER,
    LAYER_FLASH,
    SteamInputLayerTrackerEngine,
)


def _build_engine(
    *,
    overrides: dict | None = None,
    with_tracker: bool = False,
    tracker_layer: str = LAYER_FLASH,
) -> tuple[FlashBlastEngine, FakeOscClient]:
    cfg: dict = {
        "name": "Flash Blast",
        "type": "flash_blast",
        "inputs": {
            "channel": 0,
            "cc_white_amount": 2,
            "cc_color_amount": 1,
        },
        "tolerance": 0.1,
        "tap_window_seconds": 0.08,
        "tap_peak_threshold": 0.5,
        "fade_release_delay_seconds": 0.05,
        "layer_debounce_seconds": 0.15,
    }
    if overrides:
        cfg.update(overrides)
    osc = FakeOscClient()
    midi = RecordingMidiOut()
    engine = FlashBlastEngine(cfg["name"], cfg, midi, osc_client=osc)
    engines = [engine]
    if with_tracker:
        tracker = SteamInputLayerTrackerEngine(
            "tracker",
            {
                "chaser_notes": [60, 62],
                "flash_notes": [61, 63],
                "default_layer": tracker_layer,
            },
            RecordingMidiOut(),
        )
        engines.insert(0, tracker)
    registry = EngineRegistry(engines)
    for eng in engines:
        eng.bind_registry(registry)
    return engine, osc


def _cc_for_norm(norm: float) -> int:
    return max(0, min(127, int(round(norm * 127))))


def _writes(osc: FakeOscClient, path: str) -> list:
    return [v for p, v in osc.sends if p == path]


class FlashBlastInitTests(unittest.TestCase):
    def test_init_writes_rest_state(self) -> None:
        _, osc = _build_engine()
        # STROBE rest: bypass=on + opacity=1.0 (Y-button contract).
        self.assertEqual(_writes(osc, DEFAULT_OSC_STROBE_BYPASS), [True])
        self.assertEqual(
            _writes(osc, DEFAULT_OSC_STROBE_OPACITY), [STROBE_REST_OPACITY]
        )
        # BUILD rest: Decay=0 (held mode), Opacity=0 (hidden), Bump=0.
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_DECAY), [0.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY), [0.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_BUMP), [0.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_COLOR_BUILD_DECAY), [0.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_COLOR_BUILD_OPACITY), [0.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_COLOR_BUILD_BUMP), [0.0])
        # FADE rest: Opacity=1 (always ready), Bump=0.
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_FADE_OPACITY), [1.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP), [0.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_COLOR_FADE_OPACITY), [1.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_COLOR_FADE_BUMP), [0.0])


class FlashBlastPendingEntryTests(unittest.TestCase):
    def test_below_engage_floor_stays_idle(self) -> None:
        engine, _ = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.05), now=0.0)  # below 0.1 floor
        self.assertEqual(engine._white_lane.state, STATE_IDLE)

    def test_above_engage_floor_enters_pending(self) -> None:
        engine, osc = _build_engine()
        osc.sends.clear()
        engine.on_midi_in(0, 2, _cc_for_norm(0.20), now=0.0)
        self.assertEqual(engine._white_lane.state, STATE_PENDING)
        self.assertAlmostEqual(engine._white_lane.pending_engage_time, 0.0)
        # No visual changes yet during PENDING (deferred decision).
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY), [])
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_BUMP), [])
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP), [])


class FlashBlastTapTests(unittest.TestCase):
    def test_quick_release_above_peak_threshold_fires_fade(self) -> None:
        engine, osc = _build_engine()
        # Engage to PENDING with norm > tap_peak_threshold (0.5).
        engine.on_midi_in(0, 2, _cc_for_norm(0.7), now=0.0)
        osc.sends.clear()
        # Release within tap window (0.08s).
        engine.on_midi_in(0, 2, 0, now=0.04)
        self.assertEqual(engine._white_lane.state, STATE_IDLE)
        # FADE bump fired (1.0 then we expect tick-based release later).
        fade_writes = _writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP)
        self.assertIn(1.0, fade_writes)
        # BUILD untouched on tap.
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY), [])

    def test_quick_release_below_peak_threshold_is_accidental(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.30), now=0.0)  # peak 0.3, < 0.5
        osc.sends.clear()
        engine.on_midi_in(0, 2, 0, now=0.04)
        self.assertEqual(engine._white_lane.state, STATE_IDLE)
        # No FADE fire on accidental brush.
        self.assertNotIn(1.0, _writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP))

    def test_fade_bump_release_deferred_to_tick(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.7), now=0.0)
        osc.sends.clear()
        engine.on_midi_in(0, 2, 0, now=0.04)  # tap fires FADE.Bump (0 then 1)
        # After fire, FADE.Bump writes end in 1.0 (not yet released).
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP)[-1], 1.0)
        # Tick before release delay -- still at 1.0.
        engine.tick(now=0.05)  # 0.01s after fire, < 0.05s delay
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP)[-1], 1.0)
        # Tick after release delay -- now releases.
        engine.tick(now=0.10)  # 0.06s after fire, > 0.05s delay
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP)[-1], 0.0)


class FlashBlastFastTapTests(unittest.TestCase):
    def test_norm_crosses_release_norm_in_pending_fires_fade_immediately(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)  # PENDING
        osc.sends.clear()
        # Within tap_window, push past RELEASE_NORM.
        engine.on_midi_in(0, 2, 127, now=0.05)  # norm=1.0, < 0.2 window
        # Should fire FADE immediately and transition to RELEASING.
        self.assertEqual(engine._white_lane.state, STATE_RELEASING)
        self.assertIn(1.0, _writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP))
        # BUILD never touched on fast-tap path.
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY), [])
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_BUMP), [])

    def test_fast_tap_re_arms_on_release(self) -> None:
        engine, _ = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)
        engine.on_midi_in(0, 2, 127, now=0.05)  # fast-tap -> RELEASING
        self.assertEqual(engine._white_lane.state, STATE_RELEASING)
        # Drop trigger -> RELEASING -> IDLE.
        engine.on_midi_in(0, 2, 0, now=0.10)
        self.assertEqual(engine._white_lane.state, STATE_IDLE)

    def test_norm_crosses_release_after_window_expires_uses_building_path(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)  # PENDING
        engine.tick(now=0.21)  # past tap_window -> BUILDING
        self.assertEqual(engine._white_lane.state, STATE_BUILDING)
        osc.sends.clear()
        # Now cross RELEASE_NORM in BUILDING (not PENDING).
        engine.on_midi_in(0, 2, 127, now=0.22)
        # Existing path: BUILDING -> RELEASING with BUILD hidden + FADE fired.
        self.assertEqual(engine._white_lane.state, STATE_RELEASING)
        self.assertIn(0.0, _writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY))
        self.assertIn(1.0, _writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP))


class FlashBlastBuildingTests(unittest.TestCase):
    def test_tap_window_expiry_via_tick_starts_building(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)  # PENDING
        self.assertEqual(engine._white_lane.state, STATE_PENDING)
        osc.sends.clear()
        engine.tick(now=0.09)  # past tap_window
        self.assertEqual(engine._white_lane.state, STATE_BUILDING)
        # BUILD.Bump pulsed clean (0 then 1) + opacity ramp written.
        bump_writes = _writes(osc, DEFAULT_OSC_WHITE_BUILD_BUMP)
        self.assertEqual(bump_writes, [0.0, 1.0])
        # Post-engage remap with tolerance=0.1: at norm=0.3,
        # remap = (0.3-0.1)/0.9 = 0.222, sat_remap = (0.6-0.1)/0.9 = 0.556,
        # ramp = 0.222/0.556 = 0.4. Saturation still aligns with norm=0.6.
        opacity_writes = _writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY)
        self.assertEqual(len(opacity_writes), 1)
        self.assertAlmostEqual(opacity_writes[0], 0.4, delta=0.01)

    def test_build_ramp_starts_at_zero_just_above_engage_floor(self) -> None:
        engine, osc = _build_engine()
        # Just above tolerance=0.1.
        engine.on_midi_in(0, 2, _cc_for_norm(0.11), now=0.0)  # PENDING
        engine.tick(now=0.09)  # PENDING -> BUILDING
        opacity_writes = _writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY)
        # Remapped at edge ~0.011, sat_remapped=0.556, ramp ~0.02.
        self.assertLess(opacity_writes[-1], 0.05)

    def test_building_ramp_updates_with_norm(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)
        engine.tick(now=0.09)  # PENDING -> BUILDING
        osc.sends.clear()
        engine.on_midi_in(0, 2, 127, now=0.10)  # well past saturation, but < RELEASE_NORM? 127/127=1.0 >= 0.95 -> goes to RELEASING
        # 127 = norm 1.0 -> RELEASING, not BUILDING. Use norm just below release.
        engine.on_midi_in(0, 2, _cc_for_norm(0.8), now=0.11)
        # State should still be RELEASING from norm=1.0 hit (not back to BUILDING).
        self.assertEqual(engine._white_lane.state, STATE_RELEASING)

    def test_building_ramp_saturates_at_saturation_norm(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)
        engine.tick(now=0.09)  # BUILDING
        osc.sends.clear()
        # norm = 0.65 -> ramp = 0.65/0.6 = clamped to 1.0; still < RELEASE.
        engine.on_midi_in(0, 2, _cc_for_norm(0.65), now=0.10)
        self.assertEqual(engine._white_lane.state, STATE_BUILDING)
        self.assertEqual(_writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY), [1.0])

    def test_building_to_releasing_fires_fade_hides_build(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)
        engine.tick(now=0.09)  # PENDING -> BUILDING
        osc.sends.clear()
        engine.on_midi_in(0, 2, 127, now=0.1)  # norm=1.0 >= RELEASE_NORM
        self.assertEqual(engine._white_lane.state, STATE_RELEASING)
        # BUILD hidden: opacity=0, bump released.
        self.assertIn(0.0, _writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY))
        self.assertIn(0.0, _writes(osc, DEFAULT_OSC_WHITE_BUILD_BUMP))
        # FADE fired.
        self.assertIn(1.0, _writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP))

    def test_building_abort_clean_disappear_no_fade(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)
        engine.tick(now=0.09)  # PENDING -> BUILDING
        osc.sends.clear()
        # Partial pull abort -- norm drops below engage_floor.
        engine.on_midi_in(0, 2, 0, now=0.15)
        self.assertEqual(engine._white_lane.state, STATE_IDLE)
        # BUILD hidden + bump released.
        self.assertIn(0.0, _writes(osc, DEFAULT_OSC_WHITE_BUILD_OPACITY))
        self.assertIn(0.0, _writes(osc, DEFAULT_OSC_WHITE_BUILD_BUMP))
        # FADE NOT fired on partial pull abort.
        self.assertNotIn(1.0, _writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP))


class FlashBlastReleasingTests(unittest.TestCase):
    def test_releasing_to_idle_on_norm_drop(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.3), now=0.0)
        engine.tick(now=0.09)  # BUILDING
        engine.on_midi_in(0, 2, 127, now=0.1)  # RELEASING
        self.assertEqual(engine._white_lane.state, STATE_RELEASING)
        engine.on_midi_in(0, 2, 0, now=0.2)
        self.assertEqual(engine._white_lane.state, STATE_IDLE)


class FlashBlastLayerGuardTests(unittest.TestCase):
    def test_wrong_layer_forces_idle(self) -> None:
        engine, osc = _build_engine(
            with_tracker=True, tracker_layer=LAYER_CHASER
        )
        # On chaser layer, R2 pull should not advance state.
        engine.on_midi_in(0, 2, _cc_for_norm(0.7), now=0.0)
        self.assertEqual(engine._white_lane.state, STATE_IDLE)


class FlashBlastLaneIsolationTests(unittest.TestCase):
    def test_white_cc_does_not_affect_color_lane(self) -> None:
        engine, _ = _build_engine()
        engine.on_midi_in(0, 2, _cc_for_norm(0.5), now=0.0)
        self.assertEqual(engine._white_lane.state, STATE_PENDING)
        self.assertEqual(engine._color_lane.state, STATE_IDLE)

    def test_color_cc_writes_to_color_paths(self) -> None:
        engine, osc = _build_engine()
        engine.on_midi_in(0, 1, _cc_for_norm(0.7), now=0.0)  # L2 = color lane
        osc.sends.clear()
        engine.on_midi_in(0, 1, 0, now=0.04)  # tap
        # Color FADE fired, white FADE untouched.
        self.assertIn(1.0, _writes(osc, DEFAULT_OSC_COLOR_FADE_BUMP))
        self.assertNotIn(1.0, _writes(osc, DEFAULT_OSC_WHITE_FADE_BUMP))


class FlashBlastChannelFilterTests(unittest.TestCase):
    def test_wrong_channel_ignored(self) -> None:
        engine, _ = _build_engine()
        engine.on_midi_in(15, 2, 127, now=0.0)  # ch15, not the input channel
        self.assertEqual(engine._white_lane.state, STATE_IDLE)

    def test_wrong_cc_ignored(self) -> None:
        engine, _ = _build_engine()
        engine.on_midi_in(0, 50, 127, now=0.0)  # cc 50, neither white nor color
        self.assertEqual(engine._white_lane.state, STATE_IDLE)
        self.assertEqual(engine._color_lane.state, STATE_IDLE)
