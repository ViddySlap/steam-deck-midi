"""Lossy observation of bridge I/O; consumers never run on the MIDI thread.

CPython's bounded deque append and container copies run under the GIL.
Concurrent engine publishers try a writer lock once, dropping on contention. Readers retry an overlapping state copy;
the writer never acquires a reader lock, signals a condition, serializes JSON,
waits for a socket, or walks the client list.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
from itertools import count
import threading
import time

from windows.midi import MidiOut
from windows.clock import now as clock_now

_CURRENT_ACTION = ContextVar("live_midi_action", default=None)


@contextmanager
def action_context(action):
    token = _CURRENT_ACTION.set(action)
    try:
        yield
    finally:
        _CURRENT_ACTION.reset(token)


def current_action():
    return _CURRENT_ACTION.get()


def attributed(method):
    """Scope observer metadata only; keep the decorated handler unchanged."""
    @wraps(method)
    def call(self, event_or_action, *args, **kwargs):
        action = getattr(event_or_action, "action", event_or_action)
        with action_context(action):
            return method(self, event_or_action, *args, **kwargs)
    return call


def safe_publish(publisher, event):
    try:
        publisher.publish(event)
    except Exception:
        pass  # Observation failure must never escape into the bridge.


class LiveEvents:
    AXIS_INTERVAL = 1 / 30
    MAX_CLIENTS = 16
    MAX_ACTIONS = 512

    def __init__(self, capacity=1024, clock=clock_now):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._events = deque(maxlen=capacity)
        self._inputs = {}
        self._axes = {}
        self._midi = deque(maxlen=20)
        self._seq = 0
        self._tickets = count(1)
        self._publish_lock = threading.Lock()
        self._contention_dropped = 0
        self._dropped = 0
        self._version = 0
        self._clock = clock
        self._closed = threading.Event()
        self._clients = set()
        self._client_lock = threading.Lock()  # Reader side only.

    def publish(self, event):
        """Constant work, drop oldest, no client-dependent work or waits.

        In addition to append, timestamp/sequence and bounded latest-state
        bookkeeping are necessary even with no clients (snapshot contract).
        Only plain internal event dicts are retained; no user callbacks run.
        """
        ticket = next(self._tickets)
        if not self._publish_lock.acquire(blocking=False):
            self._contention_dropped += 1
            return
        try:
            self._version += 1
            if ticket <= self._seq:
                self._contention_dropped += 1
                return
            self._seq = ticket
            row = {**event, "seq": self._seq, "timestamp": self._clock()}
            kind = row["kind"]
            if kind in ("input", "axis"):
                state = self._inputs if kind == "input" else self._axes
                action = row["action"]
                if action not in state and len(state) >= self.MAX_ACTIONS:
                    del state[next(iter(state))]
                state[action] = row["state"] if kind == "input" else row["value"]
            elif kind == "midi":
                self._midi.append(row)
            if len(self._events) == self._events.maxlen:
                self._dropped += 1
            self._events.append(row)
        except Exception:
            pass
        finally:
            self._version += 1
            self._publish_lock.release()

    # Bounded retry (P0). Both retry paths below used to spin with at most
    # time.sleep(0), which yields but does not deschedule: a writer that stalls
    # mid-publication (odd version) pinned a reader thread at a full core. After
    # SPIN_BEFORE_BACKOFF attempts the reader sleeps for real, which costs a
    # reader nothing in the common case (publication is a few microseconds) and
    # caps the cost of the pathological one.
    SPIN_BEFORE_BACKOFF = 64
    BACKOFF_SECONDS = 0.001

    def _copy(self):
        # A reader can wait/retry; publication never waits for a reader.
        attempts = 0
        while True:
            if attempts >= self.SPIN_BEFORE_BACKOFF:
                time.sleep(self.BACKOFF_SECONDS)
            else:
                attempts += 1
            version = self._version
            if version % 2:
                time.sleep(0)
                continue
            result = (list(self._events), self._inputs.copy(), self._axes.copy(),
                      list(self._midi), self._seq, self._dropped + self._contention_dropped)
            if version == self._version:
                return result

    def snapshot(self):
        _, inputs, axes, midi, seq, dropped = self._copy()
        with self._client_lock:
            clients = len(self._clients)
        return {"pressed": sorted(a for a, state in inputs.items() if state == "down"),
                "axes": axes, "midi": midi, "seq": seq, "dropped": dropped,
                "clients": clients}

    def subscribe(self, since=None):
        with self._client_lock:
            if self._closed.is_set() or len(self._clients) >= self.MAX_CLIENTS:
                return None
            sub = LiveSubscription(self, self._seq if since is None else min(since, self._seq))
            self._clients.add(sub)
            return sub

    def close(self):
        self._closed.set()
        with self._client_lock:
            self._clients.clear()


class LiveSubscription:
    def __init__(self, publisher, since):
        self.publisher = publisher
        self.since = since
        self._next_read = 0.0
        self._closed = False

    def close(self):
        self._closed = True
        with self.publisher._client_lock:
            self.publisher._clients.discard(self)

    def read(self):
        """One bounded batch; polling/coalescing belongs to the reader."""
        p = self.publisher
        if self._closed or p._closed.is_set():
            return []
        now = p._clock()
        if now < self._next_read:
            return []
        self._next_read = now + p.AXIS_INTERVAL
        events, _, _, _, _, dropped = p._copy()
        rows, axes = [], {}
        previous = self.since
        for row in events:
            if row["seq"] <= self.since:
                continue
            missed = row["seq"] - previous - 1
            if missed:
                rows.append({"kind": "dropped", "seq": row["seq"] - 1,
                             "timestamp": now, "count": missed, "dropped": dropped})
            previous = row["seq"]
            if row["kind"] == "axis":
                axes[row["action"]] = row
            else:
                rows.append(row)
        rows.extend(axes.values())
        rows.sort(key=lambda row: row["seq"])
        if events:
            self.since = max(self.since, events[-1]["seq"])
        return rows

    def stream(self):
        try:
            # Flush HTTP headers immediately, even when the bridge is idle.
            yield ": live events\n\n"
            while not self._closed and not self.publisher._closed.is_set():
                for row in self.read():
                    if self._closed or self.publisher._closed.is_set():
                        return
                    yield (f'id: {row["seq"]}\nevent: {row["kind"]}\n'
                           f'data: {json.dumps(row, separators=(",", ":"), ensure_ascii=True)}\n\n')
                if self.publisher._closed.wait(self.publisher.AXIS_INTERVAL):
                    return
                # A keepalive lets disconnected idle sockets be discovered.
                yield ": keepalive\n\n"
        finally:
            self.close()


class LiveMidiOut(MidiOut):
    """Forward FIRST, observe AFTER, including backend-internal panic CCs.

    Tap the three bound backend methods so panic's calls to self.control_change
    are observed individually, even if a later panic send fails. The recorder
    installed at open_midi_output remains the real backend. No message is
    invented for a backend (such as dry-run) whose panic emits no bytes.
    """
    def __init__(self, backend, publisher):
        self._backend = backend
        for name, status, fields in (
            ("note_on", 0x90, ("channel", "note", "velocity")),
            ("note_off", 0x80, ("channel", "note", "velocity")),
            ("control_change", 0xB0, ("channel", "control", "value")),
        ):
            original = getattr(backend, name)
            setattr(backend, name, self._tap(original, publisher, status, fields))

    @staticmethod
    def _tap(original, publisher, status, fields):
        @wraps(original)
        def call(*args, **kwargs):
            result = original(*args, **kwargs)
            try:
                values = [args[i] if i < len(args) else kwargs.get(field, 0)
                          for i, field in enumerate(fields)]
                safe_publish(publisher, {"kind": "midi", "bytes": [status | values[0],
                             values[1], values[2]], "action": current_action()})
            except Exception:
                pass
            return result
        return call

    @property
    def port_name(self):
        return self._backend.port_name

    @property
    def port_index(self):
        return self._backend.port_index

    def note_on(self, *args, **kwargs):
        return self._backend.note_on(*args, **kwargs)

    def note_off(self, *args, **kwargs):
        return self._backend.note_off(*args, **kwargs)

    def control_change(self, *args, **kwargs):
        return self._backend.control_change(*args, **kwargs)

    def panic(self):
        # Safety resets do not belong to the last physical action.
        with action_context(None):
            return self._backend.panic()

    def close(self):
        return self._backend.close()
