"""Small, dependency-free watcher for synced presets and local bridge identity."""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
from windows.clock import now as clock_now

LOGGER = logging.getLogger(__name__)


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


class PresetWatcher(threading.Thread):
    def __init__(self, presets_dir: Path, settings_path: Path, reload_event,
                 *, poll_interval: float = 0.5, debounce: float = 0.15):
        super().__init__(name='preset-watch', daemon=True)
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError('preset poll interval must be positive and finite')
        if not math.isfinite(debounce) or debounce < 0:
            raise ValueError('preset debounce must be non-negative and finite')
        self.presets_dir = presets_dir
        self.settings_path = settings_path
        self.reload_event = reload_event
        self.poll_interval = poll_interval
        self.debounce = debounce
        self._stop_event = threading.Event()
        # Capture before start returns so an immediate write cannot become the
        # baseline. A failed initial scan is retried without preventing startup.
        self._snapshot = None
        try:
            self._snapshot = self._scan()
        except Exception:
            LOGGER.exception('preset watch initial scan failed')

    def _scan(self):
        paths = set(self.presets_dir.glob('*.json'))
        paths.update((self.presets_dir / '.active', self.settings_path))
        return {path: file_signature(path) for path in paths}

    def stop(self):
        self._stop_event.set()

    def run(self):
        pending_since = None
        delay = self.poll_interval
        while not self._stop_event.wait(delay):
            delay = self.poll_interval
            try:
                current = self._scan()
                now = clock_now()
                if self._snapshot is None:
                    # A scan failure at startup may have hidden a change.
                    pending_since = now
                else:
                    changed = [path for path in current.keys() | self._snapshot.keys()
                               if current.get(path) != self._snapshot.get(path)]
                    for path in sorted(changed):
                        LOGGER.info('preset watch changed: %s', path)
                    if changed:
                        pending_since = now
                self._snapshot = current
                if pending_since is not None:
                    remaining = self.debounce - (now - pending_since)
                    if remaining <= 0:
                        self.reload_event.set()
                        pending_since = None
                    else:
                        # Re-stat at the quiet boundary, without adding another
                        # full poll interval to the 150 ms debounce.
                        delay = min(self.poll_interval, remaining)
            except Exception:
                LOGGER.exception('preset watch poll failed; retrying')
