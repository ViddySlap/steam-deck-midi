"""Regression tests for the gyro layer indicator (TouchOSC gyro light).

The gyro indicator is the layer CC published for the L4 publisher. It was
dead because every publisher started at LAYER_UNKNOWN and
`_toggle_known_layer_state` early-returns on UNKNOWN -- and unlike the ABXY
and bumper publishers, the gyro publisher has no ground-truth action to pull
it out of UNKNOWN (GYRO_FORWARD/GYRO_BACKWARD were dropped from the presets
when analog gyro replaced the digital notes).
"""

from __future__ import annotations

import unittest

from windows.config import ControlChangeMapping, MacroSettings, NoteMapping
from windows.receiver import LAYER_1, LAYER_2, LAYER_UNKNOWN, ActionReceiver


class FakeMidiOut:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, int]] = []

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.calls.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.calls.append(("note_off", channel, note, velocity))

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.calls.append(("cc", channel, control, value))

    def panic(self) -> None:
        self.calls.append(("panic", -1, -1, -1))

    def close(self) -> None:
        return None


# Mirrors the real presets: L4 -> cc 74 ch2, SELECT -> cc 79, START -> cc 78.
def _mappings() -> dict:
    return {
        "L4": ControlChangeMapping(action="L4", kind="cc", channel=2, cc=74),
        "SELECT": ControlChangeMapping(action="SELECT", kind="cc", channel=2, cc=79),
        "START": ControlChangeMapping(action="START", kind="cc", channel=2, cc=78),
        "L1": NoteMapping(action="L1", kind="note", channel=0, note=60),
    }


def _cc_calls(midi: FakeMidiOut, cc: int) -> list[tuple[int, int]]:
    """(channel, value) pairs published for one CC on the layer channels.

    Restricted to channels 0/1 (layer_1_channel / layer_2_channel) because
    the button itself also emits its raw mapping on its own channel -- L4
    is mapped to cc 74 ch2, so an L4 press produces a ch2 CC alongside the
    layer publish. Only the ch0/ch1 pair drives the indicator.
    """
    return [
        (c[1], c[3])
        for c in midi.calls
        if c[0] == "cc" and c[2] == cc and c[1] in (0, 1)
    ]


class GyroLayerIndicatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.midi = FakeMidiOut()
        self.receiver = ActionReceiver(self.midi, _mappings(), timeout_seconds=1.0)
        self.addr = ("10.10.10.5", 45123)
        self.seq = 0

    def _press(self, action: str, now: float) -> None:
        self.seq += 1
        payload = (
            b'{"action":"%s","state":"down","seq":%d}'
            % (action.encode(), self.seq)
        )
        self.receiver.handle_datagram(payload, self.addr, now=now)

    def test_gyro_publisher_is_seeded_not_unknown(self) -> None:
        """The whole bug: an UNKNOWN gyro publisher makes L4 a no-op."""
        self.assertIsNotNone(self.receiver._gyro_layer_publisher)
        self.assertEqual(self.receiver._gyro_layer_publisher.state, LAYER_1)

    def test_startup_publishes_gyro_off_state(self) -> None:
        """Deck boots gyro off, so the indicator must start at layer 1."""
        self.assertEqual(_cc_calls(self.midi, 74), [(0, 127), (1, 0)])

    def test_l4_toggles_the_indicator(self) -> None:
        self.midi.calls.clear()
        self._press("L4", now=1.0)
        self.assertEqual(self.receiver._gyro_layer_publisher.state, LAYER_2)
        self.assertEqual(_cc_calls(self.midi, 74), [(0, 0), (1, 127)])

    def test_l4_toggles_back_off(self) -> None:
        self._press("L4", now=1.0)
        self.midi.calls.clear()
        self._press("L4", now=2.0)
        self.assertEqual(self.receiver._gyro_layer_publisher.state, LAYER_1)
        self.assertEqual(_cc_calls(self.midi, 74), [(0, 127), (1, 0)])

    def test_repeated_toggles_alternate(self) -> None:
        states = []
        for i in range(6):
            self._press("L4", now=float(i + 1))
            states.append(self.receiver._gyro_layer_publisher.state)
        self.assertEqual(
            states, [LAYER_2, LAYER_1, LAYER_2, LAYER_1, LAYER_2, LAYER_1]
        )

    def test_abxy_and_bumper_still_start_unknown(self) -> None:
        """The seed is gyro-only; the others rely on ground truth as before."""
        self.assertEqual(self.receiver._abxy_layer_publisher.state, LAYER_UNKNOWN)
        self.assertEqual(self.receiver._bumper_layer_publisher.state, LAYER_UNKNOWN)


class GyroLayerReloadTests(unittest.TestCase):
    """A preset hot-reload must not kill the indicator again."""

    def setUp(self) -> None:
        self.midi = FakeMidiOut()
        self.receiver = ActionReceiver(self.midi, _mappings(), timeout_seconds=1.0)
        self.addr = ("10.10.10.5", 45123)
        self.seq = 0

    def _press(self, action: str, now: float) -> None:
        self.seq += 1
        payload = (
            b'{"action":"%s","state":"down","seq":%d}'
            % (action.encode(), self.seq)
        )
        self.receiver.handle_datagram(payload, self.addr, now=now)

    def test_reload_never_leaves_gyro_unknown(self) -> None:
        self.receiver.reload_mappings(_mappings(), MacroSettings())
        self.assertNotEqual(
            self.receiver._gyro_layer_publisher.state, LAYER_UNKNOWN
        )

    def test_reload_preserves_gyro_on_state(self) -> None:
        """Hot-swapping a preset must not silently flip the indicator off."""
        self._press("L4", now=1.0)
        self.assertEqual(self.receiver._gyro_layer_publisher.state, LAYER_2)
        self.receiver.reload_mappings(_mappings(), MacroSettings())
        self.assertEqual(self.receiver._gyro_layer_publisher.state, LAYER_2)

    def test_l4_still_toggles_after_reload(self) -> None:
        self.receiver.reload_mappings(_mappings(), MacroSettings())
        self.midi.calls.clear()
        self._press("L4", now=5.0)
        self.assertEqual(self.receiver._gyro_layer_publisher.state, LAYER_2)
        self.assertEqual(_cc_calls(self.midi, 74), [(0, 0), (1, 127)])

    def test_reload_preserves_bumper_layer(self) -> None:
        """A preset swap doesn't move the deck, so tracked layer should hold."""
        self._press("L1", now=1.0)  # ground truth -> layer 1
        self.assertEqual(self.receiver._bumper_layer_publisher.state, LAYER_1)
        self.receiver.reload_mappings(_mappings(), MacroSettings())
        self.assertEqual(self.receiver._bumper_layer_publisher.state, LAYER_1)

    def test_reload_with_l4_unmapped_is_safe(self) -> None:
        stripped = {k: v for k, v in _mappings().items() if k != "L4"}
        self.receiver.reload_mappings(stripped, MacroSettings())
        self.assertIsNone(self.receiver._gyro_layer_publisher)


if __name__ == "__main__":
    unittest.main()
