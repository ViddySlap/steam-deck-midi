"""Tests for the ptz_visca engine + VISCA-over-IP sender (v1, steps 1-5).

Byte-exact frames are asserted against the recon's verified sequences
(wiki/reference/ptz-cameras.md). Mapping math, zoom + hold-to-invert, and
stop-safety run with fakes (a FakeSender records VISCA calls, a FakeSocket
records wire frames, a FakeClock drives the watchdog). Build + tests pass
without the camera dongle/rig.
"""

from __future__ import annotations

import json
import struct
import unittest

from windows.engines.ptz_visca import (
    DEFAULT_AXIS_CENTERS,
    PtzViscaEngine,
    apply_curve,
)
from windows.engines.registry import EngineRegistry, _ENGINE_TYPES
from windows.engines.visca_sender import (
    PAN_LEFT,
    PAN_RIGHT,
    PT_STOP,
    TILT_DOWN,
    TILT_UP,
    PtzViscaSender,
    build_frame,
    pantilt_payload,
    pantilt_stop_payload,
    zoom_payload,
)
from windows.midi import DryRunMidiOut


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class RecordingMidiOut(DryRunMidiOut):
    def __init__(self) -> None:
        super().__init__(selected_port_name="recording")
        self.events: list[tuple] = []

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.events.append(("cc", channel, control, value))

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.events.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.events.append(("note_off", channel, note, velocity))


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


class FakeSender:
    """Records VISCA calls the engine makes, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.closed = False

    def send_pantilt(self, ip, pan_speed, tilt_speed, pan_dir, tilt_dir) -> None:
        self.calls.append(("pantilt", ip, pan_speed, tilt_speed, pan_dir, tilt_dir))

    def send_zoom(self, ip, direction, speed) -> None:
        self.calls.append(("zoom", ip, direction, speed))

    def send_stop(self, ip) -> None:
        self.calls.append(("stop", ip))

    def send_zoom_stop(self, ip) -> None:
        self.calls.append(("zoom_stop", ip))

    def close(self) -> None:
        self.closed = True

    # convenience filters
    def of(self, kind: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == kind]


class FakeSocket:
    def __init__(self, raise_oserror: bool = False) -> None:
        self.sent: list[tuple[bytes, tuple]] = []
        self._raise = raise_oserror
        self.closed = False

    def sendto(self, data, addr) -> None:
        if self._raise:
            raise OSError("simulated send failure")
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True


CAM1 = "192.168.0.203"


def _ptz_config(**overrides) -> dict:
    cfg = {
        "name": "PTZ VISCA",
        "type": "ptz_visca",
        "enabled": True,
        "camera_nic_ip": "192.168.0.100",
        "visca_port": 52381,
        "cameras": {"1": CAM1, "2": "192.168.0.204", "3": "192.168.0.205"},
        "deadzone": 3500,
        "input_max": 32767,
        "curve": "linear",
        "pan_speed_max": 24,
        "tilt_speed_max": 20,
        "zoom_speed_max": 7,
        "invert_pan": False,
        "invert_tilt": False,
        "redundant_stops": 3,
        "drop_timeout_ms": 250,
        "stream_hz": 60,
        "select_channel": 14,
        "left_select_cc": 94,
        "right_select_cc": 95,
        "groups": {
            "left": {
                "stick_x": "L_STICK_X_AXIS",
                "stick_y": "L_STICK_Y_AXIS",
                "zoom_axis": "L_TRIGGER_PRESSURE",
                # v1 factory ships null; tests exercise the bumper with a real note.
                "zoom_invert_note": 60,
                "startup_camera": 1,
            }
        },
    }
    cfg.update(overrides)
    return cfg


def _engine(clock: FakeClock | None = None, sender: FakeSender | None = None, **overrides):
    clock = clock or FakeClock()
    sender = sender if sender is not None else FakeSender()
    eng = PtzViscaEngine(
        "PTZ VISCA", _ptz_config(**overrides), RecordingMidiOut(), clock=clock, sender=sender
    )
    return eng, sender


# Stick raw values relative to the L-stick calibrated centers (X 118, Y 434).
LX = DEFAULT_AXIS_CENTERS["L_STICK_X_AXIS"]  # 118
LY = DEFAULT_AXIS_CENTERS["L_STICK_Y_AXIS"]  # 434


# ---------------------------------------------------------------------------
# Byte builders + Sony framing
# ---------------------------------------------------------------------------


class ViscaByteTests(unittest.TestCase):
    def test_pantilt_payload_verified_pan_right(self) -> None:
        # Recon's verified pan-right @ speed 6: 81 01 06 01 06 06 02 03 FF
        self.assertEqual(
            pantilt_payload(0x06, 0x06, PAN_RIGHT, PT_STOP),
            bytes.fromhex("81 01 06 01 06 06 02 03 FF".replace(" ", "")),
        )

    def test_pantilt_stop_payload(self) -> None:
        self.assertEqual(pantilt_stop_payload(), bytes.fromhex("8101060106060303FF"))

    def test_zoom_payload_in_out_stop(self) -> None:
        self.assertEqual(zoom_payload("in", 5), bytes.fromhex("8101040725FF"))
        self.assertEqual(zoom_payload("out", 5), bytes.fromhex("8101040735FF"))
        self.assertEqual(zoom_payload("stop", 0), bytes.fromhex("8101040700FF"))

    def test_speed_clamping(self) -> None:
        # pan 99 -> 0x18, 0 -> 0x01 ; tilt 99 -> 0x14 ; zoom 99 -> 7
        self.assertEqual(pantilt_payload(99, 99, PAN_RIGHT, TILT_UP)[4], 0x18)
        self.assertEqual(pantilt_payload(99, 99, PAN_RIGHT, TILT_UP)[5], 0x14)
        self.assertEqual(pantilt_payload(0, 0, PAN_RIGHT, TILT_UP)[4], 0x01)
        self.assertEqual(zoom_payload("in", 99)[4], 0x20 | 7)

    def test_build_frame_header(self) -> None:
        payload = pantilt_stop_payload()
        frame = build_frame(payload, 0)
        self.assertEqual(frame[:2], b"\x01\x00")  # payload-type 0x0100
        self.assertEqual(struct.unpack(">H", frame[2:4])[0], len(payload))  # length
        self.assertEqual(frame[4:8], b"\x00\x00\x00\x00")  # seq 0
        self.assertEqual(frame[8:], payload)


# ---------------------------------------------------------------------------
# Sender (per-camera seq, wrap, fire-and-forget)
# ---------------------------------------------------------------------------


def _seq_of(frame: bytes) -> int:
    return struct.unpack(">I", frame[4:8])[0]


class ViscaSenderTests(unittest.TestCase):
    def test_seq_increments_per_ip_independently(self) -> None:
        sock = FakeSocket()
        s = PtzViscaSender("192.168.0.100", 52381, sock=sock)
        s.send_stop("10.0.0.1")
        s.send_stop("10.0.0.1")
        s.send_stop("10.0.0.2")
        self.assertEqual(s._seq, {"10.0.0.1": 2, "10.0.0.2": 1})
        seqs = [(_seq_of(data), addr[0]) for data, addr in sock.sent]
        self.assertEqual(seqs, [(0, "10.0.0.1"), (1, "10.0.0.1"), (0, "10.0.0.2")])

    def test_seq_wraps_at_uint32(self) -> None:
        s = PtzViscaSender("192.168.0.100", 52381, sock=FakeSocket())
        s._seq["10.0.0.1"] = 0xFFFFFFFF
        s.send_stop("10.0.0.1")
        self.assertEqual(s._seq["10.0.0.1"], 0)

    def test_send_swallows_oserror(self) -> None:
        s = PtzViscaSender("192.168.0.100", 52381, sock=FakeSocket(raise_oserror=True))
        # Must not raise — fire-and-forget never stalls the loop.
        s.send_pantilt("10.0.0.1", 6, 6, PAN_RIGHT, PT_STOP)

    def test_frame_length_matches_payload(self) -> None:
        sock = FakeSocket()
        s = PtzViscaSender("192.168.0.100", 52381, sock=sock)
        s.send_zoom("10.0.0.1", "in", 3)
        data, _ = sock.sent[0]
        self.assertEqual(struct.unpack(">H", data[2:4])[0], len(data) - 8)


# ---------------------------------------------------------------------------
# Skeleton: registration, lifecycle, status
# ---------------------------------------------------------------------------


class SkeletonTests(unittest.TestCase):
    def test_type_name_and_registration(self) -> None:
        self.assertEqual(PtzViscaEngine.type_name, "ptz_visca")
        self.assertIn("ptz_visca", _ENGINE_TYPES)
        self.assertIs(_ENGINE_TYPES["ptz_visca"], PtzViscaEngine)

    def test_constructs_from_minimal_config(self) -> None:
        eng = PtzViscaEngine(
            "PTZ", {"type": "ptz_visca", "groups": {}}, RecordingMidiOut(), sender=FakeSender()
        )
        self.assertTrue(eng.active)  # enabled defaults True

    def test_active_defaults_from_enabled(self) -> None:
        eng, _ = _engine(enabled=False)
        self.assertFalse(eng.active)
        eng2, _ = _engine()
        self.assertTrue(eng2.active)
        eng2.set_active(False)
        self.assertFalse(eng2.active)

    def test_registry_skips_inactive_engine(self) -> None:
        eng, sender = _engine()
        registry = EngineRegistry([eng])
        eng.set_active(False)  # this also fires the toggle-stop burst
        sender.calls.clear()
        registry.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        self.assertEqual(sender.calls, [])  # no dispatch while inactive

    def test_status_shape_is_json_serializable(self) -> None:
        eng, _ = _engine()
        s = eng.status()
        for key in ("name", "type", "active", "camera_nic_ip"):
            self.assertIn(key, s)
        self.assertEqual(s["type"], "ptz_visca")
        self.assertEqual(s["targets"], {"left": CAM1})
        json.dumps(s)  # must not raise

    def test_lifecycle_hooks_no_raise_when_unmatched(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("UNKNOWN_AXIS", 12345, 0.0)
        eng.on_midi_in(0, 1, 127, 0.0)
        eng.on_note_in(0, 99, 127, 0.0)  # note not the bumper
        eng.tick(0.0)
        self.assertEqual(sender.calls, [])

    def test_unbound_sender_when_nic_absent(self) -> None:
        # Bogus (unbindable) NIC IP -> bind raises -> engine degrades to None.
        eng = PtzViscaEngine("PTZ", _ptz_config(camera_nic_ip="203.0.113.255"), RecordingMidiOut())
        self.assertIsNone(eng._sender)
        self.assertEqual(eng.status()["sender"], "unbound")
        # Motion still no-ops cleanly without a sender.
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)


# ---------------------------------------------------------------------------
# Axis -> pan/tilt mapping
# ---------------------------------------------------------------------------


class PanTiltMappingTests(unittest.TestCase):
    def test_axis_to_speed_deadzone_and_range(self) -> None:
        eng, _ = _engine()
        self.assertEqual(eng.axis_to_speed(0, 0, 24), (0, 0))  # raw == center
        self.assertEqual(eng.axis_to_speed(3500, 0, 24), (0, 0))  # at deadzone edge
        speed, sign = eng.axis_to_speed(3501, 0, 24)  # just past
        self.assertEqual((speed, sign), (1, 1))
        self.assertEqual(eng.axis_to_speed(32767, 0, 24), (24, 1))  # full deflection
        self.assertEqual(eng.axis_to_speed(-32767, 0, 24), (24, -1))  # negative

    def test_center_subtraction_uses_calibrated_center(self) -> None:
        eng, sender = _engine()
        # L_STICK_Y raw +434 is neutral (the calibrated center), not 0 -> STOP.
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)  # arm pan so a center is observable
        eng.on_axis_event("L_STICK_X_AXIS", LX, 0.0)  # recenter pan
        self.assertEqual(eng.axis_to_speed(LY, LY, 20), (0, 0))
        # Deflection measured FROM the center: equal offsets either side of 434
        # give equal magnitude but opposite sign (up vs down).
        up_speed, up_sign = eng.axis_to_speed(LY + 10000, LY, 20)
        down_speed, down_sign = eng.axis_to_speed(LY - 10000, LY, 20)
        self.assertEqual(up_speed, down_speed)
        self.assertEqual((up_sign, down_sign), (1, -1))

    def test_curve_function(self) -> None:
        self.assertEqual(apply_curve(0.5, "linear"), 0.5)
        self.assertEqual(apply_curve(0.5, "quadratic"), 0.25)
        self.assertEqual(apply_curve(0.5, "s_curve"), 0.5)  # smoothstep symmetric
        self.assertLess(apply_curve(0.4, "quadratic"), apply_curve(0.4, "linear"))

    def test_curve_config_reduces_speed(self) -> None:
        lin, _ = _engine(curve="linear")
        quad, _ = _engine(curve="quadratic")
        raw = 16384
        self.assertLess(
            quad.axis_to_speed(raw, 0, 24)[0], lin.axis_to_speed(raw, 0, 24)[0]
        )

    def test_direction_nibbles_and_invert(self) -> None:
        eng, _ = _engine()
        self.assertEqual(eng._pan_dir(1), PAN_RIGHT)
        self.assertEqual(eng._pan_dir(-1), PAN_LEFT)
        self.assertEqual(eng._tilt_dir(1), TILT_UP)  # direct tilt
        self.assertEqual(eng._tilt_dir(-1), TILT_DOWN)
        inv, _ = _engine(invert_pan=True, invert_tilt=True)
        self.assertEqual(inv._pan_dir(1), PAN_LEFT)
        self.assertEqual(inv._tilt_dir(1), TILT_DOWN)

    def test_emit_drive_one_axis_uses_stop_nibble_for_other(self) -> None:
        eng, sender = _engine()
        # Push X right hard, Y stays centered -> combined frame, tilt nibble STOP.
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        pantilt = sender.of("pantilt")
        self.assertEqual(len(pantilt), 1)
        _, ip, pan_speed, tilt_speed, pan_dir, tilt_dir = pantilt[0]
        self.assertEqual(ip, CAM1)
        self.assertEqual(pan_dir, PAN_RIGHT)
        self.assertEqual(tilt_dir, PT_STOP)
        self.assertGreaterEqual(pan_speed, 1)

    def test_emit_drive_both_centered_sends_stop_on_edge(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)  # move
        sender.calls.clear()
        eng.on_axis_event("L_STICK_X_AXIS", LX, 0.0)  # back to center
        # Stop-on-center burst (redundant_stops=3).
        self.assertEqual(sender.of("stop"), [("stop", CAM1)] * 3)

    def test_negative_x_pans_left(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX - 30000, 0.0)
        self.assertEqual(sender.of("pantilt")[0][4], PAN_LEFT)

    def test_sole_emitter_no_midi_cc(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        self.assertTrue(sender.of("pantilt"))
        self.assertEqual(eng._midi_out.events, [])  # engine emits VISCA only, no CC


# ---------------------------------------------------------------------------
# Trigger -> zoom (hold-to-invert)
# ---------------------------------------------------------------------------


class ZoomTriggerTests(unittest.TestCase):
    def test_trigger_to_zoom_speed(self) -> None:
        eng, _ = _engine()
        self.assertEqual(eng.trigger_to_zoom_speed(0), 0)
        self.assertEqual(eng.trigger_to_zoom_speed(3500), 0)  # at deadzone
        self.assertEqual(eng.trigger_to_zoom_speed(3501), 1)  # just past
        self.assertEqual(eng.trigger_to_zoom_speed(32767), 7)  # max

    def test_zoom_default_in(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_TRIGGER_PRESSURE", 16000, 0.0)
        z = sender.of("zoom")
        self.assertEqual(len(z), 1)
        self.assertEqual(z[0][2], "in")

    def test_bumper_inverts_to_out_and_clears(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_TRIGGER_PRESSURE", 16000, 0.0)  # zoom IN, speed S
        sender.calls.clear()
        eng.on_note_in(0, 60, 127, 0.0)  # bumper held -> OUT, re-emit
        self.assertEqual(sender.of("zoom")[-1][2], "out")
        sender.calls.clear()
        eng.on_note_in(0, 60, 0, 0.0)  # release -> back to IN
        self.assertEqual(sender.of("zoom")[-1][2], "in")

    def test_held_trigger_flip_immediate(self) -> None:
        eng, sender = _engine()
        # value 18134 -> zoom speed 4
        eng.on_axis_event("L_TRIGGER_PRESSURE", 18134, 0.0)
        self.assertEqual(sender.of("zoom")[-1], ("zoom", CAM1, "in", 4))
        sender.calls.clear()
        eng.on_note_in(0, 60, 127, 0.0)  # bumper -> immediate OUT @ same speed
        self.assertEqual(sender.of("zoom")[-1], ("zoom", CAM1, "out", 4))

    def test_trigger_release_stops_zoom(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_TRIGGER_PRESSURE", 16000, 0.0)  # zooming
        sender.calls.clear()
        eng.on_axis_event("L_TRIGGER_PRESSURE", 0, 0.0)  # released
        self.assertEqual(sender.of("zoom_stop"), [("zoom_stop", CAM1)] * 3)

    def test_null_invert_note_ignores_bumper(self) -> None:
        groups = {
            "left": {
                "stick_x": "L_STICK_X_AXIS",
                "stick_y": "L_STICK_Y_AXIS",
                "zoom_axis": "L_TRIGGER_PRESSURE",
                "zoom_invert_note": None,
                "startup_camera": 1,
            }
        }
        eng, sender = _engine(groups=groups)
        eng.on_axis_event("L_TRIGGER_PRESSURE", 16000, 0.0)
        eng.on_note_in(0, 60, 127, 0.0)  # ignored, no raise
        self.assertTrue(all(c[2] == "in" for c in sender.of("zoom")))

    def test_zoom_and_pantilt_are_separate_calls(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        eng.on_axis_event("L_TRIGGER_PRESSURE", 16000, 0.0)
        self.assertTrue(sender.of("pantilt"))
        self.assertTrue(sender.of("zoom"))


# ---------------------------------------------------------------------------
# Stop-safety (fake clock)
# ---------------------------------------------------------------------------


class StopSafetyTests(unittest.TestCase):
    def test_center_edge_emits_once_then_quiet_then_rearms(self) -> None:
        clock = FakeClock()
        eng, sender = _engine(clock=clock)
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)  # move
        sender.calls.clear()
        eng.on_axis_event("L_STICK_X_AXIS", LX, clock.now)  # center -> 3 stops
        self.assertEqual(len(sender.of("stop")), 3)
        sender.calls.clear()
        eng.on_axis_event("L_STICK_X_AXIS", LX, clock.now)  # stays centered -> quiet
        self.assertEqual(sender.of("stop"), [])
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)  # move again
        sender.calls.clear()
        eng.on_axis_event("L_STICK_X_AXIS", LX, clock.now)  # re-armed -> 3 stops
        self.assertEqual(len(sender.of("stop")), 3)

    def test_watchdog_injects_stop_on_drop(self) -> None:
        clock = FakeClock()
        eng, sender = _engine(clock=clock)
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)  # moving at t=0
        sender.calls.clear()
        clock.advance(0.3)  # 300ms > drop_timeout 250ms
        eng.tick(clock.now)
        self.assertEqual(len(sender.of("stop")), 3)
        self.assertEqual(eng.status()["last_stop_reason"], "drop")

    def test_watchdog_does_not_fire_when_centered(self) -> None:
        clock = FakeClock()
        eng, sender = _engine(clock=clock)
        clock.advance(1.0)
        eng.tick(clock.now)  # nothing moving
        self.assertEqual(sender.calls, [])

    def test_watchdog_clears_and_rearms(self) -> None:
        clock = FakeClock()
        eng, sender = _engine(clock=clock)
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)
        clock.advance(0.3)
        eng.tick(clock.now)  # drop-stop fires
        sender.calls.clear()
        # Fresh axis event restarts motion + re-arms the watchdog.
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)
        self.assertTrue(sender.of("pantilt"))
        sender.calls.clear()
        eng.tick(clock.now)  # not stale yet
        self.assertEqual(sender.of("stop"), [])
        clock.advance(0.3)
        eng.tick(clock.now)  # stale again -> fires
        self.assertEqual(len(sender.of("stop")), 3)

    def test_pantilt_and_zoom_watchdogs_independent(self) -> None:
        clock = FakeClock()
        eng, sender = _engine(clock=clock)
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)  # pan moving
        eng.on_axis_event("L_TRIGGER_PRESSURE", 0, clock.now)  # zoom centered
        sender.calls.clear()
        clock.advance(0.3)
        eng.tick(clock.now)
        self.assertEqual(len(sender.of("stop")), 3)  # pan dropped
        self.assertEqual(sender.of("zoom_stop"), [])  # zoom was never moving

    def test_tick_interval_within_watchdog_window(self) -> None:
        eng, _ = _engine()
        interval = eng.tick_interval_seconds()
        self.assertIsInstance(interval, float)
        self.assertLessEqual(interval, (eng._drop_timeout_ms / 1000.0) / 2.0)

    def test_shutdown_stops_both_surfaces_and_closes(self) -> None:
        eng, sender = _engine()
        eng.shutdown()
        self.assertEqual(sender.of("stop"), [("stop", CAM1)] * 3)
        self.assertEqual(sender.of("zoom_stop"), [("zoom_stop", CAM1)] * 3)
        self.assertTrue(sender.closed)

    def test_toggle_off_stops_all_groups(self) -> None:
        eng, sender = _engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)  # moving
        sender.calls.clear()
        eng.set_active(False)  # active -> inactive
        self.assertEqual(sender.of("stop"), [("stop", CAM1)] * 3)
        self.assertEqual(sender.of("zoom_stop"), [("zoom_stop", CAM1)] * 3)


# ---------------------------------------------------------------------------
# Global movement-speed control (CC-scaled ceilings) — spec ptz-global-speed
# ---------------------------------------------------------------------------

# Speed-control CC contract (channel 14, MIDI ch15 convention).
SPEED_CH = 14
PT_SPEED_CC = 92
ZOOM_SPEED_CC = 93
FULL_X = LX + 32767  # full right deflection -> t == 1.0 -> ceiling speed


def _pan_speed_at_full_deflection(eng, sender) -> int:
    sender.calls.clear()
    eng.on_axis_event("L_STICK_X_AXIS", FULL_X, 0.0)
    return sender.of("pantilt")[-1][2]  # (pantilt, ip, pan_speed, ...)


class GlobalSpeedTests(unittest.TestCase):
    def test_cc127_is_full_ceiling_identical_to_v1(self) -> None:
        eng, sender = _engine()
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 127, 0.0)
        self.assertEqual(eng._eff_pan_max(), 24)
        self.assertEqual(eng._eff_tilt_max(), 20)
        self.assertEqual(_pan_speed_at_full_deflection(eng, sender), 24)

    def test_cc0_collapses_to_floor_crawl(self) -> None:
        eng, sender = _engine()
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 0, 0.0)
        self.assertEqual(eng._eff_pan_max(), 1)  # default floor
        self.assertEqual(eng._eff_tilt_max(), 1)
        # Full deflection now maps to speed 1 (the slowest VISCA move).
        self.assertEqual(_pan_speed_at_full_deflection(eng, sender), 1)

    def test_cc0_does_not_disable_stop_on_center(self) -> None:
        eng, sender = _engine()
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 0, 0.0)
        eng.on_axis_event("L_STICK_X_AXIS", FULL_X, 0.0)  # crawl move
        sender.calls.clear()
        eng.on_axis_event("L_STICK_X_AXIS", LX, 0.0)  # deadzone -> still STOPs
        self.assertEqual(sender.of("stop"), [("stop", CAM1)] * 3)

    def test_cc0_does_not_disable_drop_watchdog(self) -> None:
        clock = FakeClock()
        eng, sender = _engine(clock=clock)
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 0, clock.now)
        eng.on_axis_event("L_STICK_X_AXIS", FULL_X, clock.now)  # crawl move
        sender.calls.clear()
        clock.advance(0.3)  # > drop_timeout
        eng.tick(clock.now)
        self.assertEqual(len(sender.of("stop")), 3)
        self.assertEqual(eng.status()["last_stop_reason"], "drop")

    def test_cc64_is_between_floor_and_max(self) -> None:
        eng, sender = _engine()
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 64, 0.0)
        eff = eng._eff_pan_max()
        self.assertGreater(eff, 1)
        self.assertLess(eff, 24)
        # Full deflection at mid-scale maps proportionally lower than at CC 127.
        mid = _pan_speed_at_full_deflection(eng, sender)
        self.assertEqual(mid, eff)
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 127, 0.0)
        full = _pan_speed_at_full_deflection(eng, sender)
        self.assertLess(mid, full)

    def test_pan_tilt_and_zoom_scales_independent(self) -> None:
        eng, sender = _engine()
        # Scale pan/tilt down; zoom must stay at full ceiling.
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 0, 0.0)
        self.assertEqual(eng._eff_zoom_max(), 7)
        self.assertEqual(eng.trigger_to_zoom_speed(32767), 7)
        # Now scale zoom down; pan/tilt scale unchanged (still floor from above).
        eng.on_midi_in(SPEED_CH, ZOOM_SPEED_CC, 0, 0.0)
        self.assertEqual(eng._eff_zoom_max(), 1)
        self.assertEqual(eng.trigger_to_zoom_speed(32767), 1)
        self.assertEqual(eng._eff_pan_max(), 1)

    def test_zoom_cc_scales_only_zoom(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(SPEED_CH, ZOOM_SPEED_CC, 0, 0.0)
        self.assertEqual(eng._eff_zoom_max(), 1)
        self.assertEqual(eng._eff_pan_max(), 24)  # pan/tilt untouched
        self.assertEqual(eng._eff_tilt_max(), 20)

    def test_wrong_channel_ignored(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(0, PT_SPEED_CC, 0, 0.0)  # right CC, wrong channel
        self.assertEqual(eng._pan_tilt_scale, 1.0)
        self.assertEqual(eng._eff_pan_max(), 24)

    def test_wrong_cc_ignored(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(SPEED_CH, 50, 0, 0.0)  # right channel, unrelated CC
        self.assertEqual(eng._pan_tilt_scale, 1.0)
        self.assertEqual(eng._zoom_scale, 1.0)

    def test_default_no_cc_behaves_like_v1(self) -> None:
        eng, sender = _engine()
        self.assertEqual(eng._eff_pan_max(), 24)
        self.assertEqual(eng._eff_tilt_max(), 20)
        self.assertEqual(eng._eff_zoom_max(), 7)
        self.assertEqual(_pan_speed_at_full_deflection(eng, sender), 24)

    def test_scale_persists_across_many_axis_events(self) -> None:
        eng, sender = _engine()
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 0, 0.0)
        for _ in range(50):
            eng.on_axis_event("L_STICK_X_AXIS", FULL_X, 0.0)
            eng.on_axis_event("L_STICK_X_AXIS", LX, 0.0)
        self.assertEqual(eng._pan_tilt_scale, 0.0)
        self.assertEqual(_pan_speed_at_full_deflection(eng, sender), 1)

    def test_floor_config_raises_minimum(self) -> None:
        # A venue can set a higher floor so CC 0 still gives a usable speed.
        eng, sender = _engine(pan_speed_floor=4, tilt_speed_floor=4)
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 0, 0.0)
        self.assertEqual(eng._eff_pan_max(), 4)
        self.assertEqual(_pan_speed_at_full_deflection(eng, sender), 4)

    def test_status_reports_scales_and_effective_max(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(SPEED_CH, PT_SPEED_CC, 0, 0.0)
        eng.on_midi_in(SPEED_CH, ZOOM_SPEED_CC, 127, 0.0)
        s = eng.status()
        self.assertEqual(s["pan_tilt_speed_scale"], 0.0)
        self.assertEqual(s["zoom_speed_scale"], 1.0)
        self.assertEqual(s["effective_speed_max"], {"pan": 1, "tilt": 1, "zoom": 7})
        json.dumps(s)  # must not raise


# ---------------------------------------------------------------------------
# Two independent control groups (LEFT / RIGHT) — spec ptz-two-control-groups
# ---------------------------------------------------------------------------

CAM2 = "192.168.0.204"
RX = DEFAULT_AXIS_CENTERS["R_STICK_X_AXIS"]  # 280
RY = DEFAULT_AXIS_CENTERS["R_STICK_Y_AXIS"]  # -336

_TWO_GROUPS = {
    "left": {
        "stick_x": "L_STICK_X_AXIS",
        "stick_y": "L_STICK_Y_AXIS",
        "zoom_axis": "L_TRIGGER_PRESSURE",
        "zoom_invert_note": 60,
        "startup_camera": 1,
    },
    "right": {
        "stick_x": "R_STICK_X_AXIS",
        "stick_y": "R_STICK_Y_AXIS",
        "zoom_axis": "R_TRIGGER_PRESSURE",
        "zoom_invert_note": 61,
        "startup_camera": 2,
    },
}


def _two_group_engine(clock: FakeClock | None = None):
    return _engine(clock=clock, groups=_TWO_GROUPS)


class TwoControlGroupTests(unittest.TestCase):
    def test_startup_targets_left_cam1_right_cam2(self) -> None:
        eng, _ = _two_group_engine()
        self.assertEqual(eng.status()["targets"], {"left": CAM1, "right": CAM2})

    def test_action_routes_to_correct_group(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        eng.on_axis_event("R_STICK_X_AXIS", RX + 30000, 0.0)
        ips = [c[1] for c in sender.of("pantilt")]
        self.assertIn(CAM1, ips)  # left -> .203
        self.assertIn(CAM2, ips)  # right -> .204

    def test_unrelated_action_ignored(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_axis_event("GYRO_STATE_NOW", 12345, 0.0)
        self.assertEqual(sender.calls, [])

    def test_simultaneous_two_cameras_in_one_drain(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        eng.on_axis_event("R_STICK_X_AXIS", RX + 30000, 0.0)
        pantilt = sender.of("pantilt")
        ips = {c[1] for c in pantilt}
        self.assertEqual(ips, {CAM1, CAM2})  # two independent streams

    def test_right_stick_uses_its_own_center(self) -> None:
        # R_STICK_Y raw == its calibrated center (-336) -> magnitude 0 -> STOP.
        eng, sender = _two_group_engine()
        eng.on_axis_event("R_STICK_Y_AXIS", RY + 20000, 0.0)  # move .204 tilt
        self.assertEqual(sender.of("pantilt")[-1][1], CAM2)
        sender.calls.clear()
        eng.on_axis_event("R_STICK_Y_AXIS", RY, 0.0)  # raw -336 == center -> STOP
        self.assertEqual(sender.of("stop"), [("stop", CAM2)] * 3)

    def test_per_group_drop_watchdog_independent(self) -> None:
        clock = FakeClock()
        eng, sender = _two_group_engine(clock=clock)
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)  # left @ t=0
        eng.on_axis_event("R_STICK_X_AXIS", RX + 30000, clock.now)  # right @ t=0
        clock.advance(0.1)
        eng.on_axis_event("R_STICK_X_AXIS", RX + 30000, clock.now)  # refresh right @ t=0.1
        sender.calls.clear()
        clock.advance(0.2)  # t=0.3: left stale 0.3 (>250ms), right stale 0.2 (<250ms)
        eng.tick(clock.now)
        stops = sender.of("stop")
        self.assertTrue(stops)
        self.assertTrue(all(c == ("stop", CAM1) for c in stops))  # only left dropped
        self.assertTrue(eng._moving["right"]["pantilt"])  # right still moving

    def test_right_bumper_inverts_only_right_zoom(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_axis_event("L_TRIGGER_PRESSURE", 16000, 0.0)  # left zoom IN
        eng.on_axis_event("R_TRIGGER_PRESSURE", 16000, 0.0)  # right zoom IN
        sender.calls.clear()
        eng.on_note_in(0, 61, 127, 0.0)  # RIGHT bumper -> invert right only
        self.assertTrue(eng._zoom_inverted["right"])
        self.assertFalse(eng._zoom_inverted["left"])
        # The re-emit on the right group goes OUT, to .204.
        self.assertEqual(sender.of("zoom")[-1], ("zoom", CAM2, "out", sender.of("zoom")[-1][3]))


# ---------------------------------------------------------------------------
# Engine camera-select + stop-then-retarget — spec ptz-engine-camera-select
# ---------------------------------------------------------------------------

CAM3 = "192.168.0.205"
SELECT_CH = 14
LEFT_SELECT_CC = 94
RIGHT_SELECT_CC = 95


class CameraSelectTests(unittest.TestCase):
    def test_startup_selected_index(self) -> None:
        eng, _ = _two_group_engine()
        self.assertEqual(eng.status()["selected"], {"left": 1, "right": 2})

    def test_decode_left_and_right_select(self) -> None:
        eng, _ = _two_group_engine()
        eng.on_midi_in(SELECT_CH, LEFT_SELECT_CC, 2, 0.0)
        self.assertEqual(eng._targets["left"], CAM2)
        eng.on_midi_in(SELECT_CH, RIGHT_SELECT_CC, 3, 0.0)
        self.assertEqual(eng._targets["right"], CAM3)
        self.assertEqual(eng.status()["selected"], {"left": 2, "right": 3})

    def test_wrong_channel_and_cc_ignored(self) -> None:
        eng, _ = _two_group_engine()
        eng.on_midi_in(0, LEFT_SELECT_CC, 2, 0.0)  # wrong channel
        eng.on_midi_in(SELECT_CH, 50, 2, 0.0)  # unrelated CC
        self.assertEqual(eng._targets["left"], CAM1)  # unchanged

    def test_out_of_range_index_ignored(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_midi_in(SELECT_CH, LEFT_SELECT_CC, 0, 0.0)  # 0 = unset
        eng.on_midi_in(SELECT_CH, LEFT_SELECT_CC, 9, 0.0)  # no such camera
        self.assertEqual(eng._targets["left"], CAM1)
        self.assertEqual(sender.calls, [])  # nothing sent

    def test_stop_then_retarget(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)  # left driving .203
        sender.calls.clear()
        eng.on_midi_in(SELECT_CH, LEFT_SELECT_CC, 2, 0.0)  # switch to .204
        # STOPs go to the OUTGOING camera (.203), before the target flips.
        self.assertEqual(sender.of("stop"), [("stop", CAM1)] * 3)
        self.assertEqual(sender.of("zoom_stop"), [("zoom_stop", CAM1)] * 3)
        self.assertEqual(eng._targets["left"], CAM2)
        # The next axis event now drives the new camera.
        sender.calls.clear()
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        self.assertEqual(sender.of("pantilt")[0][1], CAM2)

    def test_noop_switch_sends_no_stop(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_midi_in(SELECT_CH, LEFT_SELECT_CC, 1, 0.0)  # already Cam 1
        self.assertEqual(sender.calls, [])
        self.assertEqual(eng._targets["left"], CAM1)

    def test_switch_resets_state_so_watchdog_does_not_misfire(self) -> None:
        clock = FakeClock()
        eng, sender = _two_group_engine(clock=clock)
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)  # moving on .203
        eng.on_midi_in(SELECT_CH, LEFT_SELECT_CC, 2, clock.now)  # switch -> resets latches
        sender.calls.clear()
        clock.advance(0.3)
        eng.tick(clock.now)  # moving was cleared -> no spurious drop-STOP
        self.assertEqual(sender.calls, [])
        # A fresh axis event re-arms cleanly on the new camera.
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, clock.now)
        self.assertEqual(sender.of("pantilt")[0][1], CAM2)

    def test_both_groups_same_camera(self) -> None:
        eng, sender = _two_group_engine()
        eng.on_midi_in(SELECT_CH, RIGHT_SELECT_CC, 1, 0.0)  # right -> .203 too
        self.assertEqual(eng._targets, {"left": CAM1, "right": CAM1})
        # Both sticks drive .203.
        eng.on_axis_event("L_STICK_X_AXIS", LX + 30000, 0.0)
        eng.on_axis_event("R_STICK_X_AXIS", RX + 30000, 0.0)
        self.assertTrue(all(c[1] == CAM1 for c in sender.of("pantilt")))
        # LEFT switches away -> STOP .203 (which right is still on); right resumes.
        sender.calls.clear()
        eng.on_midi_in(SELECT_CH, LEFT_SELECT_CC, 2, 0.0)
        self.assertEqual(sender.of("stop"), [("stop", CAM1)] * 3)
        sender.calls.clear()
        eng.on_axis_event("R_STICK_X_AXIS", RX + 30000, 0.0)  # right's next event
        self.assertEqual(sender.of("pantilt")[0][1], CAM1)  # .203 resumes


if __name__ == "__main__":
    unittest.main()
