"""Listen for X11 XI2 raw key events and send mapped action events over UDP."""

from __future__ import annotations

import argparse
import array
import ctypes
import ctypes.util
import fcntl
import json
import queue
import selectors
import socket
import struct
import sys
import termios
import threading
import time
from dataclasses import dataclass

from protocol.messages import encode_action_event, encode_axis_event, encode_heartbeat_event


HEARTBEAT_INTERVAL_SECONDS = 0.5
AXIS_MIN_INTERVAL = 1.0 / 60.0
HIDRAW_DEVICE = "/dev/hidraw2"
_HIDIOCSFEATURE = (1 << 30) | (65 << 16) | (0x48 << 8) | 0x06

GENERIC_EVENT = 35
XI_RAW_KEY_PRESS = 13
XI_RAW_KEY_RELEASE = 14
SENDER_AUDIT_ACTIONS = (
    "L2_SOFT",
    "L2_FULL",
    "R2_SOFT",
    "R2_FULL",
    "L2_SOFT_LAYER_2",
    "L2_FULL_LAYER_2",
    "R2_SOFT_LAYER_2",
    "R2_FULL_LAYER_2",
    "L4",
    "L5",
    "R4",
    "R5",
)


def _load_library(name: str) -> ctypes.CDLL:
    path = ctypes.util.find_library(name)
    if path is None:
        raise OSError(f"failed to locate shared library: {name}")
    return ctypes.CDLL(path)


_LIB_X11 = _load_library("X11")
_LIB_XI = _load_library("Xi")


class XGenericEventCookie(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("extension", ctypes.c_int),
        ("evtype", ctypes.c_int),
        ("cookie", ctypes.c_uint),
        ("data", ctypes.c_void_p),
    ]


class XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xcookie", XGenericEventCookie),
        ("pad", ctypes.c_long * 24),
    ]


class XIEventMask(ctypes.Structure):
    _fields_ = [
        ("deviceid", ctypes.c_int),
        ("mask_len", ctypes.c_int),
        ("mask", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class XIRawEventHead(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("extension", ctypes.c_int),
        ("evtype", ctypes.c_int),
        ("time", ctypes.c_ulong),
        ("deviceid", ctypes.c_int),
        ("sourceid", ctypes.c_int),
        ("detail", ctypes.c_int),
    ]


_LIB_X11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_LIB_X11.XOpenDisplay.restype = ctypes.c_void_p
_LIB_X11.XCloseDisplay.argtypes = [ctypes.c_void_p]
_LIB_X11.XCloseDisplay.restype = ctypes.c_int
_LIB_X11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
_LIB_X11.XDefaultRootWindow.restype = ctypes.c_ulong
_LIB_X11.XQueryExtension.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
_LIB_X11.XQueryExtension.restype = ctypes.c_int
_LIB_X11.XConnectionNumber.argtypes = [ctypes.c_void_p]
_LIB_X11.XConnectionNumber.restype = ctypes.c_int
_LIB_X11.XPending.argtypes = [ctypes.c_void_p]
_LIB_X11.XPending.restype = ctypes.c_int
_LIB_X11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]
_LIB_X11.XNextEvent.restype = ctypes.c_int
_LIB_X11.XGetEventData.argtypes = [ctypes.c_void_p, ctypes.POINTER(XGenericEventCookie)]
_LIB_X11.XGetEventData.restype = ctypes.c_int
_LIB_X11.XFreeEventData.argtypes = [ctypes.c_void_p, ctypes.POINTER(XGenericEventCookie)]
_LIB_X11.XFreeEventData.restype = None
_LIB_X11.XFlush.argtypes = [ctypes.c_void_p]
_LIB_X11.XFlush.restype = ctypes.c_int

_LIB_XI.XIQueryVersion.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
_LIB_XI.XIQueryVersion.restype = ctypes.c_int
_LIB_XI.XISelectEvents.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.POINTER(XIEventMask),
    ctypes.c_int,
]
_LIB_XI.XISelectEvents.restype = ctypes.c_int


@dataclass(frozen=True)
class Xi2KeyEvent:
    keycode: str
    state: str


class Xi2RawListener:
    def __init__(self, device_id: int) -> None:
        self._device_id = device_id
        self._display = _LIB_X11.XOpenDisplay(None)
        if not self._display:
            raise OSError("failed to open X display")

        self._extension_opcode = ctypes.c_int()
        first_event = ctypes.c_int()
        first_error = ctypes.c_int()
        found = _LIB_X11.XQueryExtension(
            self._display,
            b"XInputExtension",
            ctypes.byref(self._extension_opcode),
            ctypes.byref(first_event),
            ctypes.byref(first_error),
        )
        if found == 0:
            self.close()
            raise OSError("X Input extension is not available")

        major = ctypes.c_int(2)
        minor = ctypes.c_int(0)
        if _LIB_XI.XIQueryVersion(self._display, ctypes.byref(major), ctypes.byref(minor)) != 0:
            self.close()
            raise OSError("XI2 is not available on this display")

        root = _LIB_X11.XDefaultRootWindow(self._display)
        mask_bytes = (ctypes.c_ubyte * 2)()
        set_mask(mask_bytes, XI_RAW_KEY_PRESS)
        set_mask(mask_bytes, XI_RAW_KEY_RELEASE)
        event_mask = XIEventMask(
            deviceid=self._device_id,
            mask_len=len(mask_bytes),
            mask=ctypes.cast(mask_bytes, ctypes.POINTER(ctypes.c_ubyte)),
        )
        if _LIB_XI.XISelectEvents(self._display, root, ctypes.byref(event_mask), 1) != 0:
            self.close()
            raise OSError("failed to select XI2 events")
        _LIB_X11.XFlush(self._display)

    def fileno(self) -> int:
        return _LIB_X11.XConnectionNumber(self._display)

    def read_event(self) -> Xi2KeyEvent | None:
        while _LIB_X11.XPending(self._display) > 0:
            event = XEvent()
            _LIB_X11.XNextEvent(self._display, ctypes.byref(event))
            if event.type != GENERIC_EVENT:
                continue
            if event.xcookie.extension != self._extension_opcode.value:
                continue
            if event.xcookie.evtype not in (XI_RAW_KEY_PRESS, XI_RAW_KEY_RELEASE):
                continue
            if _LIB_X11.XGetEventData(self._display, ctypes.byref(event.xcookie)) == 0:
                continue
            try:
                raw = ctypes.cast(event.xcookie.data, ctypes.POINTER(XIRawEventHead)).contents
                if raw.deviceid != self._device_id:
                    continue
                return Xi2KeyEvent(
                    keycode=str(raw.detail),
                    state="down" if event.xcookie.evtype == XI_RAW_KEY_PRESS else "up",
                )
            finally:
                _LIB_X11.XFreeEventData(self._display, ctypes.byref(event.xcookie))
        return None

    def close(self) -> None:
        if getattr(self, "_display", None):
            _LIB_X11.XCloseDisplay(self._display)
            self._display = None


class TerminalNoEcho:
    def __enter__(self) -> "TerminalNoEcho":
        self._fd: int | None = None
        self._old_attrs = None
        if not sys.stdin.isatty():
            return self
        self._fd = sys.stdin.fileno()
        self._old_attrs = termios.tcgetattr(self._fd)
        new_attrs = termios.tcgetattr(self._fd)
        new_attrs[3] &= ~(termios.ECHO | termios.ICANON)
        termios.tcsetattr(self._fd, termios.TCSADRAIN, new_attrs)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is None or self._old_attrs is None:
            return
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)


@dataclass(frozen=True)
class AxisSample:
    action: str
    value: int


class HidrawAxisReader:
    _STATIC_AXIS_MAP = [
        # (action, byte_offset, center_offset, signed)
        # center_offset = observed raw value at physical rest (calibrated 2026-04-28)
        ("L_TRIGGER_PRESSURE", 44, 0, False),
        ("R_TRIGGER_PRESSURE", 46, 0, False),
        ("L_STICK_X_AXIS", 48, 118, True),
        ("L_STICK_Y_AXIS", 50, 434, True),
        ("R_STICK_X_AXIS", 52, 280, True),
        ("R_STICK_Y_AXIS", 54, -336, True),
    ]
    _GYRO_OFFSETS = [
        # (action, byte_offset) — angular velocity, integrated to position when active
        # offsets confirmed empirically 2026-04-28; velocity is exactly 0 at rest
        ("GYRO_PITCH", 30),
        ("GYRO_YAW", 32),
        ("GYRO_ROLL", 34),
    ]

    def __init__(self, deadzone: int = 1000) -> None:
        self._deadzone = deadzone
        self._queue: queue.Queue[AxisSample] = queue.Queue()
        self._stop = threading.Event()
        self._file: object = None
        self._thread: threading.Thread | None = None
        self._gyro_lock = threading.Lock()
        self._gyro_active = False
        self._gyro_position: dict[str, float] = {}
        self._gyro_prev_pos: dict[str, int] = {}
        self._gyro_last_time: float = 0.0

    def __enter__(self) -> "HidrawAxisReader":
        self._file = open(HIDRAW_DEVICE, "rb+", buffering=0)
        self._send_feature([0x00, 0x81])
        self._send_feature(
            [
                0x00, 0x87, 15,
                7, 6, 0,
                8, 6, 0,
                52, 0xFF, 0xFF,
                53, 0xFF, 0xFF,
                71, 0, 0,
            ]
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._file is not None:
            try:
                self._send_feature([0x00, 0x85])
            except OSError:
                pass
            self._file.close()
            self._file = None
        return False

    def _send_feature(self, payload: list[int]) -> None:
        buf = array.array("B", [0] * 65)
        for i, b in enumerate(payload):
            buf[i] = b
        fcntl.ioctl(self._file, _HIDIOCSFEATURE, buf)

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            try:
                data = self._file.read(64)
            except OSError:
                break
            if len(data) < 64:
                continue
            self._parse_report(data)

    def enable_gyro(self) -> None:
        with self._gyro_lock:
            self._gyro_active = True
            self._gyro_position = {a: 0.0 for a, _ in self._GYRO_OFFSETS}
            self._gyro_prev_pos = {}
            self._gyro_last_time = time.monotonic()

    def disable_gyro(self) -> None:
        with self._gyro_lock:
            self._gyro_active = False
        for action, _ in self._GYRO_OFFSETS:
            try:
                self._queue.put_nowait(AxisSample(action=action, value=0))
            except queue.Full:
                pass

    def _parse_report(self, data: bytes) -> None:
        if data[0] != 0x01 or data[2] != 0x09:
            return
        for action, offset, center, signed in self._STATIC_AXIS_MAP:
            if signed:
                raw = struct.unpack_from("<h", data, offset)[0]
            else:
                raw = struct.unpack_from("<H", data, offset)[0]
            value = raw - center
            if abs(value) > self._deadzone:
                try:
                    self._queue.put_nowait(AxisSample(action=action, value=value))
                except queue.Full:
                    pass

        if data[10] & 0x08:
            for action, offset in (("L_PAD_X_POS", 16), ("L_PAD_Y_POS", 18)):
                raw = struct.unpack_from("<h", data, offset)[0]
                if abs(raw) > self._deadzone:
                    try:
                        self._queue.put_nowait(AxisSample(action=action, value=raw))
                    except queue.Full:
                        pass

        if data[10] & 0x10:
            for action, offset in (("R_PAD_X_POS", 20), ("R_PAD_Y_POS", 22)):
                raw = struct.unpack_from("<h", data, offset)[0]
                if abs(raw) > self._deadzone:
                    try:
                        self._queue.put_nowait(AxisSample(action=action, value=raw))
                    except queue.Full:
                        pass

        with self._gyro_lock:
            if not self._gyro_active:
                return
            now = time.monotonic()
            # cap dt so a delayed first read can't cause a large position jump
            dt = min(now - self._gyro_last_time, 1.0 / 30.0)
            self._gyro_last_time = now
            for action, offset in self._GYRO_OFFSETS:
                velocity = struct.unpack_from("<h", data, offset)[0]
                self._gyro_position[action] += velocity * dt
                pos = max(-32767, min(32767, round(self._gyro_position[action])))
                self._gyro_position[action] = float(pos)
                if pos != self._gyro_prev_pos.get(action, 0):
                    self._gyro_prev_pos[action] = pos
                    try:
                        self._queue.put_nowait(AxisSample(action=action, value=pos))
                    except queue.Full:
                        pass

    def drain(self) -> dict[str, int]:
        latest: dict[str, int] = {}
        while True:
            try:
                sample = self._queue.get_nowait()
                latest[sample.action] = sample.value
            except queue.Empty:
                break
        return latest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Watch XI2 raw key events and send mapped action events"
    )
    parser.add_argument("--device-id", required=True, help="xinput device id")
    parser.add_argument(
        "--bindings",
        required=True,
        help="path to deck_bindings.json containing keycode-to-action bindings",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="receiver address in host:port form, for example 10.10.10.15:45123",
    )
    parser.add_argument(
        "--profile-name",
        default=None,
        help="override the profile_name sent over the network",
    )
    parser.add_argument(
        "--profile-hash",
        default=None,
        help="optional profile hash sent over the network",
    )
    parser.add_argument(
        "--gyro-trigger",
        default="L4",
        help="action ID that toggles gyro position mode on/off (default: L4)",
    )
    return parser


def parse_target(value: str) -> tuple[str, int]:
    host, port_text = value.rsplit(":", 1)
    return host, int(port_text)


def load_bindings(path: str) -> tuple[str | None, dict[str, str]]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    profile_name = raw.get("profile_name")
    bindings = raw.get("bindings")
    if profile_name is not None and not isinstance(profile_name, str):
        raise ValueError("profile_name must be a string when provided")
    if not isinstance(bindings, dict):
        raise ValueError("bindings file must contain an object at 'bindings'")

    validated: dict[str, str] = {}
    for token, action in bindings.items():
        if not isinstance(token, str) or not token:
            raise ValueError("binding tokens must be non-empty strings")
        if not isinstance(action, str) or not action:
            raise ValueError("binding actions must be non-empty strings")
        validated[token] = action
    return profile_name, validated


def build_action_token_index(bindings: dict[str, str]) -> dict[str, list[str]]:
    action_tokens: dict[str, list[str]] = {}
    for token, action in bindings.items():
        action_tokens.setdefault(action, []).append(token)
    for action in action_tokens:
        action_tokens[action].sort(
            key=lambda token: (0, int(token)) if token.isdigit() else (1, token)
        )
    return action_tokens


def print_sender_binding_audit(bindings: dict[str, str]) -> None:
    print("binding audit:")
    action_tokens = build_action_token_index(bindings)
    for action in SENDER_AUDIT_ACTIONS:
        tokens = action_tokens.get(action)
        token_text = ",".join(tokens) if tokens else "(unmapped)"
        print(f"- {action}: {token_text}")


def set_mask(mask: ctypes.Array[ctypes.c_ubyte], event_type: int) -> None:
    mask[event_type >> 3] |= 1 << (event_type & 7)


def should_emit_event(event: Xi2KeyEvent, held_keys: set[str]) -> bool:
    if event.state == "down":
        if event.keycode in held_keys:
            return False
        held_keys.add(event.keycode)
        return True

    if event.keycode not in held_keys:
        return False
    held_keys.remove(event.keycode)
    return True


def flush_block(
    event: Xi2KeyEvent | None,
    bindings: dict[str, str],
    held_keys: set[str],
) -> tuple[Xi2KeyEvent | None, str | None]:
    if event is None:
        return None, None

    action = bindings.get(event.keycode)
    if action is None:
        return None, None

    if not should_emit_event(event, held_keys):
        return None, None

    return event, action


def next_select_timeout(
    *,
    held_keys: set[str],
    block: list[str],
    next_heartbeat_at: float,
    now: float,
) -> float | None:
    if block:
        return 0.0
    if not held_keys:
        return None
    return max(0.0, next_heartbeat_at - now)


def send_action(
    sock: socket.socket,
    target: tuple[str, int],
    *,
    action: str,
    state: str,
    seq: int,
    profile_name: str | None,
    profile_hash: str | None,
) -> None:
    payload = encode_action_event(
        action=action,
        state=state,
        seq=seq,
        profile_name=profile_name,
        profile_hash=profile_hash,
    )
    sock.sendto(payload, target)
    print(f"sent action={action} state={state} seq={seq}")


def send_axis(
    sock: socket.socket,
    target: tuple[str, int],
    *,
    action: str,
    value: int,
    seq: int,
) -> None:
    payload = encode_axis_event(action=action, value=value, seq=seq)
    sock.sendto(payload, target)


def send_heartbeat(
    sock: socket.socket,
    target: tuple[str, int],
    *,
    seq: int,
    profile_name: str | None,
    profile_hash: str | None,
) -> None:
    payload = encode_heartbeat_event(
        seq=seq,
        profile_name=profile_name,
        profile_hash=profile_hash,
    )
    sock.sendto(payload, target)


def run_sender(
    *,
    device_id: str,
    bindings_path: str,
    target: str,
    profile_name: str | None,
    profile_hash: str | None,
    gyro_trigger: str,
) -> int:
    try:
        loaded_profile_name, bindings = load_bindings(bindings_path)
        resolved_target = parse_target(target)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        return 2

    resolved_profile_name = profile_name or loaded_profile_name
    seq = 1
    held_keys: set[str] = set()
    try:
        listener = Xi2RawListener(int(device_id))
    except OSError as exc:
        print(f"Error: failed to start XI2 listener: {exc}")
        return 2
    except ValueError:
        print(f"Error: invalid device id: {device_id}")
        return 2

    print_sender_binding_audit(bindings)
    print(f"watching XI2 raw key events for device {device_id} and sending to {target}")
    print(f"gyro trigger: {gyro_trigger}")

    axis_last_sent: dict[str, float] = {}
    gyro_enabled = False

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        with TerminalNoEcho():
            with HidrawAxisReader() as axis_reader:
                try:
                    selector = selectors.DefaultSelector()
                    selector.register(listener.fileno(), selectors.EVENT_READ)
                    next_heartbeat_at = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS
                    while True:
                        now = time.monotonic()
                        x11_timeout = next_select_timeout(
                            held_keys=held_keys,
                            block=[],
                            next_heartbeat_at=next_heartbeat_at,
                            now=now,
                        )
                        timeout = (
                            AXIS_MIN_INTERVAL
                            if x11_timeout is None
                            else min(x11_timeout, AXIS_MIN_INTERVAL)
                        )
                        events = selector.select(timeout)
                        now = time.monotonic()

                        if not events:
                            if now >= next_heartbeat_at:
                                send_heartbeat(
                                    sock,
                                    resolved_target,
                                    seq=seq,
                                    profile_name=resolved_profile_name,
                                    profile_hash=profile_hash,
                                )
                                seq += 1
                                next_heartbeat_at = now + HEARTBEAT_INTERVAL_SECONDS
                        else:
                            parsed = listener.read_event()
                            while parsed is not None:
                                event, action = flush_block(parsed, bindings, held_keys)
                                if event is not None and action is not None:
                                    if action == gyro_trigger and event.state == "down":
                                        gyro_enabled = not gyro_enabled
                                        if gyro_enabled:
                                            axis_reader.enable_gyro()
                                            print("gyro on")
                                        else:
                                            axis_reader.disable_gyro()
                                            print("gyro off")
                                    send_action(
                                        sock,
                                        resolved_target,
                                        action=action,
                                        state=event.state,
                                        seq=seq,
                                        profile_name=resolved_profile_name,
                                        profile_hash=profile_hash,
                                    )
                                    seq += 1
                                    next_heartbeat_at = now + HEARTBEAT_INTERVAL_SECONDS
                                parsed = listener.read_event()

                        for axis_action, value in axis_reader.drain().items():
                            last_sent = axis_last_sent.get(axis_action, 0.0)
                            if now - last_sent >= AXIS_MIN_INTERVAL:
                                send_axis(
                                    sock,
                                    resolved_target,
                                    action=axis_action,
                                    value=value,
                                    seq=seq,
                                )
                                seq += 1
                                axis_last_sent[axis_action] = now
                                next_heartbeat_at = now + HEARTBEAT_INTERVAL_SECONDS

                    selector.close()
                except KeyboardInterrupt:
                    print("stopping sender")
                finally:
                    listener.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    return run_sender(
        device_id=args.device_id,
        bindings_path=args.bindings,
        target=args.target,
        profile_name=args.profile_name,
        profile_hash=args.profile_hash,
        gyro_trigger=args.gyro_trigger,
    )


if __name__ == "__main__":
    sys.exit(main())
