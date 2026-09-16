"""The bridge's one clock.

Every piece of bridge timing - fade progress, relative_cc repeats, staged note
macros, action timeouts, the rate-limit loop guard, engine ticks, and the
arrival stamp on inbound MIDI - reads the time through `now()` and nothing
else. Two reasons, in order of how much they cost:

1. MIXED CLOCKS SUBTRACT TO NONSENSE. Readings from two different clock
   sources have two different epochs, so subtracting one from the other is
   meaningless even when both are monotonic. Before this module the bridge had
   the injected `clock=` seam on one side of several comparisons and a bare
   `time.monotonic()` on the other (windows/receiver.py `_handle_feedback_message`,
   the three `engine_registry.tick()` calls, `MidiIn._clock`); they happened to
   be the same function object, so the bug was invisible. One function removes
   the class, not just the instances.

2. ON WINDOWS, `time.monotonic` IS TOO COARSE TO TIME MIDI WITH. It is
   GetTickCount64, whose resolution is 15.625 ms - measured on the show laptop's
   Python 3.12 (docs/sdwin-w4/REPORT.md). A 40 ms relative_cc repeat scheduled
   against it lands on 31.25 ms or 46.875 ms, and a fade advances in visible
   steps. `time.perf_counter` is QueryPerformanceCounter at 100 ns on the same
   interpreter. On macOS and Linux both are already sub-microsecond, so this
   changes nothing there.

`perf_counter` is monotonic and, since Python 3.3, is process-wide and
comparable across threads, which is all the bridge needs. Its epoch is
undefined, so a value from here is NEVER a wall-clock time: anything a person
reads (a log stamp, a filename) uses `datetime.now()` instead.

The `clock=` parameters throughout the bridge keep working and keep their
meaning - they are the test seam, and a test that wants a fake clock still
injects one. What changed is only what they DEFAULT to.
"""

import time

__all__ = ["now"]


def now() -> float:
    """The current reading of the bridge clock, in seconds.

    The epoch is arbitrary; only differences between two readings from this
    function are meaningful.
    """
    return time.perf_counter()
