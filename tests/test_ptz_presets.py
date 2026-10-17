"""Camera presets on the face buttons and D-pad (ptz_visca, 2026-10-17).

Tap = recall on release, hold >= hold_seconds = save, confirmed by the
camera's completion reply before the overlay toast says SAVED.
"""

from __future__ import annotations

import socket
import struct
import time
import unittest

from tests.test_ptz_visca import FakeClock, FakeOsc, FakeSender, RecordingMidiOut, _ptz_config
from windows.engines.ptz_visca import PtzViscaEngine
from windows.engines.visca_sender import (
    MEMORY_RECALL,
    MEMORY_SET,
    PtzViscaSender,
    memory_payload,
    parse_reply,
)
from windows.ptz_overlay_host import PtzOverlayHost

CAM1, CAM2, CAM3 = "192.168.0.203", "192.168.0.204", "192.168.0.205"


class PresetSender(FakeSender):
    """FakeSender plus memory commands and a reply queue."""

    def __init__(self) -> None:
        super().__init__()
        self.seq = 0
        self.replies: list[tuple[str, int, str]] = []

    def send_memory_set(self, ip, slot) -> int:
        self.seq += 1
        self.calls.append(("mem_set", ip, slot, self.seq))
        return self.seq

    def send_memory_recall(self, ip, slot) -> int:
        self.seq += 1
        self.calls.append(("mem_recall", ip, slot, self.seq))
        return self.seq

    def poll_replies(self):
        out, self.replies = self.replies, []
        return out


def _groups() -> dict:
    return {
        "left": {"stick_x": "L_STICK_X_AXIS", "stick_y": "L_STICK_Y_AXIS",
                 "zoom_axis": "L_TRIGGER_PRESSURE", "startup_camera": 1},
        "right": {"stick_x": "R_STICK_X_AXIS", "stick_y": "R_STICK_Y_AXIS",
                  "zoom_axis": "R_TRIGGER_PRESSURE", "startup_camera": 2},
    }


def _engine(presets: "dict | None" = None):
    clock = FakeClock(100.0)
    sender = PresetSender()
    cfg = _ptz_config(groups=_groups(),
                      presets=presets if presets is not None else {"enabled": True})
    eng = PtzViscaEngine("PTZ VISCA", cfg, RecordingMidiOut(), clock=clock,
                         sender=sender, osc_client=FakeOsc())
    return eng, sender, clock


def _press(eng, clock, action, seconds):
    eng.on_input_event(action, "down", clock())
    t = 0.0
    while t < seconds - 1e-9:
        step = min(0.016, seconds - t)
        clock.advance(step)
        t += step
        eng.tick(clock())
    eng.on_input_event(action, "up", clock())


def _hold_to_save(eng, clock, action="BTN_A"):
    eng.on_input_event(action, "down", clock())
    clock.advance(2.5)
    eng.tick(clock())


class PresetTapTests(unittest.TestCase):
    def test_tap_recalls_on_release_not_on_press(self) -> None:
        eng, sender, clock = _engine()
        eng.on_input_event("BTN_A", "down", clock())
        self.assertEqual(sender.of("mem_recall"), [])
        clock.advance(0.2)
        eng.on_input_event("BTN_A", "up", clock())
        self.assertEqual([c[1:3] for c in sender.of("mem_recall")], [(CAM2, 100)])
        self.assertEqual(sender.of("mem_set"), [])

    def test_abxy_follow_right_stick_dpad_follow_left(self) -> None:
        eng, sender, clock = _engine()
        for action in ("BTN_A", "BTN_B", "BTN_X", "BTN_Y",
                       "DPAD_UP", "DPAD_RIGHT", "DPAD_DOWN", "DPAD_LEFT"):
            _press(eng, clock, action, 0.1)
        got = [c[1:3] for c in sender.of("mem_recall")]
        self.assertEqual(got, [(CAM2, 100), (CAM2, 101), (CAM2, 102), (CAM2, 103),
                               (CAM1, 104), (CAM1, 105), (CAM1, 106), (CAM1, 107)])

    def test_slots_follow_the_selected_camera(self) -> None:
        eng, sender, clock = _engine()
        eng.on_midi_in(14, 95, 3, clock())  # right stick -> cam 3
        _press(eng, clock, "BTN_Y", 0.1)
        self.assertEqual([c[1:3] for c in sender.of("mem_recall")], [(CAM3, 103)])

    def test_abxy_layer_2_is_the_same_button(self) -> None:
        eng, sender, clock = _engine()
        _press(eng, clock, "BTN_B_LAYER_2", 0.1)
        self.assertEqual([c[1:3] for c in sender.of("mem_recall")], [(CAM2, 101)])

    def test_unrelated_inputs_pass_through(self) -> None:
        eng, sender, clock = _engine()
        _press(eng, clock, "L4", 3.0)
        self.assertEqual(sender.of("mem_recall") + sender.of("mem_set"), [])

    def test_disabled_does_nothing(self) -> None:
        eng, sender, clock = _engine(presets={"enabled": False})
        _press(eng, clock, "BTN_A", 3.0)
        self.assertEqual(sender.of("mem_recall") + sender.of("mem_set"), [])
        self.assertFalse(eng.status()["presets"]["enabled"])

    def test_missing_presets_block_is_off(self) -> None:
        clock = FakeClock(100.0)
        sender = PresetSender()
        eng = PtzViscaEngine("PTZ VISCA", _ptz_config(groups=_groups()), RecordingMidiOut(),
                             clock=clock, sender=sender, osc_client=FakeOsc())
        _press(eng, clock, "BTN_A", 0.1)
        self.assertEqual(sender.of("mem_recall"), [])


class PresetSaveTests(unittest.TestCase):
    def test_hold_saves_once_at_threshold_and_never_recalls(self) -> None:
        eng, sender, clock = _engine()
        eng.on_input_event("BTN_X", "down", clock())
        clock.advance(2.4)
        eng.tick(clock())
        self.assertEqual(sender.of("mem_set"), [])
        clock.advance(0.11)
        eng.tick(clock())
        self.assertEqual([c[1:3] for c in sender.of("mem_set")], [(CAM2, 102)])
        clock.advance(2.0)
        eng.tick(clock())
        eng.on_input_event("BTN_X", "up", clock())
        self.assertEqual(len(sender.of("mem_set")), 1)
        self.assertEqual(sender.of("mem_recall"), [])

    def test_camera_is_fixed_at_press_time(self) -> None:
        eng, sender, clock = _engine()
        eng.on_input_event("DPAD_UP", "down", clock())
        eng.on_midi_in(14, 94, 3, clock())  # left stick switches mid-hold
        clock.advance(2.6)
        eng.tick(clock())
        self.assertEqual([c[1:3] for c in sender.of("mem_set")], [(CAM1, 104)])

    def test_toast_only_after_camera_confirms(self) -> None:
        eng, sender, clock = _engine()
        _hold_to_save(eng, clock)
        self.assertIsNone(eng.status()["presets"]["toast"])
        seq = sender.of("mem_set")[0][3]
        sender.replies = [(CAM2, seq, "ack"), (CAM2, seq, "done")]
        clock.advance(0.02)
        eng.tick(clock())
        toast = eng.status()["presets"]["toast"]
        self.assertEqual((toast["camera"], toast["label"], toast["kind"]), (2, "A", "saved"))
        clock.advance(2.6)
        self.assertIsNone(eng.status()["presets"]["toast"])

    def test_reply_from_another_camera_or_seq_does_not_confirm(self) -> None:
        eng, sender, clock = _engine()
        _hold_to_save(eng, clock)
        seq = sender.of("mem_set")[0][3]
        sender.replies = [(CAM1, seq, "done"), (CAM2, seq + 7, "done")]
        clock.advance(0.02)
        eng.tick(clock())
        self.assertIsNone(eng.status()["presets"]["toast"])

    def test_no_reply_shows_failed(self) -> None:
        eng, sender, clock = _engine()
        _hold_to_save(eng, clock)
        clock.advance(1.6)
        eng.tick(clock())
        self.assertEqual(eng.status()["presets"]["toast"]["kind"], "failed")

    def test_camera_error_shows_failed(self) -> None:
        eng, sender, clock = _engine()
        _hold_to_save(eng, clock)
        sender.replies = [(CAM2, sender.of("mem_set")[0][3], "error")]
        eng.tick(clock())
        self.assertEqual(eng.status()["presets"]["toast"]["kind"], "failed")

    def test_hold_progress_shows_after_a_moment(self) -> None:
        eng, sender, clock = _engine({"enabled": True, "hold_seconds": 2.0})
        eng.on_input_event("BTN_A", "down", clock())
        clock.advance(0.1)
        self.assertEqual(eng.status()["presets"]["holding"], [])
        clock.advance(0.9)
        holding = eng.status()["presets"]["holding"]
        self.assertEqual(len(holding), 1)
        self.assertAlmostEqual(holding[0]["progress"], 0.5)

    def test_deactivate_drops_a_held_press(self) -> None:
        eng, sender, clock = _engine()
        eng.on_input_event("BTN_A", "down", clock())
        eng.set_active(False)
        eng.set_active(True)
        eng.on_input_event("BTN_A", "up", clock())
        self.assertEqual(sender.of("mem_recall"), [])

    def test_custom_slot_base_and_hold(self) -> None:
        eng, sender, clock = _engine({"enabled": True, "slot_base": 20, "hold_seconds": 1.0})
        _press(eng, clock, "DPAD_LEFT", 1.05)
        self.assertEqual([c[1:3] for c in sender.of("mem_set")], [(CAM1, 27)])


class MemoryWireTests(unittest.TestCase):
    def test_payload_bytes(self) -> None:
        self.assertEqual(memory_payload(MEMORY_SET, 100).hex(), "8101043f0164ff")
        self.assertEqual(memory_payload(MEMORY_RECALL, 100).hex(), "8101043f0264ff")

    def test_parse_reply(self) -> None:
        def frame(seq, body):
            return b"\x01\x11" + struct.pack(">HI", len(body), seq) + body

        self.assertEqual(parse_reply(frame(42597, bytes.fromhex("9041ff"))), (42597, "ack"))
        self.assertEqual(parse_reply(frame(9, bytes.fromhex("9051ff"))), (9, "done"))
        self.assertEqual(parse_reply(frame(9, bytes.fromhex("906002ff"))), (9, "error"))
        self.assertIsNone(parse_reply(b"\x02\x01\x00\x01\x00\x00\x00\x00\x01"))

    def test_sender_returns_seq_and_reads_replies(self) -> None:
        cam = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cam.bind(("127.0.0.1", 0))
        cam.settimeout(1.0)
        port = cam.getsockname()[1]
        sender = PtzViscaSender("127.0.0.1", port)
        try:
            seq = sender.send_memory_set("127.0.0.1", 100)
            data, addr = cam.recvfrom(64)
            self.assertEqual(data[8:].hex(), "8101043f0164ff")
            self.assertEqual(struct.unpack(">I", data[4:8])[0], seq)
            body = bytes.fromhex("9051ff")
            cam.sendto(b"\x01\x11" + struct.pack(">HI", len(body), seq) + body, addr)
            replies: list = []
            for _ in range(50):
                replies += sender.poll_replies()
                if replies:
                    break
                time.sleep(0.01)
            self.assertEqual(replies, [("127.0.0.1", seq, "done")])
        finally:
            sender.close()
            cam.close()


class OverlayHostPresetTests(unittest.TestCase):
    def test_host_state_carries_toast_and_holding(self) -> None:
        eng, sender, clock = _engine()

        class Reg:
            engines = [eng]

        host = PtzOverlayHost(Reg())
        self.assertIsNone(host.state()["preset_toast"])
        eng.on_input_event("BTN_A", "down", clock())
        clock.advance(1.0)
        self.assertEqual(host.state()["preset_holding"][0]["label"], "A")
        clock.advance(1.6)
        eng.tick(clock())
        sender.replies = [(CAM2, sender.of("mem_set")[0][3], "done")]
        eng.tick(clock())
        st = host.state()
        self.assertEqual(st["preset_toast"]["kind"], "saved")
        self.assertEqual(st["preset_holding"], [])


if __name__ == "__main__":
    unittest.main()
