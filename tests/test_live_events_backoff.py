"""P0(d): a stalled LiveEvents writer cannot pin a reader core.

`LiveEvents._copy()` is a seqlock reader: it retries while the writer holds an
odd version. At BASE OF LAP both retry paths spun with at most `time.sleep(0)`,
which yields the GIL but does not deschedule, so a writer stalled mid-publication
pinned the reading thread at a full core. The Controller view holds a live
EventSource, so the reader is not hypothetical.

MEASURED, with a threshold declared before the data: over a 1.0 s wall window
with one reader blocked on a stalled writer, the process must burn less than
25% of one core. An unbounded spin burns ~100%; the bounded retry burns ~1%.
Reverting SPIN_BEFORE_BACKOFF/BACKOFF_SECONDS to `time.sleep(0)` turns
test_a_stalled_writer_does_not_pin_a_core RED - proved by
test_the_unbounded_shape_really_does_pin_a_core, which measures the BASE shape
in the same process, the same window and the same instrument.
"""

from __future__ import annotations

import threading
import time
import unittest

from windows.live_events import LiveEvents

WINDOW_SECONDS = 1.0
# Declared before data. A bounded reader is idle; an unbounded one is a core.
MAX_CORE_FRACTION = 0.25


def _measure_core_fraction(start_reader) -> float:
    """CPU seconds burned per wall second while `start_reader` runs."""
    stop = threading.Event()
    thread = threading.Thread(target=start_reader, args=(stop,), daemon=True)
    cpu0 = time.process_time()
    wall0 = time.monotonic()
    thread.start()
    # A sleep here is the MEASUREMENT WINDOW, not synchronisation.
    time.sleep(WINDOW_SECONDS)
    cpu = time.process_time() - cpu0
    wall = time.monotonic() - wall0
    stop.set()
    thread.join(10)
    return cpu / wall


class StalledWriterTests(unittest.TestCase):
    def _stalled_events(self) -> LiveEvents:
        events = LiveEvents()
        # Exactly the state a writer stalled mid-publication leaves behind:
        # an odd version, which every reader must wait out.
        events._version = 1
        return events

    def test_the_retry_is_bounded_by_declared_constants(self):
        self.assertGreater(LiveEvents.SPIN_BEFORE_BACKOFF, 0)
        self.assertGreaterEqual(LiveEvents.BACKOFF_SECONDS, 0.001)

    def test_a_stalled_writer_does_not_pin_a_core(self):
        events = self._stalled_events()

        def reader(stop):
            # _copy never returns while the version is odd; the daemon thread
            # is abandoned at the end of the window.
            try:
                events._copy()
            except Exception:
                pass

        fraction = _measure_core_fraction(reader)
        self.assertLess(
            fraction, MAX_CORE_FRACTION,
            f"a reader blocked on a stalled writer burned {fraction:.1%} of one "
            f"core over {WINDOW_SECONDS:.1f}s (limit {MAX_CORE_FRACTION:.0%}); "
            "the bounded retry in LiveEvents._copy has been weakened")

    def test_the_unbounded_shape_really_does_pin_a_core(self):
        """The detector fires: the BASE retry shape, same instrument, same window.

        Without this, a green above could mean the measurement is blind.
        """
        version = [1]

        def reader(stop):
            while not stop.is_set():
                if version[0] % 2:
                    time.sleep(0)   # the BASE shape, verbatim
                    continue

        fraction = _measure_core_fraction(reader)
        self.assertGreater(
            fraction, MAX_CORE_FRACTION,
            f"the unbounded spin burned only {fraction:.1%} of one core; the "
            "instrument cannot tell a spin from a sleep, so the green above "
            "would be vacuous")

    def test_a_reader_still_gets_a_snapshot_once_the_writer_finishes(self):
        """Bounding the retry must not break the thing it protects."""
        events = LiveEvents()
        events.publish({"kind": "midi", "bytes": [176, 1, 64]})
        snapshot = events.snapshot()
        self.assertEqual(len(snapshot["midi"]), 1)
        self.assertEqual(snapshot["midi"][0]["bytes"], [176, 1, 64])

    def test_a_reader_waiting_on_a_writer_returns_as_soon_as_it_finishes(self):
        events = self._stalled_events()
        result = {}
        done = threading.Event()

        def reader():
            result["value"] = events._copy()
            done.set()

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        # Let the reader reach the backoff, then complete the publication.
        time.sleep(0.05)
        self.assertFalse(done.is_set())
        events._version = 2
        self.assertTrue(done.wait(5), "reader never woke after the writer finished")
        thread.join(5)
        self.assertIsNotNone(result["value"])


if __name__ == "__main__":
    unittest.main()
