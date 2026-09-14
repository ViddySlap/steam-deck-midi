"""Non-TTY learn session using the wizard's existing action and binding format."""
from __future__ import annotations

import copy
import selectors
import threading

from deck.learn_wizard import load_actions, load_existing_bindings, write_bindings
from deck.xinput_send import Xi2RawListener


class LearnSession:
    def __init__(self, settings, *, action=None):
        self.settings = settings
        actions = load_actions(settings.actions_path)
        if action is not None and action not in actions:
            raise ValueError("unknown action")
        self.actions = [action] if action is not None else actions
        self.single = action is not None
        self.bindings = load_existing_bindings(settings.bindings_path) if self.single else {}
        self.index = 0
        self.candidate = None
        self.error = None
        self.saved = False
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.active = False

    def start(self):
        # Open synchronously so HTTP can refuse an unavailable capture device.
        listener = Xi2RawListener(int(self.settings.device_id or "5"))
        def capture():
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(listener, selectors.EVENT_READ)
                    while not self.stop_event.is_set():
                        if selector.select(0.05):
                            event = listener.read_event()
                            while event is not None and not self.stop_event.is_set():
                                if event.state == "down":
                                    with self.lock:
                                        self.candidate = event.keycode
                                event = listener.read_event()
            except Exception as exc:
                with self.lock:
                    self.error, self.active = str(exc), False
            finally:
                listener.close()
        self.active = True
        self.thread = threading.Thread(target=capture, name="deck-learn", daemon=True)
        self.thread.start()

    def status(self):
        with self.lock:
            return {"active": self.active, "action": self.actions[self.index] if self.index < len(self.actions) else None,
                    "candidate": self.candidate, "bindings": copy.deepcopy(self.bindings),
                    "saved": self.saved, "error": self.error}

    def _advance(self, updated):
        if self.index + 1 == len(self.actions):
            write_bindings(self.settings.bindings_path, self.settings.profile_name or "default", updated)
            self.saved = True
            self.active = False
            self.stop_event.set()
        self.bindings = updated
        self.index += 1
        self.candidate = None

    def confirm(self):
        with self.lock:
            if not self.active or self.candidate is None:
                raise ValueError("no captured candidate")
            action = self.actions[self.index]
            if any(token == self.candidate and name != action for name, token in self.bindings.items()):
                raise ValueError("candidate is already assigned to another action")
            self._advance({**self.bindings, action: self.candidate})
        self._join_if_stopped()

    def skip(self):
        with self.lock:
            if not self.active:
                raise ValueError("no active learn session")
            if self.single:
                self.active = False
                self.stop_event.set()
            else:
                self._advance(dict(self.bindings))
        self._join_if_stopped()

    def cancel(self):
        with self.lock:
            self.active = False
            self.stop_event.set()
        self._join_if_stopped()

    def _join_if_stopped(self):
        if self.stop_event.is_set() and self.thread is not None:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise ValueError("learn capture is still stopping")
