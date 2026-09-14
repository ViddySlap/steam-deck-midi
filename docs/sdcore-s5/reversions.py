"""Copy-only mutation controls; production checkout is never rewritten."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path('/tmp/sdcore-s5/reversions')
SCRATCH.mkdir(parents=True, exist_ok=True)
COPY = SCRATCH / 'source'
COPY.mkdir(exist_ok=True)
for name in ('deck', 'protocol'):
    shutil.copytree(ROOT / name, COPY / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
(COPY / 'tests').mkdir(exist_ok=True)
for name in ('__init__.py', 'test_deck_control_api.py', 'test_deck_fanout_launch.py'):
    shutil.copy2(ROOT / 'tests' / name, COPY / 'tests' / name)
(COPY / 'docs').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'docs/api.md', COPY / 'docs/api.md')
CASES = [
 ('shutdown', 'deck/control_api.py', '            self.server.close()\n            if self.server.on_shutdown', '            pass\n            if self.server.on_shutdown'),
 ('token-check', 'deck/control_api.py', 'if self.server.token_required and not hmac.compare_digest', 'if False and not hmac.compare_digest'),
 ('off-loopback-no-token', 'deck/control_api.py', 'if self.token_required and not controller.settings.api_token:', 'if False:'),
 ('start-worker', 'deck/control_api.py', '            self.thread.start()\n            return self.status()', '            return self.status()'),
 ('stop-event', 'deck/control_api.py', '    def stop(self):\n        with self.lock:\n            self.stop_event.set()', '    def stop(self):\n        with self.lock:\n            pass'),
 ('restart-stops-first', 'deck/control_api.py', '    def restart(self):\n        with self.lock:\n            self.stop()', '    def restart(self):\n        with self.lock:\n            pass'),
 ('seq-telemetry', 'deck/control_api.py', '            self.seq = seq', '            self.seq = 0'),
 ('heartbeat-telemetry', 'deck/control_api.py', '                self.heartbeat_at = heartbeat_at', '                self.heartbeat_at = None'),
 ('running-truth', 'deck/control_api.py', '"running": self.thread is not None and self.thread.is_alive(),', '"running": False,'),
 ('persist-settings', 'deck/control_api.py', '            write_runtime_settings(self.settings_path, updated)', '            pass'),
 ('publish-settings', 'deck/control_api.py', '            self.settings = updated', '            pass'),
 ('active-order', 'deck/control_api.py', 'updated = with_active_targets(current, body["names"])', 'updated = with_active_targets(current, sorted(body["names"]))'),
 ('port-override', 'deck/control_api.py', '"port": body.get("port", current.default_port)', '"port": current.default_port'),
 ('rename-selection', 'deck/local_config.py', 'active_targets=[normalized if name == settings.presets[index].name else name', 'active_targets=[name if name == settings.presets[index].name else name'),
 ('delete-target', 'deck/control_api.py', 'updated = with_deleted_preset(current, matches[0])', 'updated = current'),
 ('replace-list', 'deck/control_api.py', '"presets": entries, "active_targets": []', '"presets": asdict(current)["presets"], "active_targets": []'),
 ('bindings-reload', 'deck/control_api.py', '            self.bindings = document\n            if running:', '            self.bindings = self.bindings\n            if running:'),
 ('loaded-snapshot', 'deck/control_api.py', 'return copy.deepcopy(controller.bindings)', 'return controller._read_bindings(controller.settings.bindings_path)'),
 ('restart-new-settings', 'deck/control_api.py', 'if running and restart_needed:', 'if False:'),
 ('live-token-rotation', 'deck/control_api.py', 'token = self.server.controller.settings.api_token or ""', 'token = "old-token"'),
 ('menu-stale-snapshot', 'deck/control_api.py', 'if expected is not None and expected != self.settings:', 'if False:'),
 ('tty-preserve-token', 'deck/local_config.py', '    return replace(\n        settings,\n        device_id=normalized,', '    return DeckRuntimeSettings(\n        device_id=normalized,'),
 ('skip-stops-single', 'deck/control_learn.py', '            if self.single:', '            if False:'),
 ('learn-save', 'deck/control_learn.py', '            write_bindings(self.settings.bindings_path, self.settings.profile_name or "default", updated)', '            pass'),
 ('learn-cancel-no-save', 'deck/control_learn.py', '    def cancel(self):\n        with self.lock:', '    def cancel(self):\n        write_bindings(self.settings.bindings_path, "default", {})\n        with self.lock:'),
 ('learn-duplicate', 'deck/control_learn.py', 'if any(token == self.candidate and name != action for name, token in self.bindings.items()):', 'if False:'),
 ('learn-candidate', 'deck/control_learn.py', '                                        self.candidate = event.keycode', '                                        self.candidate = "wrong"'),
 ('learn-single-preserve', 'deck/control_learn.py', 'self.bindings = load_existing_bindings(settings.bindings_path) if self.single else {}', 'self.bindings = {}'),
 ('learn-sender-conflict', 'deck/control_api.py', 'if self.learn is not None and self.learn.active:\n                raise ValueError("cancel or finish learning before starting the sender")', 'if False:\n                raise ValueError("cancel or finish learning before starting the sender")'),
 ('select-stop-path', 'deck/xinput_send.py', '                        if stop_event.is_set():\n                            break', '                        if False:\n                            break'),
 ('sender-real-telemetry', 'deck/xinput_send.py', '            on_status(seq=seq, heartbeat_at=heartbeat_at)', '            pass'),
 ('selector-close', 'deck/xinput_send.py', '                        selector.close()', '                        pass'),
 ('listener-error-close', 'deck/xinput_send.py', '        resources.callback(listener.close)', '        pass'),
 ('cli-activate', 'deck/deckctl.py', 'method, path = "POST", "/api/targets/active"', 'method, path = "GET", "/api/targets"'),
 ('json-errors', 'deck/control_api.py', 'return self._json(400, {"error": str(exc) or "invalid request"})', 'return self._json(200, {"error": str(exc) or "invalid request"})'),
]
COMMAND = [sys.executable, '-m', 'unittest', 'tests.test_deck_control_api', 'tests.test_deck_fanout_launch']
results = []
def run(name):
    env = {**os.environ, 'TMPDIR': '/tmp/sdcore-s5', 'PYTHONDONTWRITEBYTECODE': '1'}
    command = COMMAND if name != "stop-event" else [sys.executable, "-m", "unittest", "tests.test_deck_control_api.DeckControlAPITests.test_stop_sets_event_before_join"]
    result = subprocess.run(command, cwd=COPY, env=env, capture_output=True, text=True, timeout=35)
    (SCRATCH / (name + '.log')).write_text(result.stdout + result.stderr)
    return result.returncode
assert run('pristine') == 0, 'pristine controls must pass'
for name, path, old, new in CASES:
    target = COPY / path
    original = target.read_text()
    assert original.count(old) == 1, (name, original.count(old))
    target.write_text(original.replace(old, new))
    try:
        code = run(name)
        assert code != 0, f'mutation survived: {name}'
        results.append({'mutation': name, 'result': 'RED', 'exit_code': code})
        print(name + ': RED', flush=True)
    finally:
        target.write_text(original)
assert run('restored') == 0, 'restored controls must pass'
result = {'pristine': 'GREEN', 'mutations': results, 'restored': 'GREEN'}
(SCRATCH / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
print(f'PASS: {len(results)} mutation reds; pristine/restored green', flush=True)
