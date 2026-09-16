"""P0(a): engine tick-rate bounds - one bad rate cannot stop or spin the bridge.

At BASE OF LAP, `update_hz` 0 raised ZeroDivisionError out of
`EngineRegistry.shortest_tick_interval()` (which is called OUTSIDE the
per-engine tick try/except), a negative value made `sock.settimeout` raise
ValueError, and `inf` produced a 0.0 timeout - a NON-BLOCKING socket whose
`recvfrom` raises BlockingIOError, which `except socket.timeout` does not
catch. Every one of those exits the receive loop. A huge value is a spin.

Reverting any clamp in windows/engines/*.py, the guard in
`shortest_tick_interval`, or the floor in `serve_forever` turns these RED.
"""

from __future__ import annotations

import math
import socket
import unittest
from unittest.mock import Mock

from windows.engine_config_api import _rate_field_error
from windows.engines.base import MAX_TICK_HZ, MIN_TICK_HZ, Engine, clamp_tick_hz
from windows.engines.registry import EngineRegistry, build_engine
from windows.midi import DryRunMidiOut
from windows.receiver import MIN_SOCKET_TIMEOUT_SECONDS

# The rate field each engine reads, and the extra config it needs to stay off
# the network during the test.
RATE_ENGINES: tuple[tuple[str, str, dict], ...] = (
    ("autopilot", "update_hz", {}),
    ("audio_opacity", "update_hz", {}),
    ("autopilot_ptz", "update_hz", {}),
    ("chaser_stack_dispatcher", "tick_hz", {}),
    ("ptz_visca", "stream_hz", {"camera_nic_ip": "127.0.0.1"}),
)

# The values the master named. Each one killed or spun the loop at BASE.
BAD_VALUES: tuple[object, ...] = (0, -5, 100000, float("nan"), float("inf"))


class ClampTickHzTests(unittest.TestCase):
    def test_bounds_match_the_mapping_ui_clamp(self):
        # windows/static/index.html: update_hz min 1, max 120.
        self.assertEqual((MIN_TICK_HZ, MAX_TICK_HZ), (1.0, 120.0))

    def test_every_bad_value_lands_inside_the_bounds(self):
        for value in BAD_VALUES:
            with self.subTest(value=value):
                hz = clamp_tick_hz(value, default=30.0)
                self.assertTrue(math.isfinite(hz), hz)
                self.assertGreaterEqual(hz, MIN_TICK_HZ)
                self.assertLessEqual(hz, MAX_TICK_HZ)

    def test_specific_mappings(self):
        self.assertEqual(clamp_tick_hz(0, default=30.0), MIN_TICK_HZ)
        self.assertEqual(clamp_tick_hz(-5, default=30.0), MIN_TICK_HZ)
        self.assertEqual(clamp_tick_hz(100000, default=30.0), MAX_TICK_HZ)
        self.assertEqual(clamp_tick_hz(float("inf"), default=30.0), MAX_TICK_HZ)
        self.assertEqual(clamp_tick_hz(float("-inf"), default=30.0), MIN_TICK_HZ)
        # NaN is not "out of range", it is "not a number": fall back.
        self.assertEqual(clamp_tick_hz(float("nan"), default=30.0), 30.0)

    def test_a_value_in_range_is_returned_unchanged(self):
        for good in (1, 30, 59.94, 120):
            with self.subTest(good=good):
                self.assertEqual(clamp_tick_hz(good, default=30.0), float(good))

    def test_non_numeric_falls_back_and_never_raises(self):
        for junk in (None, "sixty", [], {}, object()):
            with self.subTest(junk=junk):
                self.assertEqual(clamp_tick_hz(junk, default=30.0), 30.0)

    def test_a_nan_default_still_yields_a_usable_rate(self):
        self.assertEqual(clamp_tick_hz("junk", default=float("nan")), MIN_TICK_HZ)


class EngineTickIntervalBoundsTests(unittest.TestCase):
    """Every engine, every bad value: built, bounded, and usable as a timeout."""

    def _build(self, type_name, field, extra, value):
        spec = {"type": type_name, "enabled": True, field: value, **extra}
        return build_engine(spec, DryRunMidiOut(), state_dir=None)

    def test_tick_interval_is_finite_positive_and_bounded(self):
        for type_name, field, extra in RATE_ENGINES:
            for value in BAD_VALUES:
                with self.subTest(engine=type_name, value=value):
                    engine = self._build(type_name, field, extra, value)
                    interval = engine.tick_interval_seconds()
                    self.assertIsNotNone(interval)
                    self.assertTrue(math.isfinite(interval), interval)
                    self.assertGreater(interval, 0.0, interval)
                    # Bounded by the slowest allowed rate; an engine may ask for
                    # something SHORTER than 1/MIN_TICK_HZ for its own reasons
                    # (ptz_visca caps to its watchdog window), never longer.
                    self.assertLessEqual(interval, 1.0 / MIN_TICK_HZ, interval)
                    self.assertGreaterEqual(interval, 1.0 / MAX_TICK_HZ, interval)

    def test_shortest_tick_interval_never_raises(self):
        for type_name, field, extra in RATE_ENGINES:
            for value in BAD_VALUES:
                with self.subTest(engine=type_name, value=value):
                    engine = self._build(type_name, field, extra, value)
                    registry = EngineRegistry([engine])
                    interval = registry.shortest_tick_interval()
                    self.assertIsNotNone(interval)
                    self.assertTrue(math.isfinite(interval), interval)
                    self.assertGreater(interval, 0.0)

    def test_the_resulting_timeout_is_accepted_by_a_real_socket(self):
        """The BASE failure was here: settimeout(-0.2) raised, settimeout(0.0)
        made the socket non-blocking and recvfrom then raised BlockingIOError."""
        for type_name, field, extra in RATE_ENGINES:
            for value in BAD_VALUES:
                with self.subTest(engine=type_name, value=value):
                    engine = self._build(type_name, field, extra, value)
                    registry = EngineRegistry([engine])
                    timeout = min(0.25, registry.shortest_tick_interval())
                    timeout = max(MIN_SOCKET_TIMEOUT_SECONDS, timeout)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.addCleanup(sock.close)
                    sock.settimeout(timeout)
                    self.assertGreater(sock.gettimeout(), 0.0)

    def test_tick_does_not_raise_under_a_bad_rate(self):
        """audio_opacity divides by the rate inside tick() as well."""
        for type_name, field, extra in RATE_ENGINES:
            for value in BAD_VALUES:
                with self.subTest(engine=type_name, value=value):
                    engine = self._build(type_name, field, extra, value)
                    EngineRegistry([engine]).tick(1234.5)


class _RaisingEngine(Engine):
    type_name = "raising"

    def tick_interval_seconds(self):
        raise RuntimeError("planted: tick_interval_seconds blew up")


class _NonFiniteEngine(Engine):
    type_name = "nonfinite"

    def __init__(self, *args, value, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = value

    def tick_interval_seconds(self):
        return self._value


class ShortestTickIntervalIsolationTests(unittest.TestCase):
    """shortest_tick_interval sits outside the tick try/except; it must not
    let one engine take the receive loop down with it."""

    def _engine(self, cls, **kwargs):
        return cls("planted", {"enabled": True}, DryRunMidiOut(), **kwargs)

    def test_a_raising_engine_is_skipped_not_propagated(self):
        registry = EngineRegistry([self._engine(_RaisingEngine)])
        self.assertIsNone(registry.shortest_tick_interval())

    def test_a_raising_engine_does_not_hide_a_healthy_one(self):
        healthy = build_engine({"type": "autopilot", "enabled": True, "update_hz": 30},
                               DryRunMidiOut(), state_dir=None)
        registry = EngineRegistry([self._engine(_RaisingEngine), healthy])
        self.assertAlmostEqual(registry.shortest_tick_interval(), 1.0 / 30.0)

    def test_non_finite_and_non_positive_intervals_are_skipped(self):
        for value in (0.0, -1.0, float("nan"), float("inf"), "thirty", None):
            with self.subTest(value=value):
                registry = EngineRegistry([self._engine(_NonFiniteEngine, value=value)])
                self.assertIsNone(registry.shortest_tick_interval())

    def test_an_inactive_raising_engine_is_never_asked(self):
        engine = self._engine(_RaisingEngine)
        engine.set_active(False)
        self.assertIsNone(EngineRegistry([engine]).shortest_tick_interval())


class SocketTimeoutFloorTests(unittest.TestCase):
    def test_the_floor_is_one_millisecond(self):
        self.assertEqual(MIN_SOCKET_TIMEOUT_SECONDS, 0.001)

    def test_the_floor_turns_every_killer_value_into_a_blocking_timeout(self):
        # These are the raw values serve_forever could compute at BASE.
        for raw in (0.0, -0.2, 1e-9, float("nan")):
            with self.subTest(raw=raw):
                timeout = max(MIN_SOCKET_TIMEOUT_SECONDS, min(raw, 0.25))
                self.assertGreaterEqual(timeout, MIN_SOCKET_TIMEOUT_SECONDS)
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.addCleanup(sock.close)
                sock.settimeout(timeout)
                # Non-zero timeout => still a BLOCKING socket, so recvfrom
                # raises socket.timeout (caught) and not BlockingIOError.
                self.assertGreater(sock.gettimeout(), 0.0)
                sock.bind(("127.0.0.1", 0))
                with self.assertRaises(socket.timeout):
                    sock.recvfrom(16)


class PutEngineConfigRateValidationTests(unittest.TestCase):
    """PUT /api/engines/<type>/config refuses a bad rate and writes nothing."""

    def test_every_bad_value_is_named_and_refused(self):
        for field in ("update_hz", "tick_hz", "stream_hz"):
            for value in BAD_VALUES:
                with self.subTest(field=field, value=value):
                    message = _rate_field_error({field: value})
                    self.assertIsNotNone(message)
                    self.assertTrue(message.startswith(field), message)
                    self.assertTrue(message.isascii(), message)

    def test_values_in_range_and_absent_fields_are_accepted(self):
        self.assertIsNone(_rate_field_error({}))
        self.assertIsNone(_rate_field_error({"update_hz": 30}))
        self.assertIsNone(_rate_field_error({"update_hz": MIN_TICK_HZ}))
        self.assertIsNone(_rate_field_error({"update_hz": MAX_TICK_HZ}))

    def test_a_bad_rate_is_refused_before_anything_is_written(self):
        from windows import engine_config_api

        registry = Mock()
        registry.user_dir = Mock()
        registry.get_by_type.return_value = Mock()
        receiver_tasks = Mock()
        status, payload = engine_config_api.put_engine_config(
            registry, receiver_tasks, "autopilot", {"update_hz": 0})
        self.assertEqual(status, 400)
        self.assertEqual(payload["field"], "update_hz")
        self.assertIn("update_hz", payload["error"])
        # Nothing was queued onto the receiver thread, so nothing was written.
        self.assertEqual(receiver_tasks.run.call_count, 0)

    def test_a_good_rate_still_reaches_the_normal_path(self):
        from windows import engine_config_api

        registry = Mock()
        registry.user_dir = None  # short-circuits with 404, past rate validation
        status, _ = engine_config_api.put_engine_config(
            registry, Mock(), "autopilot", {"update_hz": 30})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
