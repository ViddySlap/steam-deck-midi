"""Machine-local persistence of autopilot channel intent.

A bridge crash or restart mid-show used to turn every autopilot channel off
silently: ChannelState was rebuilt from config defaults. This module stores
the five USER-INTENT fields per channel (enabled, beats_per_clip,
transition_seconds, clip_mode, layer_enabled) in
`<config>/state/autopilot_channels.local.json` so a restarted engine can put
them back. Runtime fields (cycle position, crossfade timing, clip bags and
caches) are never stored: they describe a moment, not a choice.

File I/O never runs on the receiver thread. The engine hands a snapshot to
`AutopilotStateWriter.submit`, which only stores it and wakes a writer
thread. The writer always writes the LATEST snapshot (no timer, no debounce
window): changes that arrive while a write is in flight coalesce into the
next write. `flush`/`close` wait until the last submitted snapshot is on
disk, so a clean teardown never loses the final change.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable
from windows.clock import now as clock_now

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 1
STATE_FILE_NAME = "autopilot_channels.local.json"
STATE_DIR_NAME = "state"
FAILURE_LOG_INTERVAL_SECONDS = 60.0
INTENT_FIELDS = (
    "enabled",
    "beats_per_clip",
    "transition_seconds",
    "clip_mode",
    "layer_enabled",
)


class StateFileInvalid(ValueError):
    """The state file exists but cannot be used (malformed or future schema)."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_channel(raw: object, mode_names: frozenset[str]) -> None:
    if not isinstance(raw, dict):
        raise StateFileInvalid("channel entry is not an object")
    missing = [name for name in INTENT_FIELDS if name not in raw]
    if missing:
        raise StateFileInvalid(f"channel entry missing {missing}")
    if not isinstance(raw["enabled"], bool):
        raise StateFileInvalid("enabled must be a boolean")
    if not _is_int(raw["beats_per_clip"]) or raw["beats_per_clip"] < 1:
        raise StateFileInvalid("beats_per_clip must be an integer >= 1")
    seconds = raw["transition_seconds"]
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or seconds < 0
    ):
        raise StateFileInvalid("transition_seconds must be a finite number >= 0")
    if raw["clip_mode"] not in mode_names:
        raise StateFileInvalid("clip_mode must be a mode name")
    layers = raw["layer_enabled"]
    if not isinstance(layers, dict):
        raise StateFileInvalid("layer_enabled must be an object")
    for key, value in layers.items():
        if not key.isdigit() or not isinstance(value, bool):
            raise StateFileInvalid("layer_enabled must map layer numbers to booleans")


def read_state_file(path: Path, mode_names: frozenset[str]) -> dict[str, dict] | None:
    """Return the validated `engines` map, or None when the file is absent.

    Raises StateFileInvalid for unreadable JSON, a wrong shape, or a schema
    version this build does not know. The file is never modified here.
    """
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StateFileInvalid(f"cannot read: {exc}") from exc
    try:
        document = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise StateFileInvalid(f"not JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise StateFileInvalid("top level is not an object")
    schema = document.get("schema")
    if not _is_int(schema):
        raise StateFileInvalid("schema must be an integer")
    if schema != SCHEMA_VERSION:
        raise StateFileInvalid(f"unsupported schema {schema} (this build reads {SCHEMA_VERSION})")
    engines = document.get("engines")
    if not isinstance(engines, dict):
        raise StateFileInvalid("engines must be an object")
    for entry in engines.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("channels"), dict):
            raise StateFileInvalid("engine entry must hold a channels object")
        for channel in entry["channels"].values():
            _validate_channel(channel, mode_names)
    return engines


def build_document(engines: dict[str, dict]) -> dict:
    return {"schema": SCHEMA_VERSION, "engines": engines}


class AutopilotStateWriter:
    """Writes the latest submitted state document atomically, off-thread."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float] = clock_now,
    ) -> None:
        self.path = Path(path)
        self._clock = clock
        self._cond = threading.Condition()
        self._pending: dict | None = None
        self._submitted = 0
        self._completed = 0
        self._last_ok = True
        self._last_failure_log_at: float | None = None
        self._thread: threading.Thread | None = None
        self._closed = False

    def submit(self, document: dict) -> None:
        """Queue `document` as the newest state. Never blocks on I/O, never raises."""
        write_inline = False
        with self._cond:
            self._submitted += 1
            if self._closed:
                write_inline = True
                generation = self._submitted
            else:
                self._pending = document
                if self._thread is None:
                    self._thread = threading.Thread(
                        target=self._run, name="autopilot-state-writer", daemon=True
                    )
                    self._thread.start()
                self._cond.notify_all()
        if write_inline:
            # Only reachable after close(); the receiver loop has stopped.
            ok = self._write(document)
            with self._cond:
                self._completed = max(self._completed, generation)
                self._last_ok = ok
                self._cond.notify_all()

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until the last submitted document is written. True if it succeeded."""
        deadline = clock_now() + timeout
        with self._cond:
            while self._completed < self._submitted:
                remaining = deadline - clock_now()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return self._last_ok

    def close(self, timeout: float = 5.0) -> bool:
        ok = self.flush(timeout)
        with self._cond:
            self._closed = True
            self._cond.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return ok

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._pending is None and not self._closed:
                    self._cond.wait()
                if self._pending is None:
                    return
                document = self._pending
                generation = self._submitted
                self._pending = None
            ok = self._write(document)
            with self._cond:
                self._completed = generation
                self._last_ok = ok
                self._cond.notify_all()

    def _write(self, document: dict) -> bool:
        tmp_name: str | None = None
        try:
            payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
            tmp_name = None
            return True
        except Exception as exc:  # noqa: BLE001 - persistence must never break the show
            now = self._clock()
            if (
                self._last_failure_log_at is None
                or now - self._last_failure_log_at >= FAILURE_LOG_INTERVAL_SECONDS
            ):
                self._last_failure_log_at = now
                LOGGER.warning("autopilot state: write to %s failed: %s", self.path, exc)
            return False
        finally:
            if tmp_name is not None:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
