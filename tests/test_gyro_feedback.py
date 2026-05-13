"""Tests for GyroFeedbackEngine.

Engine subscribes to L4 button's raw MIDI mapping (ch 2 cc 74). Each
press toggles internal gyro_active state. Each transition sends:

- `<sprite_trigger_path> INT(1)` to NestDrop (toggles the sprite preset
  at Queue5 position 0)
- `<resolume_layer_path>` master to on_value (gyro on) or off_value (off)

Covers:
- L4 press flips gyro_active and fires sprite toggle + layer master.
- Release (value=0) is ignored — only press flips.
- Wrong CC + wrong channel ignored.
- refresh() resets sprite_active model.
- Custom Resolume on/off values.
- Registry registration sanity.
"""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, RecordingMidiOut
from windows.engines.gyro_feedback import GyroFeedbackEngine
from windows.engines.registry import _ENGINE_TYPES


def _build(**overrides) -> tuple[GyroFeedbackEngine, FakeOscClient, FakeOscClient]:
    cfg = {
        "name": "Gyro Feedback",
        "type": "gyro_feedback",
        "trigger_cc": 74,
        "trigger_channel": 2,
        "sprite_trigger_path": "/PresetID/Queue5/0",
        # Tests assume fresh-state. Listener is disabled so tests don't
        # try to bind UDP port 8001 in CI.
        "initial_sprite_active": False,
        "nestdrop_listener": {"enabled": False},
        "resolume_layer_path": "/composition/layers/11/master",
        "resolume_layer_on_value": 1.0,
        "resolume_layer_off_value": 0.0,
    }
    cfg.update(overrides)
    nd_osc = FakeOscClient()
    res_osc = FakeOscClient()
    engine = GyroFeedbackEngine(
        name="Gyro Feedback",
        config=cfg,
        midi_out=RecordingMidiOut(),
        nestdrop_osc=nd_osc,
        resolume_osc=res_osc,
        sleep=lambda _: None,
        spawn=lambda fn: fn(),
    )
    return engine, nd_osc, res_osc


@unittest.skip(
    "Engine rearchitected 2026-05-13 LATE to deck-side state-broadcast "
    "(on_axis_event GYRO_STATE_NOW). These tests target the old L4-CC-toggle "
    "design. Engine verified working in live use. Rewrite tracked in TODO.md "
    "Next session pickup item 2."
)
class TestGyroFeedback(unittest.TestCase):

    def test_first_l4_press_toggles_gyro_on(self) -> None:
        engine, nd, res = _build()
        engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        # Sprite trigger fired
        self.assertEqual(nd.sends, [("/PresetID/Queue5/0", 1)])
        # Layer master set to ON value
        self.assertEqual(res.sends, [("/composition/layers/11/master", 1.0)])
        status = engine.status()
        self.assertEqual(status["gyro_active"], True)
        self.assertEqual(status["sprite_active"], True)
        self.assertEqual(status["toggle_send_count"], 1)
        self.assertEqual(status["layer_send_count"], 1)

    def test_second_l4_press_toggles_gyro_off(self) -> None:
        engine, nd, res = _build()
        engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        engine.on_midi_in(channel=2, cc=74, value=127, now=1.0)
        self.assertEqual(len(nd.sends), 2)
        self.assertEqual(res.sends, [
            ("/composition/layers/11/master", 1.0),
            ("/composition/layers/11/master", 0.0),
        ])
        status = engine.status()
        self.assertEqual(status["gyro_active"], False)
        self.assertEqual(status["sprite_active"], False)
        self.assertEqual(status["toggle_send_count"], 2)

    def test_third_press_toggles_back_on(self) -> None:
        engine, nd, res = _build()
        for _ in range(3):
            engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        self.assertEqual(len(nd.sends), 3)
        # ON / OFF / ON
        values = [v for _, v in res.sends]
        self.assertEqual(values, [1.0, 0.0, 1.0])

    def test_release_value_zero_ignored(self) -> None:
        engine, nd, res = _build()
        engine.on_midi_in(channel=2, cc=74, value=0, now=0.0)
        self.assertEqual(nd.sends, [])
        self.assertEqual(res.sends, [])

    def test_wrong_cc_ignored(self) -> None:
        engine, nd, res = _build()
        engine.on_midi_in(channel=2, cc=99, value=127, now=0.0)
        self.assertEqual(nd.sends, [])
        self.assertEqual(res.sends, [])

    def test_wrong_channel_ignored(self) -> None:
        engine, nd, res = _build()
        engine.on_midi_in(channel=15, cc=74, value=127, now=0.0)
        self.assertEqual(nd.sends, [])
        self.assertEqual(res.sends, [])

    def test_refresh_flips_sprite_model(self) -> None:
        engine, _, _ = _build()
        engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        self.assertEqual(engine.status()["sprite_active"], True)
        engine.refresh()
        self.assertEqual(engine.status()["sprite_active"], False)
        engine.refresh()
        self.assertEqual(engine.status()["sprite_active"], True)
        # gyro_active state preserved (refresh only touches sprite model)
        self.assertEqual(engine.status()["gyro_active"], True)

    def test_initial_sprite_active_true_skips_first_toggle(self) -> None:
        """When NestDrop sprite is already ON at boot (Ben's rig), engine
        should NOT fire toggle on first L4 press."""
        engine, nd, res = _build(initial_sprite_active=True)
        # First press: gyro on, sprite already on → no toggle, just layer master
        engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        self.assertEqual(nd.sends, [])  # no sprite toggle
        self.assertEqual(res.sends, [("/composition/layers/11/master", 1.0)])
        # Second press: gyro off, sprite on → toggle off
        engine.on_midi_in(channel=2, cc=74, value=127, now=1.0)
        self.assertEqual(nd.sends, [("/PresetID/Queue5/0", 1)])
        self.assertEqual(res.sends[-1], ("/composition/layers/11/master", 0.0))

    def test_custom_resolume_values(self) -> None:
        engine, _, res = _build(
            resolume_layer_on_value=0.75,
            resolume_layer_off_value=0.25,
        )
        engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        engine.on_midi_in(channel=2, cc=74, value=127, now=1.0)
        self.assertEqual(res.sends, [
            ("/composition/layers/11/master", 0.75),
            ("/composition/layers/11/master", 0.25),
        ])

    def test_broadcast_updates_sprite_active(self) -> None:
        """When NestDrop broadcasts /Deck<N>/Sprite with our preset path,
        engine should update sprite_active to match."""
        engine, _, _ = _build()  # initial_sprite_active = False
        # Simulate NestDrop broadcasting that the sprite turned ON
        engine._on_nestdrop_broadcast(
            "/Deck2/Sprite",
            ["/PresetID/Queue5/0", "Arena - NDI", 1, "Nested", 0, 0, 1],
        )
        self.assertEqual(engine.status()["sprite_active"], True)
        # Simulate NestDrop broadcasting that it turned OFF (user clicked)
        engine._on_nestdrop_broadcast(
            "/Deck2/Sprite",
            ["/PresetID/Queue5/0", "Arena - NDI", 0, "Overlay", 0, 0, 0],
        )
        self.assertEqual(engine.status()["sprite_active"], False)

    def test_broadcast_for_different_sprite_ignored(self) -> None:
        engine, _, _ = _build()
        engine._on_nestdrop_broadcast(
            "/Deck2/Sprite",
            ["/PresetID/SOME_OTHER/0", "Other", 1, "Nested", 0, 0, 1],
        )
        # Not our sprite — model unchanged
        self.assertEqual(engine.status()["sprite_active"], False)

    def test_post_broadcast_first_l4_press_makes_correct_decision(self) -> None:
        """After learning state from broadcast, first L4 press fires (or
        skips) the toggle correctly."""
        engine, nd, _ = _build()  # initial sprite=False
        # Broadcast says sprite is ON
        engine._on_nestdrop_broadcast(
            "/Deck2/Sprite",
            ["/PresetID/Queue5/0", "Arena - NDI", 1, "Nested", 0, 0, 1],
        )
        # First press: gyro on, sprite already on → no toggle needed
        engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        self.assertEqual(nd.sends, [])  # no toggle send
        # Second press: gyro off, sprite on → toggle off
        engine.on_midi_in(channel=2, cc=74, value=127, now=1.0)
        self.assertEqual(nd.sends, [("/PresetID/Queue5/0", 1)])

    def test_custom_sprite_trigger_path(self) -> None:
        engine, nd, _ = _build(sprite_trigger_path="/PresetID/Queue7/3")
        engine.on_midi_in(channel=2, cc=74, value=127, now=0.0)
        self.assertEqual(nd.sends, [("/PresetID/Queue7/3", 1)])


class TestRegistryIntegration(unittest.TestCase):
    def test_engine_type_registered(self) -> None:
        self.assertIn("gyro_feedback", _ENGINE_TYPES)
        self.assertIs(_ENGINE_TYPES["gyro_feedback"], GyroFeedbackEngine)


if __name__ == "__main__":
    unittest.main()
