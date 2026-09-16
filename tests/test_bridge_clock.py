"""P3: the bridge reads ONE clock, and that clock is fine enough to time MIDI.

Three checks, in the order they catch a regression:

* `BridgeClockWiringTests` - every injection default in the bridge IS
  `windows.clock.now`. Asserts the function objects actually wired into the
  classes, so it is RED on any machine the moment a default goes back to
  `time.monotonic`.
* `BridgeClockSourceScanTests` - no module under `windows/` reads a clock
  directly except `windows/clock.py`. An AST scan, so it catches a NEW bare
  read that the wiring test cannot see.
* `BridgeClockResolutionTests` - the behaviour the other two exist to protect:
  on a clock that advances in 15.625 ms steps (Windows `time.monotonic`, see
  docs/sdwin-w4/REPORT.md) a 40 ms relative_cc repeat and a macro fade come out
  visibly quantized, and on the bridge's real clock they do not.

Why 15.625 ms: that is the measured resolution of `time.monotonic` on the show
laptop's Python 3.12 (GetTickCount64). `time.perf_counter` there is
QueryPerformanceCounter at 100 ns.
"""

from __future__ import annotations

import ast
import inspect
import time
import unittest
from pathlib import Path

import windows.clock
from windows.clock import now as clock_now
from windows.config import MacroCCMapping, MacroSettings, RelativeCCMapping
from windows.live_events import LiveEvents
from windows.receiver import ActionReceiver

from tests.test_receiver import FakeMidiOut

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DIR = REPO_ROOT / "windows"

# The Windows `time.monotonic` tick, and the reason this item exists.
WINDOWS_MONOTONIC_STEP = 0.015625

# The ONE module allowed to name a stdlib clock. A path relative to windows/.
CLOCK_MODULE = "clock.py"

# Attribute reads on `time` that are a clock reading. `time.sleep` is a
# duration, not a reading, and is not in this set.
CLOCK_ATTRS = frozenset(
    {"monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns", "time", "time_ns"}
)


def scan_tree(root: Path) -> list[str]:
    """Every direct stdlib clock read under `root`, as 'relpath:line:time.attr'.

    Importable on purpose: a BASE archive can be scanned with HEAD's scanner,
    the same way tests/test_config_divisor_tripwire.py does it.
    """
    findings: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        if rel == CLOCK_MODULE:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in CLOCK_ATTRS
                and isinstance(node.value, ast.Name)
                and node.value.id == "time"
            ):
                findings.append(f"{rel}:{node.lineno}:time.{node.attr}")
    return findings


# Every class under windows/engines/ that takes a `clock=` with a default, from
# the P3 inventory. A new engine with a clock seam is expected to be added here.
EXPECTED_ENGINE_CLOCK_DEFAULTS = [
    "audio_opacity.AudioOpacityEngine",
    "autopilot.AutopilotEngine",
    "autopilot_ptz.AutopilotPtzEngine",
    "autopilot_state.AutopilotStateWriter",
    "base.Engine",
    "bumper_blast.BumperBlastEngine",
    "chaser_stack_dispatcher.ChaserStackDispatcherEngine",
    "flash_blast.FlashBlastEngine",
    "global_color.GlobalColorEngine",
    "gyro_feedback.GyroFeedbackEngine",
    "l_stick_layer.LStickLayerEngine",
    "nestdrop_engine.NestdropEngine",
    "osc_sync.OscSyncEngine",
    "ptz_visca.PtzViscaEngine",
    "stageflow_bridge.StageFlowBridgeEngine",
    "steam_input_layer_tracker.SteamInputLayerTrackerEngine",
]

class BridgeClockSourceScanTests(unittest.TestCase):
    def test_no_module_under_windows_reads_a_stdlib_clock_directly(self) -> None:
        self.assertEqual(
            scan_tree(WINDOWS_DIR),
            [],
            "these sites read a stdlib clock directly; route them through "
            "windows.clock.now so every comparison uses one clock",
        )

    def test_the_scanner_fires_on_a_planted_bare_read(self) -> None:
        """The detector must be shown to fire, or the empty list above is vacuous."""
        planted = REPO_ROOT / "tests" / "_clock_scan_fixture"
        planted.mkdir(exist_ok=True)
        try:
            (planted / "bare.py").write_text("import time\n\n\ndef f():\n    return time.monotonic()\n")
            (planted / "clean.py").write_text(
                "from windows.clock import now as clock_now\n\n\ndef f():\n    return clock_now()\n"
            )
            # A sleep is a duration, never a reading: it must NOT be flagged.
            (planted / "sleeps.py").write_text("import time\n\n\ndef f():\n    time.sleep(0.01)\n")
            found = scan_tree(planted)
            self.assertEqual(found, ["bare.py:5:time.monotonic"])
        finally:
            for child in planted.iterdir():
                child.unlink()
            planted.rmdir()

    def test_the_clock_module_itself_is_the_only_exemption(self) -> None:
        """clock.py is skipped by name, so prove it is the only file that needs to be."""
        self.assertTrue((WINDOWS_DIR / CLOCK_MODULE).is_file())
        self.assertIn("time.perf_counter", (WINDOWS_DIR / CLOCK_MODULE).read_text())


class BridgeClockWiringTests(unittest.TestCase):
    """Every `clock=` default IS windows.clock.now - the object, not a lookalike."""

    def _default(self, func, name="clock"):
        return inspect.signature(func).parameters[name].default

    def test_receiver_default_clock_is_the_bridge_clock(self) -> None:
        self.assertIs(self._default(ActionReceiver.__init__), clock_now)

    def test_live_events_default_clock_is_the_bridge_clock(self) -> None:
        self.assertIs(self._default(LiveEvents.__init__), clock_now)

    def test_every_engine_class_defaults_to_the_bridge_clock(self) -> None:
        import importlib
        import pkgutil

        import windows.engines

        checked: list[str] = []
        for mod in pkgutil.iter_modules(windows.engines.__path__):
            module = importlib.import_module(f"windows.engines.{mod.name}")
            for attr, obj in vars(module).items():
                if not inspect.isclass(obj) or obj.__module__ != module.__name__:
                    continue
                params = inspect.signature(obj.__init__).parameters
                if "clock" not in params:
                    continue
                default = params["clock"].default
                if default is inspect.Parameter.empty:
                    continue
                checked.append(f"{mod.name}.{attr}")
                self.assertIs(
                    default,
                    clock_now,
                    f"{mod.name}.{attr} defaults to {default!r}, not windows.clock.now",
                )
        # Zero observations is RED, never a vacuous pass, and a FLOOR would go
        # quiet if a class stopped being found. Assert the exact roster the
        # inventory in docs/sdpolish-p3/REPORT.md lists, so a class that
        # disappears from the walk is as loud as one with the wrong default.
        self.assertEqual(sorted(checked), sorted(EXPECTED_ENGINE_CLOCK_DEFAULTS))

    def test_midi_in_stamps_arrivals_with_the_bridge_clock(self) -> None:
        """received_at is compared against engine clock readings; same clock or nonsense."""
        source = (WINDOWS_DIR / "midi.py").read_text()
        self.assertIn("self._clock = clock_now", source)

    def test_the_bridge_clock_is_perf_counter(self) -> None:
        a = time.perf_counter()
        b = windows.clock.now()
        c = time.perf_counter()
        # Same epoch as perf_counter, which monotonic is not.
        self.assertLessEqual(a, b)
        self.assertLessEqual(b, c)


class _Wall:
    """A controllable wall time, read through two clocks of different resolution."""

    def __init__(self) -> None:
        self.t = 0.0

    def fine(self) -> float:
        return self.t

    def coarse(self) -> float:
        """What `time.monotonic` does on Windows: floor to a 15.625 ms tick."""
        return (self.t // WINDOWS_MONOTONIC_STEP) * WINDOWS_MONOTONIC_STEP


class BridgeClockResolutionTests(unittest.TestCase):
    """A 40 ms repeat and a fade, driven through the injected clock only.

    Nothing here passes `now=`: the receiver reads its own clock, which is the
    path the bridge actually runs, and the only path a clock change can reach.
    """

    ADDR = ("127.0.0.1", 45999)
    STEP = 0.001
    HORIZON = 0.200

    def _drive(self, wall, reader, receiver, midi, advance):
        """Step the wall in 1 ms ticks, recording the wall time of each new CC."""
        walls: list[float] = []
        seen = len(midi.calls)
        ticks = int(self.HORIZON / self.STEP)
        for i in range(1, ticks + 1):
            wall.t = round(i * self.STEP, 6)
            advance(receiver)
            if len(midi.calls) > seen:
                walls.extend([wall.t] * (len(midi.calls) - seen))
                seen = len(midi.calls)
        return walls

    def _relative_cc_walls(self, reader_name: str) -> list[float]:
        wall = _Wall()
        reader = getattr(wall, reader_name)
        midi = FakeMidiOut()
        receiver = ActionReceiver(
            midi,
            {
                "R_PAD_RIGHT": RelativeCCMapping(
                    action="R_PAD_RIGHT",
                    kind="relative_cc",
                    channel=0,
                    cc=47,
                    step_value=1,
                    repeat_interval_ms=40,
                )
            },
            timeout_seconds=10.0,
            clock=reader,
        )
        receiver.handle_datagram(b'{"action":"R_PAD_RIGHT","state":"down","seq":1}', self.ADDR)
        return self._drive(wall, reader, receiver, midi, lambda r: r.advance_relative_ccs())

    def _fade_values(self, reader_name: str) -> list[int]:
        wall = _Wall()
        reader = getattr(wall, reader_name)
        midi = FakeMidiOut()
        receiver = ActionReceiver(
            midi,
            {
                "DPAD_DOWN_LONG_PRESS": MacroCCMapping(
                    action="DPAD_DOWN_LONG_PRESS",
                    kind="macro_cc",
                    channel=0,
                    cc=20,
                    gesture="long_press",
                )
            },
            timeout_seconds=10.0,
            macro_settings=MacroSettings(fade_duration_seconds=0.2, update_hz=60),
            clock=reader,
        )
        receiver.handle_datagram(
            b'{"action":"DPAD_DOWN_LONG_PRESS","state":"down","seq":1}', self.ADDR
        )
        self._drive(wall, reader, receiver, midi, lambda r: r.advance_fades())
        return [call[3] for call in midi.calls if call[0] == "cc"]

    @staticmethod
    def _intervals(walls: list[float]) -> list[float]:
        return [round(b - a, 6) for a, b in zip(walls, walls[1:])]

    def test_a_40ms_repeat_is_exact_on_a_fine_clock(self) -> None:
        intervals = self._intervals(self._relative_cc_walls("fine"))
        self.assertGreaterEqual(len(intervals), 3, "the repeat did not fire enough times")
        self.assertEqual(set(intervals), {0.04}, f"fine clock intervals: {intervals}")

    def test_a_40ms_repeat_quantizes_on_a_15_625ms_clock(self) -> None:
        intervals = self._intervals(self._relative_cc_walls("coarse"))
        self.assertGreaterEqual(len(intervals), 3, "the repeat did not fire enough times")
        # Not 40 ms any more, and every interval a whole number of 15.625 ms
        # ticks: that is what the coarse clock does to a schedule.
        self.assertNotEqual(set(intervals), {0.04}, "no quantization: the clock was bypassed")
        # Each gap is a whole number of 15.625 ms ticks, to within the 1 ms
        # resolution this test drives the wall at (an emission is noticed at
        # the next 1 ms tick, not at the exact instant the coarse clock moved).
        for gap in intervals:
            error = abs(gap - round(gap / WINDOWS_MONOTONIC_STEP) * WINDOWS_MONOTONIC_STEP)
            self.assertLessEqual(
                error,
                self.STEP + 1e-9,
                f"{gap}s is {error}s off a whole 15.625 ms tick",
            )
        worst = max(abs(gap - 0.04) for gap in intervals)
        self.assertGreaterEqual(
            worst, 0.005, f"expected visible error against 40 ms, worst was {worst}"
        )

    def test_a_fade_quantizes_on_a_coarse_clock_and_not_on_a_fine_one(self) -> None:
        fine = self._fade_values("fine")
        coarse = self._fade_values("coarse")
        self.assertGreater(len(fine), 4, f"fade produced too few steps: {fine}")
        self.assertNotEqual(
            fine, coarse, "the fade came out identical on both clocks: the clock was bypassed"
        )
        # The fine clock walks the ramp one value at a time; the coarse one
        # sits still for a whole 15.625 ms tick and then JUMPS, because
        # advance_fades only moves when its clock reading changed. So the
        # quantization shows up as the size of the step between consecutive
        # emitted values, which is the thing a person sees on the light.
        fine_step = max(b - a for a, b in zip(fine, fine[1:]))
        coarse_step = max(b - a for a, b in zip(coarse, coarse[1:]))
        self.assertEqual(fine_step, 1, f"fine clock should walk in single steps: {fine}")
        self.assertGreaterEqual(
            coarse_step,
            5,
            f"expected a visible jump on the coarse clock: coarse={coarse}",
        )
        # And far fewer updates over the same fade, for the same reason.
        self.assertLess(len(coarse) * 2, len(fine), f"coarse={len(coarse)} fine={len(fine)}")

    def test_the_real_bridge_clock_resolves_finer_than_a_millisecond(self) -> None:
        """The property the show depends on, measured on the clock that ships.

        RED on Windows the moment windows.clock.now goes back to time.monotonic:
        GetTickCount64 cannot produce two distinct readings 1 ms apart.
        """
        deltas = []
        for _ in range(2000):
            a = windows.clock.now()
            b = windows.clock.now()
            if b > a:
                deltas.append(b - a)
        self.assertTrue(deltas, "the bridge clock never advanced over 2000 reads")
        self.assertLess(
            min(deltas),
            0.001,
            f"bridge clock granularity {min(deltas)}s is too coarse to time a 40 ms repeat",
        )


if __name__ == "__main__":
    unittest.main()
