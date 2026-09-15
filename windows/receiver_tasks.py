"""Run a callable on the receiver (serve_forever) thread and wait for it.

The HTTP server runs on its own threads, but engines and the receiver are
only ever touched from the serve_forever loop. A live change that must not
interleave with MIDI dispatch (for example swapping an engine instance) is
submitted here; serve_forever drains the queue at the top of its loop, right
beside the reload_event check, so the task runs between two datagrams and
never in the middle of one.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable

# How long a caller waits for the receiver loop to START a task. The loop
# wakes at least every poll interval (0.25 s by default), so a task that has
# not started after this long means the loop is not running (stopping, or a
# standalone UI server). A task that has not started is cancelled and never
# runs.
DEFAULT_START_TIMEOUT_SECONDS = 5.0


class ReceiverTaskTimeout(RuntimeError):
    """The receiver loop did not start the task in time; it will never run."""


class _Task:
    __slots__ = ("fn", "state", "result", "error", "done")

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn
        self.state = "pending"  # pending -> running -> done, or pending -> cancelled
        self.result: Any = None
        self.error: BaseException | None = None
        self.done = threading.Event()


class ReceiverTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: deque[_Task] = deque()

    def run(self, fn: Callable[[], Any], *, start_timeout: float = DEFAULT_START_TIMEOUT_SECONDS) -> Any:
        """Queue `fn` for the receiver thread, wait, and return its result.

        An exception raised by `fn` is re-raised here. Raises
        ReceiverTaskTimeout if the loop did not start `fn` within
        `start_timeout`; in that case `fn` is guaranteed not to run.
        """
        task = _Task(fn)
        with self._lock:
            self._pending.append(task)
        if not task.done.wait(start_timeout):
            with self._lock:
                if task.state == "pending":
                    task.state = "cancelled"
                    raise ReceiverTaskTimeout("receiver loop did not run the task")
            # Started before we could cancel: it runs to completion.
            task.done.wait()
        if task.error is not None:
            raise task.error
        return task.result

    def drain(self) -> int:
        """Run every pending task on the calling thread. Returns how many ran."""
        ran = 0
        while True:
            with self._lock:
                if not self._pending:
                    return ran
                task = self._pending.popleft()
                if task.state != "pending":
                    continue
                task.state = "running"
            try:
                task.result = task.fn()
            except BaseException as exc:  # noqa: BLE001 - handed to the caller
                task.error = exc
            finally:
                task.state = "done"
                task.done.set()
            ran += 1
