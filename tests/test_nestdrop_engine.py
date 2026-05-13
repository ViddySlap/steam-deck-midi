"""Tests for NestdropEngine (per-button config + immediate-fire + cooldown).

Covers:

- 4 default buttons: x → Queue1/Deck1, b → Queue2/Deck1,
  lpad_up → Queue3/Deck2, lpad_down → Queue4/Deck2.
- Note routing per button: each button's note list resolves to that button.
- X notes 40+41 (both SteamInput layers) treated as same logical button.
- Immediate-fire on every press (two OSC sends: activate + btSpace).
- Same-button cooldown extended by every press (regression: sustained
  tapping never re-advances).
- Cross-button always fires regardless of cooldown.
- Per-button target_deck routes btSpace to the correct NestDrop deck.
- Registry registration sanity.
"""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, RecordingMidiOut
from windows.engines.nestdrop_engine import (
    DEFAULT_BTSPACE_PATH_TEMPLATE,
    DEFAULT_BUTTONS,
    NestdropEngine,
)


def _build_engine(**overrides) -> tuple[NestdropEngine, FakeOscClient, list[float]]:
    cfg = {
        "name": "NestDrop",
        "type": "nestdrop",
        "channel": 0,
        "buttons": {
            "x":         {"notes": [40, 41], "queue_path": "/Queue/Queue1", "target_deck": 1},
            "b":         {"notes": [38, 39], "queue_path": "/Queue/Queue2", "target_deck": 1},
            "lpad_up":   {"notes": [88],     "queue_path": "/Queue/Queue3", "target_deck": 2, "fade_window_seconds": 0},
            "lpad_down": {"notes": [89],     "queue_path": "/Queue/Queue4", "target_deck": 2, "fade_window_seconds": 0},
        },
        "fade_window_seconds": 1.25,
        "activate_delay_seconds": 0.1,
        "btspace_path_template": "/Controls/Deck{deck}/btSpace",
        "osc": {"host": "127.0.0.1", "port": 8000},
    }
    cfg.update(overrides)
    osc = FakeOscClient()
    sleeps: list[float] = []
    engine = NestdropEngine(
        name="NestDrop",
        config=cfg,
        midi_out=RecordingMidiOut(),
        osc_client=osc,
        sleep=sleeps.append,
        spawn=lambda fn: fn(),
    )
    return engine, osc, sleeps


def _queue_advances(osc: FakeOscClient) -> list[tuple[str, str]]:
    """Pair up (queue_path, btspace_path) advances from the OSC log."""
    pairs = []
    i = 0
    while i < len(osc.sends) - 1:
        addr, _ = osc.sends[i]
        if addr.startswith("/Queue/"):
            btspace_addr = osc.sends[i + 1][0]
            pairs.append((addr, btspace_addr))
            i += 2
        else:
            i += 1
    return pairs


class TestNestdropEngine(unittest.TestCase):

    def test_x_press_fires_queue1_then_deck1_btspace(self) -> None:
        engine, osc, sleeps = _build_engine()
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.0)
        self.assertEqual(len(osc.sends), 2)
        self.assertEqual(osc.sends[0], ("/Queue/Queue1", 1))
        self.assertEqual(osc.sends[1], ("/Controls/Deck1/btSpace", 1))
        self.assertEqual(sleeps, [0.1])

    def test_b_press_fires_queue2_deck1(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=38, velocity=127, now=0.0)
        self.assertEqual(osc.sends, [("/Queue/Queue2", 1), ("/Controls/Deck1/btSpace", 1)])

    def test_lpad_up_fires_queue3_deck2(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=88, velocity=127, now=0.0)
        self.assertEqual(osc.sends, [("/Queue/Queue3", 1), ("/Controls/Deck2/btSpace", 1)])

    def test_lpad_down_fires_queue4_deck2(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=89, velocity=127, now=0.0)
        self.assertEqual(osc.sends, [("/Queue/Queue4", 1), ("/Controls/Deck2/btSpace", 1)])

    def test_lpad_up_no_cooldown_every_press_fires(self) -> None:
        """fade_window_seconds=0 disables the same-button cooldown.

        L_PAD_UP and L_PAD_DOWN want every press to advance — no "pulse same
        preset" behavior, just deterministic step-through.
        """
        engine, osc, _ = _build_engine()
        # 5 rapid lpad_up presses — every one should fire
        for i in range(5):
            engine.on_note_in(channel=0, note=88, velocity=127, now=i * 0.1)
        advances = _queue_advances(osc)
        self.assertEqual(len(advances), 5)
        for path, btspace in advances:
            self.assertEqual(path, "/Queue/Queue3")
            self.assertEqual(btspace, "/Controls/Deck2/btSpace")
        lpad_up = next(b for b in engine.status()["buttons"] if b["button"] == "lpad_up")
        self.assertEqual(lpad_up["press_count"], 5)
        self.assertEqual(lpad_up["advance_count"], 5)
        self.assertEqual(lpad_up["skip_count"], 0)

    def test_lpad_down_no_cooldown(self) -> None:
        engine, osc, _ = _build_engine()
        for i in range(4):
            engine.on_note_in(channel=0, note=89, velocity=127, now=i * 0.05)
        self.assertEqual(len(_queue_advances(osc)), 4)

    def test_x_still_has_cooldown_when_lpad_has_none(self) -> None:
        """Per-button fade_window: lpad_up has 0, x still uses the engine default."""
        engine, osc, _ = _build_engine()
        # X rapid taps — only first fires
        for i in range(4):
            engine.on_note_in(channel=0, note=40, velocity=127, now=i * 0.1)
        x_advances = [s for s in osc.sends if s[0] == "/Queue/Queue1"]
        self.assertEqual(len(x_advances), 1)

    def test_x_notes_on_both_layers_count_as_same_button(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.0)
        engine.on_note_in(channel=0, note=41, velocity=127, now=0.3)
        # Only one advance — second X press is in cooldown
        self.assertEqual(_queue_advances(osc), [("/Queue/Queue1", "/Controls/Deck1/btSpace")])

    def test_same_button_repeat_within_window_skips(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.0)
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.3)
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.8)
        self.assertEqual(len(_queue_advances(osc)), 1)
        x = next(b for b in engine.status()["buttons"] if b["button"] == "x")
        self.assertEqual(x["press_count"], 3)
        self.assertEqual(x["advance_count"], 1)
        self.assertEqual(x["skip_count"], 2)

    def test_sustained_tapping_never_re_advances(self) -> None:
        """Regression: every press extends cooldown — never re-fires same button."""
        engine, osc, _ = _build_engine()
        for i in range(11):
            engine.on_note_in(channel=0, note=40, velocity=127, now=i * 0.5)
        self.assertEqual(len(_queue_advances(osc)), 1)
        x = next(b for b in engine.status()["buttons"] if b["button"] == "x")
        self.assertEqual(x["press_count"], 11)
        self.assertEqual(x["advance_count"], 1)
        self.assertEqual(x["skip_count"], 10)

    def test_pause_after_rapid_taps_allows_next_advance(self) -> None:
        engine, osc, _ = _build_engine()
        for t in (0.0, 0.4, 0.8, 1.2):
            engine.on_note_in(channel=0, note=40, velocity=127, now=t)
        engine.on_note_in(channel=0, note=40, velocity=127, now=2.7)
        self.assertEqual(len(_queue_advances(osc)), 2)

    def test_cross_button_always_fires_4_button_alternation(self) -> None:
        """X→B→lpad_up→lpad_down→X rapidly: every press fires."""
        engine, osc, _ = _build_engine()
        sequence = [
            (40, "x"),
            (38, "b"),
            (88, "lpad_up"),
            (89, "lpad_down"),
            (40, "x"),
        ]
        for i, (note, _label) in enumerate(sequence):
            engine.on_note_in(channel=0, note=note, velocity=127, now=i * 0.1)
        advances = _queue_advances(osc)
        self.assertEqual(
            advances,
            [
                ("/Queue/Queue1", "/Controls/Deck1/btSpace"),
                ("/Queue/Queue2", "/Controls/Deck1/btSpace"),
                ("/Queue/Queue3", "/Controls/Deck2/btSpace"),
                ("/Queue/Queue4", "/Controls/Deck2/btSpace"),
                ("/Queue/Queue1", "/Controls/Deck1/btSpace"),
            ],
        )

    def test_lpad_up_then_lpad_down_is_cross_button(self) -> None:
        """L_PAD_UP and L_PAD_DOWN share Deck 2 but are different buttons."""
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=88, velocity=127, now=0.0)
        engine.on_note_in(channel=0, note=89, velocity=127, now=0.1)
        engine.on_note_in(channel=0, note=88, velocity=127, now=0.2)
        # All 3 fire — alternation between lpad_up and lpad_down on same deck
        queue_paths = [p for p, _ in _queue_advances(osc)]
        self.assertEqual(queue_paths, ["/Queue/Queue3", "/Queue/Queue4", "/Queue/Queue3"])

    def test_cross_button_resets_same_button_cooldown(self) -> None:
        """X X (skip) lpad_up X — the X after lpad_up is fresh."""
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.0)   # X fires
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.3)   # X SKIPPED
        engine.on_note_in(channel=0, note=88, velocity=127, now=0.6)   # lpad_up fires (cross)
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.9)   # X fires (cross from lpad_up)
        queue_paths = [p for p, _ in _queue_advances(osc)]
        self.assertEqual(queue_paths, ["/Queue/Queue1", "/Queue/Queue3", "/Queue/Queue1"])

    def test_note_off_ignored(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=40, velocity=0, now=0.0)
        self.assertEqual(osc.sends, [])

    def test_wrong_channel_ignored(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=15, note=40, velocity=127, now=0.0)
        self.assertEqual(osc.sends, [])

    def test_unmapped_note_ignored(self) -> None:
        engine, osc, _ = _build_engine()
        engine.on_note_in(channel=0, note=99, velocity=127, now=0.0)
        self.assertEqual(osc.sends, [])

    def test_zero_activate_delay_skips_sleep(self) -> None:
        engine, osc, sleeps = _build_engine(activate_delay_seconds=0.0)
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.0)
        self.assertEqual(len(osc.sends), 2)
        self.assertEqual(sleeps, [])

    def test_custom_target_deck_per_button(self) -> None:
        engine, osc, _ = _build_engine(
            buttons={
                "x": {"notes": [40], "queue_path": "/Queue/Queue1", "target_deck": 4},
            },
        )
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.0)
        self.assertEqual(osc.sends[1], ("/Controls/Deck4/btSpace", 1))

    def test_status_reports_last_press_button(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_note_in(channel=0, note=40, velocity=127, now=0.0)
        self.assertEqual(engine.status()["last_press_button"], "x")
        engine.on_note_in(channel=0, note=89, velocity=127, now=0.3)
        self.assertEqual(engine.status()["last_press_button"], "lpad_down")
        # Skipped press still updates tracker
        engine.on_note_in(channel=0, note=89, velocity=127, now=0.5)
        self.assertEqual(engine.status()["last_press_button"], "lpad_down")

    def test_status_includes_all_4_buttons(self) -> None:
        engine, _, _ = _build_engine()
        buttons = {b["button"]: b for b in engine.status()["buttons"]}
        self.assertEqual(set(buttons.keys()), {"x", "b", "lpad_up", "lpad_down"})
        self.assertEqual(buttons["lpad_up"]["target_deck"], 2)
        self.assertEqual(buttons["lpad_up"]["btspace_path"], "/Controls/Deck2/btSpace")
        self.assertEqual(buttons["lpad_up"]["queue_path"], "/Queue/Queue3")


class TestRegistryIntegration(unittest.TestCase):
    def test_engine_type_registered(self) -> None:
        from windows.engines.registry import _ENGINE_TYPES

        self.assertIn("nestdrop", _ENGINE_TYPES)
        self.assertIs(_ENGINE_TYPES["nestdrop"], NestdropEngine)

    def test_default_buttons_constant(self) -> None:
        self.assertEqual(set(DEFAULT_BUTTONS.keys()), {"x", "b", "lpad_up", "lpad_down"})
        self.assertEqual(DEFAULT_BUTTONS["lpad_up"]["queue_path"], "/Queue/Queue3")
        self.assertEqual(DEFAULT_BUTTONS["lpad_up"]["target_deck"], 2)
        self.assertEqual(DEFAULT_BTSPACE_PATH_TEMPLATE, "/Controls/Deck{deck}/btSpace")


if __name__ == "__main__":
    unittest.main()
