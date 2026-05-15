from __future__ import annotations

import ctypes
import json
import tempfile
import unittest
from pathlib import Path

from deck.xinput_send import (
    HidrawDiscoveryError,
    Xi2KeyEvent,
    _hidraw_matches_steam_gamepad,
    build_action_token_index,
    discover_controller_hidraw,
    flush_block,
    load_bindings,
    next_select_timeout,
    set_mask,
    should_emit_event,
)
from protocol.messages import encode_action_event, parse_action_event


_VALVE_HID_ID = "0003:000028DE:00001205"
_USB_BASE = "usb-0000:04:00.4-3"


def _write_uevent(root: Path, hidraw_name: str, hid_id: str, hid_phys: str, modalias: str, hid_name: str = "Valve Software Steam Deck Controller") -> None:
    device_dir = root / hidraw_name / "device"
    device_dir.mkdir(parents=True, exist_ok=True)
    (device_dir / "uevent").write_text(
        f"DRIVER=hid-steam\n"
        f"HID_ID={hid_id}\n"
        f"HID_NAME={hid_name}\n"
        f"HID_PHYS={hid_phys}\n"
        f"HID_UNIQ=\n"
        f"MODALIAS={modalias}\n",
        encoding="utf-8",
    )


class LoadBindingsTests(unittest.TestCase):
    def test_loads_profile_and_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bindings.json"
            path.write_text(
                json.dumps({"profile_name": "default", "bindings": {"14": "BTN_A"}}),
                encoding="utf-8",
            )
            profile_name, bindings = load_bindings(str(path))

        self.assertEqual(profile_name, "default")
        self.assertEqual(bindings, {"14": "BTN_A"})


class BindingAuditTests(unittest.TestCase):
    def test_builds_action_to_sorted_token_index(self) -> None:
        index = build_action_token_index(
            {
                "18": "R2_SOFT",
                "17": "R2_FULL",
                "55": "R4",
                "5": "R4",
                "A": "R4",
            }
        )
        self.assertEqual(index["R2_SOFT"], ["18"])
        self.assertEqual(index["R2_FULL"], ["17"])
        self.assertEqual(index["R4"], ["5", "55", "A"])


class ShouldEmitEventTests(unittest.TestCase):
    def test_emits_first_press_and_release(self) -> None:
        held_keys: set[str] = set()

        self.assertTrue(
            should_emit_event(
                Xi2KeyEvent(keycode="67", state="down"), held_keys
            )
        )
        self.assertEqual(held_keys, {"67"})
        self.assertTrue(
            should_emit_event(
                Xi2KeyEvent(keycode="67", state="up"), held_keys
            )
        )
        self.assertEqual(held_keys, set())

    def test_suppresses_duplicate_press_while_held(self) -> None:
        held_keys = {"67"}

        self.assertFalse(
            should_emit_event(
                Xi2KeyEvent(keycode="67", state="down"), held_keys
            )
        )
        self.assertEqual(held_keys, {"67"})

    def test_suppresses_release_without_matching_hold(self) -> None:
        held_keys: set[str] = set()

        self.assertFalse(
            should_emit_event(
                Xi2KeyEvent(keycode="67", state="up"), held_keys
            )
        )
        self.assertEqual(held_keys, set())

    def test_tracks_multiple_held_keys_independently(self) -> None:
        held_keys: set[str] = set()

        self.assertTrue(
            should_emit_event(
                Xi2KeyEvent(keycode="67", state="down"), held_keys
            )
        )
        self.assertTrue(
            should_emit_event(
                Xi2KeyEvent(keycode="68", state="down"), held_keys
            )
        )
        self.assertEqual(held_keys, {"67", "68"})
        self.assertTrue(
            should_emit_event(
                Xi2KeyEvent(keycode="67", state="up"), held_keys
            )
        )
        self.assertEqual(held_keys, {"68"})


class FlushBlockTests(unittest.TestCase):
    def test_flushes_bound_press(self) -> None:
        parsed, action = flush_block(
            Xi2KeyEvent(keycode="67", state="down"),
            {"67": "BTN_A"},
            set(),
        )

        self.assertEqual(
            parsed, Xi2KeyEvent(keycode="67", state="down")
        )
        self.assertEqual(action, "BTN_A")

    def test_flushes_release_without_needing_trailing_blank_separator(self) -> None:
        held_keys = {"67"}
        parsed, action = flush_block(
            Xi2KeyEvent(keycode="67", state="up"),
            {"67": "BTN_A"},
            held_keys,
        )

        self.assertEqual(
            parsed, Xi2KeyEvent(keycode="67", state="up")
        )
        self.assertEqual(action, "BTN_A")
        self.assertEqual(held_keys, set())


class SetMaskTests(unittest.TestCase):
    def test_sets_bit_for_event_type(self) -> None:
        mask = (ctypes.c_ubyte * 2)()
        set_mask(mask, 13)
        self.assertEqual(mask[1], 0b00100000)


class NextSelectTimeoutTests(unittest.TestCase):
    def test_checks_immediately_when_internal_work_is_pending(self) -> None:
        self.assertEqual(
            next_select_timeout(
                held_keys={"67"},
                block=["pending"],
                next_heartbeat_at=10.0,
                now=9.9,
            ),
            0.0,
        )

    def test_uses_heartbeat_deadline_when_idle_and_holding(self) -> None:
        self.assertEqual(
            next_select_timeout(
                held_keys={"67"},
                block=[],
                next_heartbeat_at=10.0,
                now=9.25,
            ),
            0.75,
        )

    def test_blocks_indefinitely_when_no_keys_are_held(self) -> None:
        self.assertIsNone(
            next_select_timeout(
                held_keys=set(),
                block=[],
                next_heartbeat_at=10.0,
                now=9.25,
            )
        )


class SharedProtocolEncodingTests(unittest.TestCase):
    def test_encoded_event_round_trips(self) -> None:
        payload = encode_action_event(action="BTN_A", state="down", seq=1)
        event = parse_action_event(payload)
        self.assertEqual(event.action, "BTN_A")
        self.assertEqual(event.state, "down")
        self.assertEqual(event.seq, 1)


class HidrawDiscoveryTests(unittest.TestCase):
    def test_canonical_layout_picks_hidraw2(self) -> None:
        # Standard boot: input0=kbd, input1=mouse, input2=gamepad
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_uevent(root, "hidraw0", _VALVE_HID_ID, f"{_USB_BASE}/input0", "hid:b0003g0001v000028DEp00001205")
            _write_uevent(root, "hidraw1", _VALVE_HID_ID, f"{_USB_BASE}/input1", "hid:b0003g0001v000028DEp00001205")
            _write_uevent(root, "hidraw2", _VALVE_HID_ID, f"{_USB_BASE}/input2", "hid:b0003g0103v000028DEp00001205")
            path, _ = discover_controller_hidraw(str(root))
        self.assertEqual(path, "/dev/hidraw2")

    def test_broken_layout_picks_correct_interface(self) -> None:
        # On-site repro: hidraw1 holds /input2 (gamepad), hidraw2 holds /input1 (mouse).
        # Hardcoded /dev/hidraw2 would have hit the mouse interface and EPIPE'd.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_uevent(root, "hidraw0", _VALVE_HID_ID, f"{_USB_BASE}/input0", "hid:b0003g0001v000028DEp00001205")
            _write_uevent(root, "hidraw1", _VALVE_HID_ID, f"{_USB_BASE}/input2", "hid:b0003g0103v000028DEp00001205")
            _write_uevent(root, "hidraw2", _VALVE_HID_ID, f"{_USB_BASE}/input1", "hid:b0003g0001v000028DEp00001205")
            path, uevent = discover_controller_hidraw(str(root))
        self.assertEqual(path, "/dev/hidraw1")
        self.assertTrue(uevent["HID_PHYS"].endswith("/input2"))

    def test_ignores_non_steam_hidraw_devices(self) -> None:
        # Touchscreen + BT keyboard surrounding a swapped controller layout.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_uevent(root, "hidraw0", _VALVE_HID_ID, f"{_USB_BASE}/input0", "hid:b0003g0001v000028DEp00001205")
            _write_uevent(root, "hidraw1", _VALVE_HID_ID, f"{_USB_BASE}/input2", "hid:b0003g0103v000028DEp00001205")
            _write_uevent(root, "hidraw2", _VALVE_HID_ID, f"{_USB_BASE}/input1", "hid:b0003g0001v000028DEp00001205")
            _write_uevent(root, "hidraw3", "0018:00002808:00001015", "i2c-FTS3528:00", "hid:b0018g0004v00002808p00001015", hid_name="FTS3528:00 2808:1015")
            _write_uevent(root, "hidraw4", "0005:0000046D:0000B342", "60:32:3b:4d:bf:b2", "hid:b0005g0001v0000046Dp0000B342", hid_name="Keyboard K380")
            path, _ = discover_controller_hidraw(str(root))
        self.assertEqual(path, "/dev/hidraw1")

    def test_raises_when_no_steam_controller_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_uevent(root, "hidraw0", "0018:00002808:00001015", "i2c-FTS3528:00", "hid:b0018g0004v00002808p00001015", hid_name="touchscreen")
            with self.assertRaises(HidrawDiscoveryError) as ctx:
                discover_controller_hidraw(str(root))
        # Diagnostic should mention what we did see
        self.assertIn("hidraw0", str(ctx.exception))

    def test_match_predicate_rejects_kbd_emulation_interface(self) -> None:
        self.assertFalse(_hidraw_matches_steam_gamepad({
            "HID_ID": _VALVE_HID_ID,
            "HID_PHYS": f"{_USB_BASE}/input0",
            "MODALIAS": "hid:b0003g0001v000028DEp00001205",
        }))

    def test_match_predicate_rejects_mouse_emulation_interface(self) -> None:
        self.assertFalse(_hidraw_matches_steam_gamepad({
            "HID_ID": _VALVE_HID_ID,
            "HID_PHYS": f"{_USB_BASE}/input1",
            "MODALIAS": "hid:b0003g0001v000028DEp00001205",
        }))

    def test_match_predicate_accepts_gamepad_interface(self) -> None:
        self.assertTrue(_hidraw_matches_steam_gamepad({
            "HID_ID": _VALVE_HID_ID,
            "HID_PHYS": f"{_USB_BASE}/input2",
            "MODALIAS": "hid:b0003g0103v000028DEp00001205",
        }))
