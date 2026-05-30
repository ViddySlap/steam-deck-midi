"""Tests for GlobalColorEngine (MIDI-only, post Pass 3 Part B)."""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, RecordingMidiOut
from windows.engines.global_color import (
    DEFAULT_PALETTE_HEXES,
    PALETTE_SIZE,
    GlobalColorEngine,
    _cc_from_hex,
    _hex_from_cc,
)
from windows.engines.registry import EngineRegistry


CHASER_COLOR_PATH = "/composition/layers/10/video/effects/colorbump2/effect/color"
SHOCKWAVE_COLOR_PATH = (
    "/composition/layers/10/video/effects/shockwave/effect/flashcolor"
)
LOGO_HL_PATH = "/composition/video/effects/viddylut/effect/highlightcolor"
GYRO_HL_PATH = (
    "/composition/layers/11/video/effects/viddy-colorisfv2/effect/colors/highlight"
)
GYRO_SH_PATH = (
    "/composition/layers/11/video/effects/viddy-colorisfv2/effect/colors/shadow"
)
GYRO_WHITE_PATH = (
    "/composition/layers/11/video/effects/viddy-colorisfv2/effect/colors/replacewhite"
)


def _build_engine(
    *,
    config_overrides: dict | None = None,
    bind: bool = True,
) -> tuple[GlobalColorEngine, FakeOscClient, RecordingMidiOut]:
    cfg: dict = {
        "name": "Global Color",
        "type": "global_color",
        "channel": 14,
        "palette_channel": 13,
        "cc_base": 40,
        "palette_cc_base": 0,
        "resync_cc": 99,
        "fade_cc": 46,
        "default_fade_seconds": 0.0,
        "max_fade_seconds": 5.0,
        "palette_defaults": list(DEFAULT_PALETTE_HEXES),
        "channels": {
            "chaser": [
                {
                    "name": "Color Bump COLOR-long.Color",
                    "osc_path": CHASER_COLOR_PATH,
                    "format": "hex_rgba_string",
                },
                {
                    "name": "ShockWave.Flash Color",
                    "osc_path": SHOCKWAVE_COLOR_PATH,
                    "format": "hex_rgba_string",
                },
            ],
            "video_highlight": [],
            "video_shadow": [],
            "logo_highlight": [],
            "logo_shadow": [],
        },
    }
    if config_overrides:
        cfg.update(config_overrides)
    osc = FakeOscClient()
    midi = RecordingMidiOut()
    engine = GlobalColorEngine(cfg["name"], cfg, midi, osc_client=osc)
    if bind:
        registry = EngineRegistry([engine])
        engine.bind_registry(registry)
        # Clear the resync event emitted from bind_registry so individual
        # tests can assert cleanly.
        midi.events.clear()
    return engine, osc, midi


def _writes(osc: FakeOscClient, path: str) -> list:
    return [v for p, v in osc.sends if p == path]


class HexCcRoundTripTests(unittest.TestCase):
    def test_hex_from_cc_extremes(self) -> None:
        self.assertEqual(_hex_from_cc(127, 127, 127), "#ffffffff")
        self.assertEqual(_hex_from_cc(0, 0, 0), "#000000ff")

    def test_hex_from_cc_clamps(self) -> None:
        self.assertEqual(_hex_from_cc(200, -5, 127), "#ff00ffff")

    def test_cc_from_hex_extremes(self) -> None:
        self.assertEqual(_cc_from_hex("#ffffffff"), (127, 127, 127))
        self.assertEqual(_cc_from_hex("#000000ff"), (0, 0, 0))

    def test_round_trip_preserves_within_one_bit(self) -> None:
        # cc=64 -> hex=129 (0x81) -> back to cc=64. Stable.
        h = _hex_from_cc(64, 64, 64)
        self.assertEqual(_cc_from_hex(h), (64, 64, 64))


class ChannelCcTests(unittest.TestCase):
    def test_chaser_cc_writes_to_both_consumers(self) -> None:
        engine, osc, _ = _build_engine()
        # Raw value 0 -> index 0 -> palette[0] = red.
        engine.on_midi_in(14, 40, 0, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#ff0000ff"])
        self.assertEqual(_writes(osc, SHOCKWAVE_COLOR_PATH), ["#ff0000ff"])

    def test_chaser_cc_updates_active_index(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(14, 40, 9, now=0.0)
        self.assertEqual(engine._channels["chaser"].active_index, 9)

    def test_channel_value_clamped_to_palette_range(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(14, 40, 127, now=0.0)  # raw 127 > 9, clamps to 9.
        self.assertEqual(engine._channels["chaser"].active_index, 9)

    def test_channel_value_is_raw_not_normalized(self) -> None:
        # Wire patch's channel Write CC has normalize=false, so value 5 means
        # palette index 5 directly (not 5/127*9 like the old code did).
        engine, osc, _ = _build_engine()
        engine.on_midi_in(14, 40, 5, now=0.0)
        # palette[5] = blue.
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#0000ffff"])

    def test_empty_channel_writes_nothing_but_records_index(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_midi_in(14, 41, 5, now=0.0)
        self.assertEqual(osc.sends, [])
        self.assertEqual(engine._channels["video_highlight"].active_index, 5)

    def test_wrong_channel_ignored_for_channel_cc(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_midi_in(0, 50, 0, now=0.0)
        self.assertEqual(osc.sends, [])

    def test_unknown_cc_on_input_channel_ignored(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_midi_in(14, 70, 0, now=0.0)
        self.assertEqual(osc.sends, [])


class GyroChannelSplitTests(unittest.TestCase):
    """The former single gyro_feedback channel (one CC, two consumers) is
    split into two independent channels: gyro_highlight (CC 96) and
    gyro_shadow (CC 97), each driving one consumer on Layer 11."""

    def _build_gyro_engine(self):
        return _build_engine(
            config_overrides={
                "channels": {
                    "chaser": [
                        {"osc_path": CHASER_COLOR_PATH, "format": "hex_rgba_string"}
                    ],
                    "gyro_highlight": [
                        {
                            "name": "VIDDY-COLOR ISF V2 gyro.Highlight",
                            "osc_path": GYRO_HL_PATH,
                            "format": "hex_rgba_string",
                        }
                    ],
                    "gyro_shadow": [
                        {
                            "name": "VIDDY-COLOR ISF V2 gyro.Shadow",
                            "osc_path": GYRO_SH_PATH,
                            "format": "hex_rgba_string",
                        }
                    ],
                    "gyro_white": [
                        {
                            "name": "VIDDY-COLOR ISF V2 gyro.Replace White",
                            "osc_path": GYRO_WHITE_PATH,
                            "format": "hex_rgba_string",
                        }
                    ],
                }
            }
        )

    def test_gyro_highlight_cc_96_writes_only_highlight(self) -> None:
        engine, osc, _ = self._build_gyro_engine()
        # CC 96 raw value 0 -> palette[0] = red.
        engine.on_midi_in(14, 96, 0, now=0.0)
        self.assertEqual(_writes(osc, GYRO_HL_PATH), ["#ff0000ff"])
        # Shadow consumer must NOT be touched by the highlight CC.
        self.assertEqual(_writes(osc, GYRO_SH_PATH), [])

    def test_gyro_shadow_cc_97_writes_only_shadow(self) -> None:
        engine, osc, _ = self._build_gyro_engine()
        # CC 97 raw value 5 -> palette[5] = blue.
        engine.on_midi_in(14, 97, 5, now=0.0)
        self.assertEqual(_writes(osc, GYRO_SH_PATH), ["#0000ffff"])
        self.assertEqual(_writes(osc, GYRO_HL_PATH), [])

    def test_gyro_channels_are_independent(self) -> None:
        engine, osc, _ = self._build_gyro_engine()
        # Highlight to green (palette[3]), shadow to cyan (palette[4]).
        engine.on_midi_in(14, 96, 3, now=0.0)
        engine.on_midi_in(14, 97, 4, now=0.0)
        self.assertEqual(_writes(osc, GYRO_HL_PATH), ["#00ff00ff"])
        self.assertEqual(_writes(osc, GYRO_SH_PATH), ["#00ffffff"])
        self.assertEqual(engine._channels["gyro_highlight"].active_index, 3)
        self.assertEqual(engine._channels["gyro_shadow"].active_index, 4)

    def test_gyro_channel_cc_assignments(self) -> None:
        engine, _, _ = self._build_gyro_engine()
        self.assertEqual(engine._channels["gyro_highlight"].cc, 96)
        self.assertEqual(engine._channels["gyro_shadow"].cc, 97)
        self.assertEqual(engine._channels["gyro_white"].cc, 98)

    def test_gyro_white_cc_98_writes_only_replacewhite(self) -> None:
        engine, osc, _ = self._build_gyro_engine()
        # CC 98 raw value 5 -> palette[5] = blue, written to the L11 replace-white.
        engine.on_midi_in(14, 98, 5, now=0.0)
        self.assertEqual(_writes(osc, GYRO_WHITE_PATH), ["#0000ffff"])
        self.assertEqual(_writes(osc, GYRO_HL_PATH), [])
        self.assertEqual(_writes(osc, GYRO_SH_PATH), [])

    def test_old_gyro_feedback_channel_removed(self) -> None:
        # The combined channel and its CC 95 no longer exist.
        engine, osc, _ = self._build_gyro_engine()
        self.assertNotIn("gyro_feedback", engine._channels)
        engine.on_midi_in(14, 95, 0, now=0.0)  # retired CC -> no-op.
        self.assertEqual(osc.sends, [])


class GlobalChannelTests(unittest.TestCase):
    def test_global_cc_fans_out_to_all_sub_channels(self) -> None:
        engine, osc, _ = _build_engine(
            config_overrides={
                "channels": {
                    "chaser": [
                        {"osc_path": CHASER_COLOR_PATH, "format": "hex_rgba_string"}
                    ],
                    "video_highlight": [],
                    "video_shadow": [],
                    "logo_highlight": [
                        {"osc_path": LOGO_HL_PATH, "format": "hex_rgba_string"}
                    ],
                    "logo_shadow": [],
                }
            }
        )
        # Raw value 9 -> palette[9] = black.
        engine.on_midi_in(14, 45, 9, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#000000ff"])
        self.assertEqual(_writes(osc, LOGO_HL_PATH), ["#000000ff"])

    def test_global_updates_sub_channel_active_indices(self) -> None:
        # Behavior change 2026-05-28: GLOBAL CC now sets each non-excluded
        # sub-channel's active_index, so that a single CC 45 emission is a
        # full equivalent of "select index N on every sub-channel" — the
        # single-CC alternative to TouchOSC's drop-prone ALL COLORS cascade.
        engine, _, _ = _build_engine()
        engine.on_midi_in(14, 40, 3, now=0.0)
        self.assertEqual(engine._channels["chaser"].active_index, 3)
        engine.on_midi_in(14, 45, 0, now=0.1)
        self.assertEqual(engine._channels["chaser"].active_index, 0)
        self.assertEqual(engine._channels["video_highlight"].active_index, 0)
        self.assertEqual(engine._channels["video_shadow"].active_index, 0)
        self.assertEqual(engine._channels["logo_highlight"].active_index, 0)
        self.assertEqual(engine._channels["logo_shadow"].active_index, 0)

    def test_global_does_not_touch_excluded_channels(self) -> None:
        # Replace-black channels (video_black/logo_black/chaser_black) are
        # in GLOBAL_EXCLUDES — they stay at their existing index when GLOBAL
        # fires. Otherwise an ALL COLORS macro would unintentionally drag
        # the replace-black colors along with the rest.
        engine, _, _ = _build_engine()
        # Seed video_black at index 4 directly (real-world it'd come from CC 92).
        engine._channels["video_black"].active_index = 4
        engine.on_midi_in(14, 45, 7, now=0.0)
        self.assertEqual(engine._channels["video_black"].active_index, 4)
        self.assertEqual(engine._channels["chaser"].active_index, 7)

    def test_global_uses_current_palette(self) -> None:
        engine, osc, _ = _build_engine()
        engine._palette[5] = "#deadbeef"
        engine.on_midi_in(14, 45, 5, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#deadbeef"])


class PaletteCcTests(unittest.TestCase):
    def test_palette_cc_updates_slot_and_fans_active_channel(self) -> None:
        engine, osc, _ = _build_engine()
        # Set chaser to slot 2 (yellow).
        engine.on_midi_in(14, 40, 2, now=0.0)
        osc.sends.clear()
        # Slot 2's R/G/B = CCs 6/7/8 on ch14. Make slot 2 fully red.
        engine.on_midi_in(13, 6, 127, now=0.0)
        engine.on_midi_in(13, 7, 0, now=0.0)
        engine.on_midi_in(13, 8, 0, now=0.0)
        # Final state of palette[2] = #ff0000ff. Re-fan happens on each
        # changed-component write that flips the hex.
        chaser_writes = _writes(osc, CHASER_COLOR_PATH)
        self.assertIn("#ff0000ff", chaser_writes)
        self.assertEqual(engine._palette[2], "#ff0000ff")

    def test_palette_cc_does_not_fan_inactive_slot(self) -> None:
        engine, osc, _ = _build_engine()
        # chaser is on slot 0 by default.
        engine.on_midi_in(14, 40, 0, now=0.0)
        osc.sends.clear()
        # Update slot 5's R component. chaser is on slot 0, so no fan.
        engine.on_midi_in(13, 15, 127, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), [])
        # But palette[5] R is now updated.
        self.assertEqual(engine._palette_raw[5][0], 127)

    def test_palette_cc_outside_range_ignored(self) -> None:
        engine, _, _ = _build_engine()
        # CC 30 is past the palette range (10 slots * 3 = 30 CCs => max CC 29).
        engine.on_midi_in(13, 30, 64, now=0.0)
        # No state change; palette stays at defaults.
        self.assertEqual(engine._palette, list(DEFAULT_PALETTE_HEXES))

    def test_palette_cc_wrong_channel_ignored(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(0, 0, 127, now=0.0)
        # Slot 0's R should NOT change to 127.
        # Default red is (127, 0, 0) so we can't tell with slot 0 — use slot 3.
        engine.on_midi_in(0, 9, 0, now=0.0)  # slot 3 R, on wrong channel
        # Slot 3 default = green (0, 127, 0). R should stay 0.
        self.assertEqual(engine._palette_raw[3][0], 0)

    def test_duplicate_cc_does_not_re_fan(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_midi_in(14, 40, 0, now=0.0)  # chaser -> slot 0 (red)
        osc.sends.clear()
        # Same R value as default for slot 0 (127). No change, no re-fan.
        engine.on_midi_in(13, 0, 127, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), [])


class ResyncEmissionTests(unittest.TestCase):
    def test_bind_registry_emits_resync_cc(self) -> None:
        engine, _, midi = _build_engine(bind=False)
        registry = EngineRegistry([engine])
        engine.bind_registry(registry)
        # Resync emits CC 99 on channel index 14 (= MIDI ch15).
        self.assertEqual(midi.events, [("cc", 14, 99, 127)])
        self.assertEqual(engine._resync_emit_count, 1)

    def test_refresh_emits_resync_cc(self) -> None:
        engine, _, midi = _build_engine()
        engine.refresh()
        self.assertEqual(midi.events, [("cc", 14, 99, 127)])
        self.assertEqual(engine._resync_emit_count, 2)  # bind + refresh

    def test_resync_cc_configurable(self) -> None:
        engine, _, midi = _build_engine(
            config_overrides={"resync_cc": 100}, bind=False
        )
        engine.bind_registry(EngineRegistry([engine]))
        self.assertEqual(midi.events, [("cc", 14, 100, 127)])


class ConfigValidationTests(unittest.TestCase):
    def test_wrong_palette_defaults_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            _build_engine(config_overrides={"palette_defaults": ["#000000ff"]})


class CcBaseOffsetTests(unittest.TestCase):
    @unittest.skip(
        "cc_base remap is anticipated for the channel-CC move from 40-45 "
        "back to 50-55 after Pass 3 Part A V-C-B slim-down. Channels are "
        "hardcoded in CHANNEL_CC currently; cc_base only affects palette CCs. "
        "Wire up when the slim-down lands."
    )
    def test_cc_base_override_remaps_channel_ccs(self) -> None:
        engine, osc, _ = _build_engine(config_overrides={"cc_base": 50})
        engine.on_midi_in(14, 50, 0, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#ff0000ff"])
        # CC 40 (the default base) is now a no-op.
        osc.sends.clear()
        engine.on_midi_in(14, 40, 0, now=0.0)
        self.assertEqual(osc.sends, [])

    def test_palette_cc_base_override_remaps_palette_ccs(self) -> None:
        engine, osc, _ = _build_engine(config_overrides={"palette_cc_base": 40})
        engine.on_midi_in(14, 40, 0, now=0.0)
        osc.sends.clear()
        # Slot 0 R is now at CC 40.
        engine.on_midi_in(13, 40, 0, now=0.0)
        engine.on_midi_in(13, 41, 127, now=0.0)
        # Slot 0 became (0, 127, 0) = green-ish. Chaser is on slot 0 so fans.
        chaser_writes = _writes(osc, CHASER_COLOR_PATH)
        self.assertTrue(any(w.startswith("#00ff") for w in chaser_writes))


class PaletteSizeInvariantTests(unittest.TestCase):
    def test_palette_has_10_slots(self) -> None:
        self.assertEqual(PALETTE_SIZE, 10)
        engine, _, _ = _build_engine()
        self.assertEqual(len(engine._palette), 10)
        self.assertEqual(len(engine._palette_raw), 10)


class ChannelLifecycleTests(unittest.TestCase):
    def test_palette_seed_from_config_defaults(self) -> None:
        engine, _, _ = _build_engine()
        self.assertEqual(engine._palette[0], "#ff0000ff")
        self.assertEqual(engine._palette[9], "#000000ff")

    def test_palette_raw_matches_defaults(self) -> None:
        engine, _, _ = _build_engine()
        # palette[0] = #ff0000ff -> raw R=127, G=0, B=0.
        self.assertEqual(engine._palette_raw[0], [127, 0, 0])
        # palette[6] = #7f00ffff -> raw R=round(127*127/255)=63, G=0, B=127.
        self.assertEqual(engine._palette_raw[6][0], 63)
        self.assertEqual(engine._palette_raw[6][1], 0)
        self.assertEqual(engine._palette_raw[6][2], 127)


class FadeTimeTests(unittest.TestCase):
    def test_fade_cc_updates_seconds(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(14, 46, 127, now=0.0)
        self.assertAlmostEqual(engine._fade_seconds, 5.0, places=4)
        engine.on_midi_in(14, 46, 0, now=0.0)
        self.assertEqual(engine._fade_seconds, 0.0)
        engine.on_midi_in(14, 46, 64, now=0.0)
        # 64/127 * 5 ~ 2.52s
        self.assertAlmostEqual(engine._fade_seconds, 64 / 127 * 5, places=4)
        self.assertEqual(engine._fade_cc_count, 3)

    def test_fade_zero_snaps(self) -> None:
        engine, osc, _ = _build_engine()
        # fade=0 by default per _build_engine
        engine.on_midi_in(14, 40, 0, now=0.0)
        engine.on_midi_in(14, 40, 5, now=0.1)
        chaser = _writes(osc, CHASER_COLOR_PATH)
        # Both writes land immediately: red then blue (palette[5]).
        self.assertEqual(chaser, ["#ff0000ff", "#0000ffff"])

    def test_first_write_always_snaps(self) -> None:
        engine, osc, _ = _build_engine(
            config_overrides={"default_fade_seconds": 2.0}
        )
        # Even with fade=2s, the FIRST write to a consumer has no "from" state,
        # so it snaps.
        engine.on_midi_in(14, 40, 4, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#00ffffff"])  # cyan
        self.assertEqual(engine._fades, {})

    def test_fade_schedules_and_completes_on_tick(self) -> None:
        engine, osc, _ = _build_engine(
            config_overrides={"default_fade_seconds": 1.0}
        )
        # Snap first write to red.
        engine.on_midi_in(14, 40, 0, now=0.0)
        osc.sends.clear()
        # Now fade to blue (palette[5]) over 1s. No immediate write.
        engine.on_midi_in(14, 40, 5, now=1.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), [])
        self.assertIn(CHASER_COLOR_PATH, engine._fades)
        # Tick at 50% -> interpolated midpoint.
        engine.tick(now=1.5)
        chaser_mid = _writes(osc, CHASER_COLOR_PATH)
        self.assertEqual(len(chaser_mid), 1)
        self.assertNotIn(chaser_mid[0], ("#ff0000ff", "#0000ffff"))
        # Tick at completion -> final blue, fade removed.
        engine.tick(now=2.0)
        chaser_done = _writes(osc, CHASER_COLOR_PATH)
        self.assertEqual(chaser_done[-1], "#0000ffff")
        self.assertNotIn(CHASER_COLOR_PATH, engine._fades)

    def test_mid_fade_retarget_uses_current_interpolated(self) -> None:
        engine, osc, _ = _build_engine(
            config_overrides={"default_fade_seconds": 1.0}
        )
        engine.on_midi_in(14, 40, 0, now=0.0)  # snap red
        engine.on_midi_in(14, 40, 5, now=1.0)  # start fade red -> blue
        engine.tick(now=1.5)  # midpoint
        midpoint = _writes(osc, CHASER_COLOR_PATH)[-1]
        # Re-target to green (palette[3]) mid-fade.
        engine.on_midi_in(14, 40, 3, now=1.5)
        new_fade = engine._fades[CHASER_COLOR_PATH]
        self.assertEqual(new_fade.from_hex, midpoint)
        self.assertEqual(new_fade.to_hex, "#00ff00ff")
        self.assertEqual(new_fade.t_start, 1.5)

    def test_palette_slot_tweak_fades(self) -> None:
        engine, osc, _ = _build_engine(
            config_overrides={"default_fade_seconds": 1.0}
        )
        # chaser on slot 2 (yellow). Snap first.
        engine.on_midi_in(14, 40, 2, now=0.0)
        osc.sends.clear()
        # Tweak slot 2 R component down to 0 -> still yellow-ish since G+B
        # also matter. Use a real change: set R=0, G=127, B=127 (cyan).
        engine.on_midi_in(13, 6, 0, now=0.5)
        engine.on_midi_in(13, 7, 127, now=0.5)
        engine.on_midi_in(13, 8, 127, now=0.5)
        # No immediate writes -- fade is scheduled.
        self.assertIn(CHASER_COLOR_PATH, engine._fades)
        engine.tick(now=1.5)  # 1s after last CC -> fade complete
        last = _writes(osc, CHASER_COLOR_PATH)[-1]
        # Final hex matches palette[2] after the tweak.
        self.assertEqual(last, engine._palette[2])

    def test_tick_no_op_when_no_fades(self) -> None:
        engine, osc, _ = _build_engine()
        engine.tick(now=5.0)
        self.assertEqual(osc.sends, [])

    def test_resync_re_emits_fade_time_path_works(self) -> None:
        # Resync via MIDI Learn'd CC 99 fires the Wire patch's dashboard
        # Resync trigger; Wire re-emits palette + channel + fade time CCs.
        # The engine has no direct path to fire the Wire patch from here,
        # but we sanity-check the resync emit still happens at bind.
        engine, _, midi = _build_engine(bind=False)
        engine.bind_registry(EngineRegistry([engine]))
        self.assertEqual(midi.events, [("cc", 14, 99, 127)])


if __name__ == "__main__":
    unittest.main()
