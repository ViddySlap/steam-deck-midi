"""Tests for GlobalColorEngine (Pass 2, new)."""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, FakeRestClient, RecordingMidiOut
from windows.engines.global_color import (
    DEFAULT_PALETTE_DEFAULTS,
    PALETTE_SIZE,
    GlobalColorEngine,
)
from windows.engines.registry import EngineRegistry


CHASER_COLOR_PATH = "/composition/layers/10/video/effects/colorbumpcolor/effect/color"
SHOCKWAVE_COLOR_PATH = (
    "/composition/layers/10/video/effects/shockwave/effect/flashcolor"
)
LOGO_HL_PATH = "/composition/video/effects/viddylut/effect/highlightcolor"


def _build_engine(
    *,
    config_overrides: dict | None = None,
    comp: dict | None = None,
) -> tuple[GlobalColorEngine, FakeRestClient, FakeOscClient]:
    cfg: dict = {
        "name": "Global Color",
        "type": "global_color",
        "channel": 14,
        "cc_base": 50,
        "palette_refresh_hz": 1.0,
        "palette_patch_slug": "colorpalette",
        "palette_input_names": [
            "red", "orange", "yellow", "green", "cyan",
            "blue", "purple", "magenta", "white", "black",
        ],
        "palette_defaults": list(DEFAULT_PALETTE_DEFAULTS),
        "channels": {
            "chaser": [
                {
                    "name": "Color Bump COLOR.Color",
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
    rest = FakeRestClient(composition=comp or {"layers": [], "video": {"effects": []}})
    osc = FakeOscClient()
    midi = RecordingMidiOut()
    engine = GlobalColorEngine(
        cfg["name"], cfg, midi, rest_client=rest, osc_client=osc
    )
    registry = EngineRegistry([engine])
    engine.bind_registry(registry)
    return engine, rest, osc


def _writes(osc: FakeOscClient, path: str) -> list:
    return [v for p, v in osc.sends if p == path]


class CcDecodeTests(unittest.TestCase):
    def test_value_zero_maps_to_index_zero(self) -> None:
        self.assertEqual(GlobalColorEngine._cc_to_index(0), 0)

    def test_value_127_maps_to_index_9(self) -> None:
        self.assertEqual(GlobalColorEngine._cc_to_index(127), 9)

    def test_midpoint_rounds_to_nearest(self) -> None:
        # 9 distinct buckets across 0..127. 14/127*9 ≈ 0.99 -> rounds to 1.
        self.assertEqual(GlobalColorEngine._cc_to_index(14), 1)
        # 63/127*9 ≈ 4.46 -> rounds to 4.
        self.assertEqual(GlobalColorEngine._cc_to_index(63), 4)
        # 64/127*9 ≈ 4.53 -> rounds to 5.
        self.assertEqual(GlobalColorEngine._cc_to_index(64), 5)

    def test_clamps_out_of_range(self) -> None:
        self.assertEqual(GlobalColorEngine._cc_to_index(200), 9)
        self.assertEqual(GlobalColorEngine._cc_to_index(-10), 0)


class ChannelFanOutTests(unittest.TestCase):
    def test_chaser_cc_writes_to_both_consumers(self) -> None:
        engine, _, osc = _build_engine()
        osc.sends.clear()
        # CC 50 (chaser), value 0 -> index 0 -> palette[0] = red.
        engine.on_midi_in(14, 50, 0, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#ff0000ff"])
        self.assertEqual(_writes(osc, SHOCKWAVE_COLOR_PATH), ["#ff0000ff"])

    def test_chaser_cc_updates_active_index(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(14, 50, 127, now=0.0)
        self.assertEqual(engine._channels["chaser"].active_index, 9)

    def test_empty_channel_writes_nothing(self) -> None:
        engine, _, osc = _build_engine()
        osc.sends.clear()
        # CC 51 = video_highlight (empty consumers in v1).
        engine.on_midi_in(14, 51, 64, now=0.0)
        self.assertEqual(osc.sends, [])
        # But active_index is still updated for future consumer additions.
        self.assertEqual(engine._channels["video_highlight"].active_index, 5)

    def test_wrong_channel_ignored(self) -> None:
        engine, _, osc = _build_engine()
        osc.sends.clear()
        engine.on_midi_in(0, 50, 64, now=0.0)
        self.assertEqual(osc.sends, [])

    def test_unknown_cc_ignored(self) -> None:
        engine, _, osc = _build_engine()
        osc.sends.clear()
        engine.on_midi_in(14, 99, 64, now=0.0)
        self.assertEqual(osc.sends, [])


class GlobalChannelTests(unittest.TestCase):
    def test_global_cc_fans_out_to_all_sub_channels_consumers(self) -> None:
        engine, _, osc = _build_engine(
            config_overrides={
                "channels": {
                    "chaser": [
                        {
                            "name": "Color Bump COLOR.Color",
                            "osc_path": CHASER_COLOR_PATH,
                            "format": "hex_rgba_string",
                        }
                    ],
                    "video_highlight": [],
                    "video_shadow": [],
                    "logo_highlight": [
                        {
                            "name": "VIDDYLUT.HighlightColor",
                            "osc_path": LOGO_HL_PATH,
                            "format": "hex_rgba_string",
                        }
                    ],
                    "logo_shadow": [],
                }
            }
        )
        osc.sends.clear()
        # CC 55 (global), value 127 -> index 9 -> palette[9] = black.
        engine.on_midi_in(14, 55, 127, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#000000ff"])
        self.assertEqual(_writes(osc, LOGO_HL_PATH), ["#000000ff"])

    def test_global_does_not_update_sub_channel_active_indices(self) -> None:
        engine, _, _ = _build_engine()
        # Set chaser's active index to 3 first.
        engine.on_midi_in(14, 50, 42, now=0.0)  # 42/127*9 ~= 2.97 -> 3
        self.assertEqual(engine._channels["chaser"].active_index, 3)
        # Fire global -- chaser's active_index must NOT change.
        engine.on_midi_in(14, 55, 0, now=0.1)
        self.assertEqual(engine._channels["chaser"].active_index, 3)

    def test_global_uses_current_palette(self) -> None:
        engine, _, osc = _build_engine()
        # Update palette[5] via direct mutation; global CC 55 should fan out
        # palette[5] when value lands on index 5.
        engine._palette[5] = "#deadbeef"
        osc.sends.clear()
        # Value 71 -> 71/127*9 ~= 5.03 -> rounds to 5.
        engine.on_midi_in(14, 55, 71, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#deadbeef"])


class PaletteRefreshTests(unittest.TestCase):
    @staticmethod
    def _palette_comp(slot_overrides: dict[str, str]) -> dict:
        names = [
            "red", "orange", "yellow", "green", "cyan",
            "blue", "purple", "magenta", "white", "black",
        ]
        params = {}
        for idx, name in enumerate(names):
            params[name] = {
                "id": 4000 + idx,
                "value": slot_overrides.get(name, DEFAULT_PALETTE_DEFAULTS[idx]),
            }
        return {
            "layers": [],
            "video": {
                "effects": [
                    {"name": {"value": "COLOR PALETTE"}, "params": params}
                ]
            },
        }

    def test_refresh_pulls_palette_from_comp(self) -> None:
        comp = self._palette_comp({"red": "#aa0000ff"})
        engine, _, _ = _build_engine(comp=comp)
        self.assertEqual(engine._palette[0], "#aa0000ff")

    def test_refresh_only_rewrites_active_channels(self) -> None:
        comp = self._palette_comp({})
        engine, rest, osc = _build_engine(comp=comp)
        # Set chaser active_index to 2 (yellow).
        engine.on_midi_in(14, 50, 28, now=0.0)  # 28/127*9 ~= 1.98 -> 2
        self.assertEqual(engine._channels["chaser"].active_index, 2)
        osc.sends.clear()
        # Change palette[2] (yellow) -- chaser should re-fan.
        rest.set_composition(self._palette_comp({"yellow": "#abcdef12"}))
        engine.tick(now=10.0)  # force refresh
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#abcdef12"])

    def test_refresh_does_not_rewrite_unchanged_slots(self) -> None:
        comp = self._palette_comp({})
        engine, rest, osc = _build_engine(comp=comp)
        engine.on_midi_in(14, 50, 0, now=0.0)  # chaser -> palette[0] (red)
        osc.sends.clear()
        engine.tick(now=10.0)  # refresh; no slot changed
        self.assertEqual(osc.sends, [])

    def test_refresh_skips_non_active_slot_changes(self) -> None:
        comp = self._palette_comp({})
        engine, rest, osc = _build_engine(comp=comp)
        # chaser active = 0 (red).
        engine.on_midi_in(14, 50, 0, now=0.0)
        osc.sends.clear()
        # Change slot 5 (blue) -- chaser is on red, no re-fan.
        rest.set_composition(self._palette_comp({"blue": "#abcdef12"}))
        engine.tick(now=10.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), [])
        # But palette is updated.
        self.assertEqual(engine._palette[5], "#abcdef12")

    def test_refresh_handles_missing_palette_patch(self) -> None:
        engine, rest, _ = _build_engine()  # comp has no COLOR PALETTE
        # Should not raise.
        engine.tick(now=10.0)
        # Palette stays at defaults.
        self.assertEqual(
            engine._palette[0], DEFAULT_PALETTE_DEFAULTS[0]
        )


class ConfigValidationTests(unittest.TestCase):
    def test_wrong_palette_input_names_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            _build_engine(
                config_overrides={"palette_input_names": ["only", "two"]}
            )

    def test_wrong_palette_defaults_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            _build_engine(
                config_overrides={"palette_defaults": ["#000000ff"]}
            )


class CcBaseOffsetTests(unittest.TestCase):
    def test_cc_base_override_remaps_channels(self) -> None:
        engine, _, osc = _build_engine(config_overrides={"cc_base": 60})
        osc.sends.clear()
        # CC 60 should be chaser now.
        engine.on_midi_in(14, 60, 0, now=0.0)
        self.assertEqual(_writes(osc, CHASER_COLOR_PATH), ["#ff0000ff"])
        # CC 50 should be a no-op.
        osc.sends.clear()
        engine.on_midi_in(14, 50, 0, now=0.0)
        self.assertEqual(osc.sends, [])


class PaletteSizeInvariantTests(unittest.TestCase):
    def test_palette_has_10_slots(self) -> None:
        self.assertEqual(PALETTE_SIZE, 10)
        engine, _, _ = _build_engine()
        self.assertEqual(len(engine._palette), 10)


if __name__ == "__main__":
    unittest.main()
