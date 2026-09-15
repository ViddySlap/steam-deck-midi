"""In-memory ring of recent log records for GET /api/logs/tail.

Attached to the root logger at startup in every mode (console, tray,
--no-ui), so an agent can read what the console shows without a log file.
It holds formatted lines only, never opens a file, and keeps the newest
RING_CAPACITY records.
"""

from __future__ import annotations

import logging
from collections import deque

RING_CAPACITY = 1000
RING_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class RingLogHandler(logging.Handler):
    def __init__(self, capacity: int = RING_CAPACITY) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=capacity)
        self.setFormatter(logging.Formatter(RING_FORMAT))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._lines.append(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never raise
            self.handleError(record)

    def tail(self, lines: int) -> list[str]:
        """Return the newest `lines` formatted records, oldest first."""
        self.acquire()
        try:
            snapshot = list(self._lines)
        finally:
            self.release()
        return snapshot[-lines:] if lines > 0 else []


def install_ring_handler(logger: logging.Logger | None = None) -> RingLogHandler:
    """Attach one RingLogHandler to `logger` (root by default) and return it."""
    target = logger if logger is not None else logging.getLogger()
    for handler in target.handlers:
        if isinstance(handler, RingLogHandler):
            return handler
    handler = RingLogHandler()
    target.addHandler(handler)
    return handler
