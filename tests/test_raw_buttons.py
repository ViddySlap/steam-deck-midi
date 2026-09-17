from __future__ import annotations

import unittest

from protocol.messages import ButtonStateEvent
from windows.raw_buttons import BUTTON_BITS, RawButtonConfig, RawButtonDecoder


EDM_LONG_PRESS = {
    "DPAD_UP_LONG_PRESS",
    "DPAD_DOWN_LONG_PRESS",
    "DPAD_LEFT_LONG_PRESS",
    "DPAD_RIGHT_LONG_PRESS",
    "L_PAD_LEFT_LONG_PRESS",
    "L_PAD_RIGHT_LONG_PRESS",
}


def state(
    *held: str,
    t: int = 0,
    lp: int = 0,
    rp: int = 0,
    lx: int = 0,
    ly: int = 0,
    rx: int = 0,
    lt: int = 0,
    rt: int = 0,
) -> ButtonStateEvent:
    buttons = bytearray(8)
    for name in held:
        offset, mask = BUTTON_BITS[name]
        buttons[offset - 8] |= mask
    return ButtonStateEvent(
        kind="buttons",
        seq=1,
        deck_ms=t,
        buttons=bytes(buttons),
        left_pad_pressure=lp,
        right_pad_pressure=rp,
        left_pad_x=lx,
        left_pad_y=ly,
        right_pad_x=rx,
        right_pad_y=0,
        left_trigger=lt,
        right_trigger=rt,
    )


class Harness:
    def __init__(self, mapped: set[str] | None = None, **config) -> None:
        self.decoder = RawButtonDecoder(RawButtonConfig(**config))
        self.mapped = mapped if mapped is not None else set(EDM_LONG_PRESS)
        self.now = 0.0

    def feed(self, event: ButtonStateEvent) -> list[tuple[str, str]]:
        self.now += 0.01
        return self.decoder.feed(event, self.now, lambda action: action in self.mapped)


class PlainButtonTests(unittest.TestCase):
    def test_press_and_release_emit_once(self) -> None:
        h = Harness()
        self.assertEqual(h.feed(state("L5")), [("L5", "down")])
        self.assertEqual(h.feed(state("L5")), [])
        self.assertEqual(h.feed(state()), [("L5", "up")])

    def test_stick_click_and_touch_are_separate_actions(self) -> None:
        h = Harness()
        self.assertEqual(h.feed(state("LEFT_STICK_TOUCH")), [("LEFT_STICK_TOUCH", "down")])
        self.assertEqual(
            h.feed(state("LEFT_STICK_TOUCH", "L3")), [("LEFT_STICK_CLICK_L3", "down")]
        )
        self.assertEqual(h.feed(state("LEFT_STICK_TOUCH")), [("LEFT_STICK_CLICK_L3", "up")])

    def test_left_menu_is_select_and_right_is_start(self) -> None:
        h = Harness()
        self.assertEqual(h.feed(state("MENU")), [("START", "down")])
        self.assertEqual(h.feed(state("VIEW")), [("START", "up"), ("SELECT", "down")])

    def test_every_bit_decodes_alone(self) -> None:
        for name in BUTTON_BITS:
            with self.subTest(name=name):
                events = Harness(mapped=set()).feed(state(name))
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0][1], "down")


class LayerTests(unittest.TestCase):
    def test_right_menu_button_toggles_abxy_layer(self) -> None:
        h = Harness()
        self.assertEqual(h.feed(state("A")), [("BTN_A", "down")])
        h.feed(state())
        h.feed(state("MENU"))
        h.feed(state())
        self.assertTrue(h.decoder.abxy_layer)
        self.assertEqual(h.feed(state("A")), [("BTN_A_LAYER_2", "down")])
        h.feed(state())
        h.feed(state("MENU"))
        h.feed(state())
        self.assertFalse(h.decoder.abxy_layer)
        self.assertEqual(h.feed(state("B")), [("BTN_B", "down")])

    def test_left_menu_button_toggles_bumpers_and_triggers(self) -> None:
        h = Harness()
        h.feed(state("VIEW"))
        h.feed(state())
        self.assertEqual(
            h.feed(state("L1", "R2_FULL", rt=32000)),
            [("L1_LAYER_2", "down"), ("R2_FULL_LAYER_2", "down"), ("R2_SOFT_LAYER_2", "down")],
        )

    def test_layers_are_independent(self) -> None:
        h = Harness()
        h.feed(state("VIEW"))
        h.feed(state())
        self.assertEqual(h.feed(state("A")), [("BTN_A", "down")])
        h.feed(state())
        self.assertEqual(h.feed(state("L1")), [("L1_LAYER_2", "down")])

    def test_unlayered_inputs_keep_base_action_inside_a_layer(self) -> None:
        h = Harness()
        h.feed(state("MENU"))
        h.feed(state())
        h.feed(state("VIEW"))
        h.feed(state())
        self.assertEqual(
            h.feed(state("L4", "R5", "L3")),
            [("R5", "down"), ("LEFT_STICK_CLICK_L3", "down"), ("L4", "down")],
        )

    def test_action_is_latched_at_press_across_a_layer_flip(self) -> None:
        h = Harness()
        self.assertEqual(h.feed(state("A")), [("BTN_A", "down")])
        self.assertEqual(h.feed(state("A", "MENU")), [("START", "down")])
        self.assertEqual(h.feed(state("MENU")), [("BTN_A", "up")])

    def test_layers_start_off(self) -> None:
        self.assertEqual(RawButtonDecoder().layers, (False, False))


class LongPressTests(unittest.TestCase):
    def test_tap_fires_short_on_release_only(self) -> None:
        h = Harness()
        self.assertEqual(h.feed(state("DPAD_LEFT", t=1000)), [])
        self.assertEqual(h.feed(state("DPAD_LEFT", t=1100)), [])
        self.assertEqual(h.feed(state(t=1130)), [("DPAD_LEFT", "down")])
        # Emitted as a real press, released a moment later, not a zero-length blip.
        self.assertEqual(h.decoder.due_releases(h.now + 0.07), [])
        self.assertEqual(h.decoder.due_releases(h.now + 0.08), [("DPAD_LEFT", "up")])
        self.assertEqual(h.decoder.due_releases(h.now + 1.0), [])

    def test_rapid_taps_each_get_their_own_press(self) -> None:
        h = Harness()
        h.feed(state("DPAD_LEFT", t=0))
        self.assertEqual(h.feed(state(t=60)), [("DPAD_LEFT", "down")])
        h.feed(state("DPAD_LEFT", t=90))
        # The first tap's release is still pending when the second one lands.
        self.assertEqual(
            h.feed(state(t=150)), [("DPAD_LEFT", "up"), ("DPAD_LEFT", "down")]
        )

    def test_due_release_is_emitted_on_the_next_state(self) -> None:
        h = Harness()
        h.feed(state("DPAD_UP", t=0))
        h.feed(state(t=100))
        h.now += 0.2
        self.assertEqual(h.feed(state(t=400)), [("DPAD_UP", "up")])

    def test_hold_fires_long_once_and_never_short(self) -> None:
        h = Harness()
        h.feed(state("DPAD_UP", t=1000))
        self.assertEqual(h.feed(state("DPAD_UP", t=1450)), [])
        self.assertEqual(h.feed(state("DPAD_UP", t=1500)), [("DPAD_UP_LONG_PRESS", "down")])
        self.assertEqual(h.feed(state("DPAD_UP", t=1550)), [])
        self.assertEqual(h.feed(state(t=2000)), [("DPAD_UP_LONG_PRESS", "up")])

    def test_duration_uses_deck_clock_not_arrival(self) -> None:
        # A 3 s receive stall between down and up is still a tap on the Deck.
        h = Harness()
        h.feed(state("DPAD_DOWN", t=5000))
        h.now += 3.0
        self.assertEqual(h.feed(state(t=5120)), [("DPAD_DOWN", "down")])

    def test_no_long_mapping_means_instant_press(self) -> None:
        h = Harness(mapped=set())
        self.assertEqual(h.feed(state("DPAD_RIGHT", t=0)), [("DPAD_RIGHT", "down")])
        self.assertEqual(h.feed(state("DPAD_RIGHT", t=900)), [])
        self.assertEqual(h.feed(state(t=950)), [("DPAD_RIGHT", "up")])

    def test_threshold_is_configurable(self) -> None:
        h = Harness(long_press_ms=300)
        h.feed(state("DPAD_UP", t=0))
        self.assertEqual(h.feed(state("DPAD_UP", t=300)), [("DPAD_UP_LONG_PRESS", "down")])


class TrackpadTests(unittest.TestCase):
    def test_click_is_pressure_with_hysteresis(self) -> None:
        h = Harness(mapped=set())
        self.assertEqual(h.feed(state("DPAD_UP", lp=1478)), [("DPAD_UP", "down")])
        self.assertEqual(h.feed(state(lp=2499, lx=5000)), [("DPAD_UP", "up")])
        self.assertEqual(h.feed(state(lp=3612, lx=5000)), [("L_PAD_RIGHT", "down")])
        self.assertEqual(h.feed(state(lp=1600, lx=5000)), [])
        self.assertEqual(h.feed(state(lp=1499, lx=5000)), [("L_PAD_RIGHT", "up")])

    def test_halves_and_centre_leans(self) -> None:
        for x, expected in ((-32766, "L_PAD_LEFT"), (-1, "L_PAD_LEFT"), (0, "L_PAD_RIGHT"), (32766, "L_PAD_RIGHT")):
            with self.subTest(x=x):
                h = Harness(mapped=set())
                self.assertEqual(h.feed(state(lp=5000, lx=x)), [(expected, "down")])

    def test_side_latched_at_onset(self) -> None:
        h = Harness(mapped=set())
        h.feed(state(lp=5000, lx=-20000))
        self.assertEqual(h.feed(state(lp=5000, lx=20000)), [])
        self.assertEqual(h.feed(state(lp=0, lx=20000)), [("L_PAD_LEFT", "up")])

    def test_pad_long_press(self) -> None:
        h = Harness()
        h.feed(state(lp=5000, lx=20000, t=0))
        self.assertEqual(h.feed(state(lp=5000, lx=20000, t=500)), [("L_PAD_RIGHT_LONG_PRESS", "down")])
        self.assertEqual(h.feed(state(t=600)), [("L_PAD_RIGHT_LONG_PRESS", "up")])

    def test_right_pad_ignored_unless_enabled(self) -> None:
        self.assertEqual(Harness(mapped=set()).feed(state(rp=6000, rx=100)), [])
        enabled = Harness(mapped=set(), right_pad_clicks=True)
        self.assertEqual(enabled.feed(state(rp=6000, rx=100)), [("R_PAD_RIGHT", "down")])


class QamScrollComboTests(unittest.TestCase):
    def test_qam_alone_does_not_scroll(self) -> None:
        h = Harness(mapped=set())
        self.assertEqual(h.feed(state("QAM")), [("QAM", "down")])
        self.assertEqual(h.feed(state()), [("QAM", "up")])

    def test_resting_thumb_zone_picks_direction(self) -> None:
        for (x, y), expected in {
            (20000, 3000): "QAM_SCROLL_RIGHT",
            (-20000, -3000): "QAM_SCROLL_LEFT",
            (2000, 25000): "QAM_SCROLL_UP",
            (-2000, -25000): "QAM_SCROLL_DOWN",
            (400, -100): "QAM_SCROLL_RIGHT",  # near the middle leans
        }.items():
            with self.subTest(x=x, y=y):
                h = Harness(mapped=set())
                self.assertEqual(
                    h.feed(touching("QAM", lx=x, ly=y)), [("QAM", "down"), (expected, "down")]
                )

    def test_follows_thumb_live_and_stops_on_release(self) -> None:
        h = Harness(mapped=set())
        h.feed(touching("QAM", lx=20000))
        self.assertEqual(h.feed(touching("QAM", lx=21000)), [])
        self.assertEqual(
            h.feed(touching("QAM", lx=1000, ly=26000)),
            [("QAM_SCROLL_RIGHT", "up"), ("QAM_SCROLL_UP", "down")],
        )
        self.assertEqual(h.feed(touching(lx=1000, ly=26000)), [("QAM", "up"), ("QAM_SCROLL_UP", "up")])

    def test_lifting_the_thumb_stops_scroll(self) -> None:
        h = Harness(mapped=set())
        h.feed(touching("QAM", lx=-20000))
        self.assertEqual(h.feed(state("QAM", lx=-20000)), [("QAM_SCROLL_LEFT", "up")])

    def test_boundary_hysteresis(self) -> None:
        h = Harness(mapped=set())
        h.feed(touching("QAM", lx=10000, ly=9000))
        # Diagonal wobble and a small drift past centre keep the current direction.
        self.assertEqual(h.feed(touching("QAM", lx=10000, ly=11000)), [])
        self.assertEqual(h.feed(touching("QAM", lx=-1500, ly=0)), [])
        self.assertEqual(
            h.feed(touching("QAM", lx=-2500, ly=0)),
            [("QAM_SCROLL_RIGHT", "up"), ("QAM_SCROLL_LEFT", "down")],
        )

    def test_silence_releases_scroll(self) -> None:
        h = Harness(mapped=set())
        h.feed(touching("QAM", ly=-20000))
        self.assertEqual(
            h.decoder.check_stale(h.now + 1.0), [("QAM", "up"), ("QAM_SCROLL_DOWN", "up")]
        )


def touching(*held: str, lx: int = 0, ly: int = 0) -> ButtonStateEvent:
    """A thumb resting on the left pad: touch bit set, pressure below a click."""
    event = state(*held, lp=300, lx=lx, ly=ly)
    buttons = bytearray(event.buttons)
    buttons[10 - 8] |= 0x08
    return ButtonStateEvent(**{**event.__dict__, "buttons": bytes(buttons)})


class TriggerTests(unittest.TestCase):
    def test_soft_pull_from_analog_full_pull_from_bit(self) -> None:
        h = Harness()
        self.assertEqual(h.feed(state(lt=4999)), [])
        self.assertEqual(h.feed(state(lt=5000)), [("L2_SOFT", "down")])
        self.assertEqual(h.feed(state("L2_FULL", lt=32000)), [("L2_FULL", "down")])
        self.assertEqual(h.feed(state(lt=4500)), [("L2_FULL", "up")])
        self.assertEqual(h.feed(state(lt=3999)), [("L2_SOFT", "up")])


class StaleReleaseTests(unittest.TestCase):
    def test_releases_held_after_silence(self) -> None:
        h = Harness()
        h.feed(state("L5", "DPAD_UP", t=0))
        h.feed(state("L5", "DPAD_UP", "R4", t=600))
        self.assertEqual(h.decoder.check_stale(h.now + 0.4), [])
        self.assertEqual(
            h.decoder.check_stale(h.now + 0.5),
            [("DPAD_UP_LONG_PRESS", "up"), ("L5", "up"), ("R4", "up")],
        )
        self.assertEqual(h.decoder.check_stale(h.now + 5.0), [])

    def test_pending_short_press_is_dropped_not_fired(self) -> None:
        h = Harness()
        h.feed(state("DPAD_LEFT", t=0))
        self.assertEqual(h.decoder.check_stale(h.now + 1.0), [])

    def test_still_held_after_recovery_is_a_new_press(self) -> None:
        h = Harness()
        h.feed(state("L5"))
        h.decoder.check_stale(h.now + 1.0)
        h.now += 1.0
        self.assertEqual(h.feed(state("L5")), [("L5", "down")])

    def test_layers_survive_stale_release(self) -> None:
        h = Harness()
        h.feed(state("MENU"))
        h.decoder.check_stale(h.now + 1.0)
        self.assertTrue(h.decoder.abxy_layer)


if __name__ == "__main__":
    unittest.main()
