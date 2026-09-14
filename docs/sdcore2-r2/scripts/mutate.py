"""R2 behavior reversions, each with pristine and byte-equal restored controls."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path('/tmp/sdcore-r2')
SCRATCH.mkdir(exist_ok=True)
PYTHON = ROOT / '.venv/bin/python'
API = 'tests.test_ui_server.BridgeShutdownApiTests.'
LOOP = 'tests.test_bridge_shutdown.BridgeShutdownTests.'
CASES = [
    ('route-missing', 'windows/ui_server.py', '@app.route("/api/shutdown", methods=["POST"])',
     '@app.route("/api/removed-shutdown", methods=["POST"])', API + 'test_shutdown_route_is_registered_for_post_only'),
    ('loopback-guard-missing', 'windows/ui_server.py', 'if not loopback:', 'if False:',
     API + 'test_shutdown_refuses_non_loopback_even_with_forwarded_header'),
    ('callback-missing', 'windows/ui_server.py', '                    self.shutdown_fn()', '                    pass',
     API + 'test_shutdown_sets_stop_event_and_returns_202'),
    ('idempotence-missing', 'windows/ui_server.py', 'if not self._stopping:', 'if True:',
     API + 'test_shutdown_is_idempotent'),
    ('stop-event-ignored', 'windows/receiver.py', 'while not receiver.stop_event.is_set():', 'while True:',
     LOOP + 'test_real_receiver_shutdown_releases_notes_cc_and_udp_within_three_seconds'),
    ('release-missing', 'windows/receiver.py', '    finally:\n        receiver.release_all()\n', '    finally:\n',
     LOOP + 'test_real_receiver_shutdown_releases_notes_cc_and_udp_within_three_seconds'),
    ('release-after-engines', 'windows/receiver.py',
     '        receiver.release_all()\n        if engine_registry is not None:\n            engine_registry.shutdown()',
     '        if engine_registry is not None:\n            engine_registry.shutdown()\n        receiver.release_all()',
     LOOP + 'test_shutdown_releases_before_engines_stop_and_closes_inputs'),
    ('udp-close-missing', 'windows/receiver.py', '        sock.close()', '        pass',
     LOOP + 'test_real_receiver_shutdown_releases_notes_cc_and_udp_within_three_seconds'),
    ('reply-wait-missing', 'windows/ui_server.py', 'self._http_server.daemon_threads = False',
     'self._http_server.daemon_threads = True', LOOP + 'test_http_stop_waits_for_shutdown_reply_and_releases_port'),
    ('http-close-missing', 'windows/win_recv.py', '                ui_server.stop()', '                pass',
     LOOP + 'test_main_wires_both_tray_modes_to_the_http_shutdown_function'),
    ('tray-callback-missing', 'windows/win_recv.py', 'stop_bridge=receiver.request_shutdown,', 'stop_bridge=None,',
     LOOP + 'test_main_wires_both_tray_modes_to_the_http_shutdown_function'),
    ('tray-join-missing', 'windows/tray.py', '            self._bridge_thread.join()', '            pass',
     LOOP + 'test_tray_quit_waits_for_bridge_cleanup_without_forced_exit'),
    ('tray-early-exit-guard-missing', 'windows/tray.py',
     'if self._bridge_thread is not None and not self._bridge_thread.is_alive():', 'if False:',
     LOOP + 'test_tray_ready_after_early_bridge_exit_stops_immediately'),
]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='mutation-') as tmp:
    tree = Path(tmp)
    with tarfile.open(fileobj=io.BytesIO(git('archive', 'HEAD'))) as archive:
        archive.extractall(tree, filter='data')
    # Before commit, copy only this link's candidate paths, never ignored config.
    for name in ['windows/receiver.py', 'windows/ui_server.py', 'windows/win_recv.py',
                 'windows/tray.py', 'tests/test_ui_server.py', 'tests/test_bridge_shutdown.py', 'docs/api.md']:
        (tree / name).write_bytes((ROOT / name).read_bytes())
    env = {**os.environ, 'TMPDIR': str(SCRATCH), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(tree)}

    def run(label, test, green):
        result = subprocess.run([str(PYTHON), '-B', '-m', 'unittest', test], cwd=tree,
                                env=env, capture_output=True, text=True, timeout=15)
        (SCRATCH / (label + '.log')).write_text(result.stdout + result.stderr)
        assert (result.returncode == 0) == green, (label, result.stdout, result.stderr)
        print(label, 'GREEN' if green else 'RED', flush=True)

    for label, name, anchor, replacement, test in CASES:
        path = tree / name
        before = path.read_bytes()
        assert before.decode().count(anchor) == 1, (label, 'anchor is not unique')
        run(label + '-pristine', test, True)
        try:
            path.write_text(before.decode().replace(anchor, replacement))
            run(label + '-mutant', test, False)
        finally:
            path.write_bytes(before)
        run(label + '-restored', test, True)
        assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(before).digest()
    print('ALL_13_BITE; every restored file byte-equal', flush=True)
