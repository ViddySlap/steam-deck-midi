"""Stdlib-only HTTP control plane shared by the Deck menu and SSH clients."""
from __future__ import annotations

import argparse
import copy
import hmac
import json
import os
import signal
import sys
import threading
import time
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from deck.local_config import (
    api_is_loopback, ensure_local_settings, runtime_settings_from_dict,
    validate_api_bind, with_active_targets, with_deleted_preset,
    with_renamed_preset, write_runtime_settings,
)
from deck.xinput_send import run_sender, validate_bindings


class SenderController:
    """Serialize settings/menu/API changes; the worker only updates telemetry."""

    def __init__(self, settings_path, settings=None, *, run=run_sender):
        from deck.local_config import load_runtime_settings
        self.settings_path = settings_path
        self.settings = settings or load_runtime_settings(settings_path)
        self.lock = threading.RLock()
        self.metrics_lock = threading.Lock()
        self.run = run
        self.thread = None
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.seq = 0
        self.heartbeat_at = None
        self.last_error = None
        self.exit_code = None
        self.running_targets = []
        self.single_target = None
        self.bindings = None
        self.learn = None
        try:
            self.bindings = self._read_bindings(self.settings.bindings_path)
        except (OSError, ValueError) as exc:
            self.last_error = str(exc)

    @staticmethod
    def _read_bindings(path):
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        validate_bindings(document)
        return document

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.settings)

    def _selected(self):
        by_name = {p.name: p for p in self.settings.presets}
        names = self.settings.active_targets or ([self.single_target] if self.single_target else [])
        return [by_name[name] for name in names if name in by_name]

    def status(self):
        with self.lock, self.metrics_lock:
            return {
                "running": self.thread is not None and self.thread.is_alive(),
                "active_targets": [asdict(p) for p in self._selected()],
                "running_targets": copy.deepcopy(self.running_targets) if self.thread and self.thread.is_alive() else [],
                "seq": self.seq,
                "heartbeat_age": None if self.heartbeat_at is None else max(0, time.monotonic() - self.heartbeat_at),
                "profile_name": self.settings.profile_name or (self.bindings or {}).get("profile_name"),
                "profile_hash": self.settings.profile_hash,
                "bindings_path": self.settings.bindings_path,
                "device_id": self.settings.device_id or "5",
                "last_error": self.last_error, "exit_code": self.exit_code,
            }

    def _observe(self, *, seq, heartbeat_at=None):
        with self.metrics_lock:
            self.seq = seq
            if heartbeat_at is not None:
                self.heartbeat_at = heartbeat_at

    def start(self, single_target=None):
        with self.lock:
            if self.learn is not None and self.learn.active:
                raise ValueError("cancel or finish learning before starting the sender")
            if self.thread is not None and self.thread.is_alive():
                return self.status()
            if single_target is not None:
                self.single_target = single_target if not self.settings.active_targets else None
            selected = self._selected()
            if not selected:
                raise ValueError("select active targets first")
            if self.bindings is None:
                self.bindings = self._read_bindings(self.settings.bindings_path)
            self.stop_event = threading.Event()
            with self.metrics_lock:
                self.seq, self.heartbeat_at, self.last_error, self.exit_code = 0, None, None, None
            self.running_targets = [asdict(p) for p in selected]
            kwargs = dict(device_id=self.settings.device_id or "5",
                          bindings_path=self.settings.bindings_path,
                          targets=[(p.host, p.port) for p in selected],
                          profile_name=self.settings.profile_name, profile_hash=self.settings.profile_hash,
                          stop_event=self.stop_event, on_status=self._observe,
                          bindings_document=copy.deepcopy(self.bindings), manage_terminal=False)
            def worker():
                try:
                    result = self.run(**kwargs)
                    with self.metrics_lock:
                        self.exit_code = result
                        if result:
                            self.last_error = f"sender exited with code {result}"
                except Exception as exc:
                    with self.metrics_lock:
                        self.last_error, self.exit_code = str(exc), 2
                finally:
                    kwargs["stop_event"].set()
            self.thread = threading.Thread(target=worker, name="deck-sender", daemon=True)
            self.thread.start()
            return self.status()

    def stop(self):
        with self.lock:
            self.stop_event.set()
            if self.thread is not None:
                self.thread.join(timeout=3)
                if self.thread.is_alive():
                    raise ValueError("sender is still stopping; poll status before restarting")
            return self.status()

    def restart(self):
        with self.lock:
            self.stop()
            return self.start()

    def commit_settings(self, updated, *, expected=None):
        with self.lock:
            if expected is not None and expected != self.settings:
                raise ValueError("settings changed while the menu was open; select again")
            if self.learn is not None and self.learn.active:
                raise ValueError("cancel or finish learning before changing settings")
            updated = runtime_settings_from_dict(asdict(updated))
            if not api_is_loopback(updated.api_bind) and not updated.api_token:
                raise ValueError("api_token is required for an off-loopback api_bind")
            if getattr(self, "token_required", False) and not updated.api_token:
                raise ValueError("cannot remove api_token while serving off-loopback")
            bindings = self.bindings
            if updated.bindings_path != self.settings.bindings_path:
                bindings = self._read_bindings(updated.bindings_path)
            running = self.thread is not None and self.thread.is_alive()
            sender_fields = ("device_id", "bindings_path", "profile_name", "profile_hash", "presets", "active_targets")
            restart_needed = any(getattr(updated, key) != getattr(self.settings, key) for key in sender_fields)
            # Persist before publishing memory or touching the running sender.
            write_runtime_settings(self.settings_path, updated)
            self.settings = updated
            self.bindings = bindings
            if self.single_target not in {p.name for p in updated.presets}:
                self.single_target = None
            if running and restart_needed:
                self.stop()
                if self._selected():
                    self.start()
            return self.snapshot()

    def update_settings(self, changes):
        with self.lock:
            allowed = set(asdict(self.settings)) - {"presets", "active_targets"}
            if set(changes) - allowed:
                raise ValueError("unknown settings fields; use target routes for presets/active_targets")
            updated = runtime_settings_from_dict({**asdict(self.settings), **changes})
            return self.commit_settings(updated)

    def settings_json(self):
        with self.lock:
            result = asdict(self.settings)
            result["api_token_configured"] = bool(result.pop("api_token"))
            return result

    def targets_json(self):
        with self.lock:
            return {"presets": [asdict(p) for p in self.settings.presets],
                    "active_targets": list(self.settings.active_targets)}

    def change_targets(self, action, body):
        with self.lock:
            current = self.settings
            if action == "active":
                updated = with_active_targets(current, body["names"])
                previous_single = self.single_target
                self.single_target = None
                try:
                    self.commit_settings(updated)
                    if not body["names"]:
                        self.stop()
                except (OSError, ValueError):
                    self.single_target = previous_single
                    raise
            else:
                if action in {"replace", "add"}:
                    entries = body["presets"] if action == "replace" else [
                        {**body, "port": body.get("port", current.default_port)}]
                    if not isinstance(entries, list):
                        raise ValueError("presets must be a list")
                    if action == "add":
                        entries = [asdict(p) for p in current.presets] + entries
                    updated = runtime_settings_from_dict({**asdict(current), "presets": entries, "active_targets": []})
                    names = [p.name for p in updated.presets]
                    if len(names) != len(set(names)):
                        raise ValueError("preset names must be unique")
                    updated = with_active_targets(updated, [n for n in current.active_targets if n in names])
                else:
                    name = body["old"] if action == "rename" else body["name"]
                    matches = [i for i, p in enumerate(current.presets) if p.name == name]
                    if len(matches) != 1:
                        raise ValueError("unknown or ambiguous target name")
                    if action == "rename":
                        updated = with_renamed_preset(current, matches[0], body["new"])
                    else:
                        updated = with_deleted_preset(current, matches[0])
                previous_single = self.single_target
                if action == "rename" and self.single_target == body["old"]:
                    self.single_target = body["new"].strip()
                try:
                    self.commit_settings(updated)
                except (OSError, ValueError):
                    self.single_target = previous_single
                    raise
            return self.targets_json()

    def reload_bindings(self):
        with self.lock:
            document = self._read_bindings(self.settings.bindings_path)
            running = self.thread is not None and self.thread.is_alive()
            if running:
                self.stop()
            self.bindings = document
            if running:
                self.start()
            return copy.deepcopy(document)

    def learning(self, action, body):
        from deck.control_learn import LearnSession
        with self.lock:
            if action == "start":
                if self.thread is not None and self.thread.is_alive():
                    raise ValueError("stop the sender before learning")
                if self.learn is not None and self.learn.active:
                    raise ValueError("learning is already active")
                session = LearnSession(self.settings, action=body.get("action"))
                session.start()
                self.learn = session
            elif self.learn is None:
                if action == "status":
                    return {"active": False}
                raise ValueError("no learn session")
            elif action != "status":
                getattr(self.learn, action)()
                if self.learn.saved:
                    self.reload_bindings()
            return self.learn.status()


ROUTES = {
    ("POST", "/api/shutdown"),
    ("GET", "/api/status"), ("GET", "/api/targets"), ("POST", "/api/targets"),
    *(('POST', '/api/targets/' + name) for name in ('active', 'add', 'delete', 'rename')),
    *(('POST', '/api/sender/' + name) for name in ('start', 'stop', 'restart')),
    ("GET", "/api/bindings"), ("POST", "/api/bindings/reload"),
    ("GET", "/api/settings"), ("PUT", "/api/settings"),
    ("GET", "/api/actions"), ("GET", "/api/learn"),
    *(('POST', '/api/learn/' + name) for name in ('start', 'confirm', 'skip', 'cancel')),
}


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True
    routes = ROUTES

    def __init__(self, controller, *, bind=None, port=None, on_shutdown=None):
        self.controller = controller
        self.on_shutdown = on_shutdown
        bind = validate_api_bind(bind if bind is not None else controller.settings.api_bind)
        self.token_required = not api_is_loopback(bind)
        if self.token_required and not controller.settings.api_token:
            raise ValueError("api_token is required when binding off-loopback")
        port = controller.settings.api_port if port is None else port
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("API port must be between 0 and 65535")
        super().__init__((bind, port), _Handler)
        controller.token_required = self.token_required
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05},
                                       name="deck-control-api", daemon=True)
        self.thread.start()

    def close(self):
        thread = self.thread
        if thread is not None:
            self.shutdown()
            thread.join(timeout=3)
            self.thread = None
        self.server_close()

    def dispatch(self, method, path, body):
        controller = self.controller
        with controller.lock:
            if path == "/api/shutdown":
                if controller.learn is not None:
                    controller.learn.cancel()
                controller.stop()
                return {"ok": True}
            if (method, path) == ("GET", "/api/status"):
                return controller.status()
            if path == "/api/settings":
                if method == "PUT":
                    controller.update_settings(body)
                return controller.settings_json()
            if path.startswith("/api/targets"):
                if method == "POST":
                    return controller.change_targets(path.rsplit("/", 1)[1] if path != "/api/targets" else "replace", body)
                return controller.targets_json()
            if path.startswith("/api/sender/"):
                return getattr(controller, path.rsplit("/", 1)[1])()
            if path == "/api/bindings/reload":
                return controller.reload_bindings()
            if path == "/api/bindings":
                if controller.bindings is None:
                    raise ValueError("no bindings loaded; learn or reload bindings first")
                return copy.deepcopy(controller.bindings)
            if path == "/api/actions":
                from deck.learn_wizard import load_actions
                return {"actions": load_actions(controller.settings.actions_path)}
            return controller.learning("status" if path == "/api/learn" else path.rsplit("/", 1)[1], body)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, result):
        payload = json.dumps(result, ensure_ascii=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_error(self, code, message=None, explain=None):
        if code == 501:
            code = 405
        self._json(code, {"error": message or self.responses.get(code, ("request failed",))[0]})

    def _request(self):
        self.connection.settimeout(3)
        # Authentication and mutation share a lock, including token rotation.
        with self.server.controller.lock:
            token = self.server.controller.settings.api_token or ""
            supplied = self.headers.get("X-Deck-Token", "")
            if self.server.token_required and not hmac.compare_digest(supplied.encode(), token.encode()):
                return self._json(401, {"error": "X-Deck-Token required"})
            path = urlsplit(self.path).path
            if (self.command, path) not in self.server.routes:
                code = 405 if any(p == path for _, p in self.server.routes) else 404
                return self._json(code, {"error": "method not allowed" if code == 405 else "route not found"})
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Transfer-Encoding is not supported")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 1024 * 1024:
                    raise ValueError("body must be at most 1 MiB")
                body = json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(body, dict):
                    raise ValueError("body must be a JSON object")
                result = self.server.dispatch(self.command, path, body)
            except (ValueError, KeyError, TypeError, AttributeError, UnicodeError, OSError) as exc:
                return self._json(400, {"error": str(exc) or "invalid request"})
            self._json(200, result)
        if path == "/api/shutdown":
            self.wfile.flush()
            self.server.close()
            if self.server.on_shutdown is not None:
                self.server.on_shutdown()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _request


def interrupt_launcher():
    """Wake the launcher out of blocking TTY input after HTTP shutdown replies."""
    os.kill(os.getpid(), signal.SIGINT)


def add_api_arguments(parser):
    parser.add_argument("--api-bind", default=None, help="API IPv4 bind override; LAN binds require api_token in settings")
    parser.add_argument("--api-port", type=int, default=None, help="API port override (default: settings or 7724)")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deck sender control API without a TTY menu")
    parser.add_argument("--settings", default="config/deck_runtime_settings.local.json")
    parser.add_argument("--settings-example", default="config/deck_runtime_settings.example.json")
    add_api_arguments(parser)
    args = parser.parse_args(argv)
    controller = None
    try:
        settings = ensure_local_settings(args.settings, args.settings_example)
        controller = SenderController(args.settings, settings)
        server = ControlServer(controller, bind=args.api_bind, port=args.api_port)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    server.start()
    print(f"Deck control API: http://{server.server_address[0]}:{server.server_address[1]}", flush=True)
    api_thread = server.thread
    try:
        while api_thread.is_alive():
            api_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if controller.learn is not None:
            controller.learn.cancel()
        controller.stop()
        server.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
