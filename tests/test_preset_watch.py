"""Disk changes must reach the real bridge reload path, not just a log."""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from windows.preset_watch import PresetWatcher
from tests import test_win_recv_settings as startup
from windows import win_recv
from windows.midi import DryRunMidiOut
from windows.receiver import ActionReceiver, serve_forever


class FakeEvent:
    def __init__(self):
        self.signal = threading.Event()
        self.count = 0
        self.when = None

    def set(self):
        self.count += 1
        self.when = time.monotonic()
        self.signal.set()


class PresetWatcherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.presets = self.root / 'presets'
        self.presets.mkdir()
        self.preset = self.presets / 'Show.json'
        self.preset.write_text('{"mappings":{}}')
        self.event = FakeEvent()

    def watch(self, **kwargs):
        watcher = PresetWatcher(self.presets, self.root / 'bridge.local.json', self.event, **kwargs)
        watcher.start()
        self.addCleanup(lambda: (watcher.stop(), watcher.join(1)))
        return watcher

    def test_default_poll_change_within_one_second_and_daemon(self):
        watcher = self.watch()
        self.assertTrue(watcher.daemon)
        self.preset.write_text('{"mappings":{}, "engines":{}}')
        self.assertTrue(self.event.signal.wait(1))

    def test_touch_add_delete_marker_and_local_settings(self):
        self.watch(poll_interval=0.01, debounce=0.02)
        before = self.preset.read_bytes()
        stamp = self.preset.stat().st_mtime_ns + 1000000000
        operations = [
            lambda: os.utime(self.preset, ns=(stamp, stamp)),
            lambda: (self.presets / 'Other.json').write_text('{}'),
            lambda: (self.presets / 'Other.json').unlink(),
            lambda: (self.presets / '.active').write_text('Show.json'),
            lambda: (self.root / 'bridge.local.json').write_text('{"preset_section":"macbook"}'),
        ]
        for operation in operations:
            self.event.signal.clear()
            operation()
            self.assertTrue(self.event.signal.wait(1))
        self.assertEqual(self.preset.read_bytes(), before)

    def test_temp_files_ignored_and_rename_debounced(self):
        watcher = PresetWatcher(self.presets, self.root / 'bridge.local.json', self.event,
                                poll_interval=0.01, debounce=0.15)
        tmp = self.presets / '.preset-sync.tmp'
        tmp.write_text('{')
        now = 0.0
        steps = iter((0.01, 0.02, 0.10, 0.20, 0.26))
        def advance(_delay):
            nonlocal now
            try:
                now = next(steps)
            except StopIteration:
                return True
            self.assertEqual(self.event.count, 0)
            if now == 0.02:
                tmp.replace(self.preset)
            elif now == 0.10:
                self.preset.write_text('{"mappings":{}}')
            return False
        # Drive the real polling loop over real files, with deterministic quiet
        # boundaries. A separate daemon-thread test checks the real 1 s bound.
        with patch.object(watcher._stop_event, 'wait', side_effect=advance), \
             patch('windows.preset_watch.time.monotonic', side_effect=lambda:now):
            watcher.run()
        self.assertTrue(self.event.signal.is_set())
        self.assertEqual(self.event.count, 1)
        self.assertEqual(self.event.when, 0.26)
        self.assertEqual(json.loads(self.preset.read_text()), {'mappings':{}})

    def test_poll_exception_recovers_and_keeps_detecting(self):
        watcher = self.watch(poll_interval=0.01, debounce=0.02)
        real = watcher._scan
        with patch.object(watcher, '_scan', side_effect=[RuntimeError('scan failed'), real()]) as scan:
            deadline = time.monotonic() + 1
            while scan.call_count < 2 and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertGreaterEqual(scan.call_count, 2)
        self.preset.write_text('{}')
        self.assertTrue(self.event.signal.wait(1))
        self.assertTrue(watcher.is_alive())

    def test_event_exception_is_retried(self):
        original = self.event.set
        failed = False
        def fail_once():
            nonlocal failed
            if not failed:
                failed = True
                raise RuntimeError('event failed')
            original()
        with patch.object(self.event, 'set', side_effect=fail_once):
            self.watch(poll_interval=0.01, debounce=0.02)
            self.preset.write_text('{}')
            self.assertTrue(self.event.signal.wait(1))

    def test_initial_scan_failure_retries_without_stopping_startup(self):
        with patch.object(PresetWatcher, '_scan', side_effect=OSError('initial scan failed')):
            watcher = PresetWatcher(self.presets, self.root / 'bridge.local.json', self.event,
                                    poll_interval=0.01, debounce=0.02)
        watcher.start()
        self.addCleanup(lambda: (watcher.stop(), watcher.join(1)))
        self.assertTrue(self.event.signal.wait(1))
        self.assertTrue(watcher.is_alive())

    def test_invalid_intervals_rejected(self):
        for interval in (0, -1, float('nan'), float('inf')):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                PresetWatcher(self.presets, self.root / 'bridge.local.json', self.event,
                              poll_interval=interval)


class ReloadIntegrationTests(unittest.TestCase):
    def run_receiver_loop(self, host, port, receiver, **kw):
        seq = getattr(self, '_seq', 0) + 2
        self._seq = seq
        sock = Mock()
        sock.recvfrom.side_effect = [
            (json.dumps({'action':'BTN_A','state':'down','seq':seq}).encode(), ('127.0.0.1', 12345)),
            (json.dumps({'action':'BTN_A','state':'up','seq':seq+1}).encode(), ('127.0.0.1', 12345)),
            KeyboardInterrupt(),
        ]
        with patch('windows.receiver.socket.socket', return_value=sock):
            serve_forever(host, port, receiver, **kw)
    # Reuse the established source-main harness without changing any old assertions.
    def setUp(self):
        startup.BridgeStartupSettingsTests.setUp(self)
        self.midi = DryRunMidiOut()

    def boot(self, check, *extra, ui=True):
        return startup.BridgeStartupSettingsTests.boot(self, check, '--preset-poll-interval', '0.01', *extra, ui=ui)

    def test_save_and_disk_reload_versions_and_real_midi(self):
        def check(host, port, receiver, **kw):
            self.assertIsInstance(receiver, ActionReceiver)
            client = self.servers[-1]._app.test_client()
            self.assertEqual(client.get('/api/state-version').get_json(), 0)
            self.macbook['mappings']['BTN_A']['note'] = 45
            response = client.post('/api/save', json={'section':'macbook', 'document':self.macbook})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get('/api/state-version').get_json(), 0)
            with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                self.run_receiver_loop(host, port, receiver, **kw)
                emitted.assert_called_with(0, 45, 127)
            version = client.get('/api/state-version').get_json()
            self.assertEqual(version, 1)
            # Wait out the watcher's duplicate observation of the API write.
            self.assertTrue(kw['reload_event'].wait(1))
            kw['reload_event'].clear()
            path = self.root / 'presets/default.json'
            raw = json.loads(path.read_text())
            raw['sections']['macbook']['mappings']['BTN_A']['note'] = 57
            path.write_text(json.dumps(raw))
            self.assertTrue(kw['reload_event'].wait(1))
            with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                self.run_receiver_loop(host, port, receiver, **kw)
                emitted.assert_called_with(0, 57, 127)
            self.assertEqual(client.get('/api/state-version').get_json(), version + 1)
        self.boot(check)

    def test_half_write_keeps_last_good_then_full_write_applies(self):
        def check(host, port, receiver, **kw):
            client = self.servers[-1]._app.test_client()
            path = self.root / 'presets/default.json'
            raw = json.loads(path.read_text())
            path.write_text('{"sections":')
            self.assertTrue(kw['reload_event'].wait(1))
            with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                self.run_receiver_loop(host, port, receiver, **kw)
                emitted.assert_called_with(0, 36, 127)
            self.assertEqual(client.get('/api/state-version').get_json(), 0)
            raw['sections']['macbook']['mappings']['BTN_A']['note'] = 61
            path.write_text(json.dumps(raw))
            self.assertTrue(kw['reload_event'].wait(1))
            with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                self.run_receiver_loop(host, port, receiver, **kw)
                emitted.assert_called_with(0, 61, 127)
            self.assertEqual(client.get('/api/state-version').get_json(), 1)
        self.boot(check)

    def test_explicit_reload_requests_event_without_claiming_application(self):
        def check(host, port, receiver, **kw):
            client = self.servers[-1]._app.test_client()
            response = client.post('/api/reload')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {'ok': True})
            self.assertTrue(kw['reload_event'].is_set())
            self.assertEqual(client.get('/api/state-version').get_json(), 0)
            self.run_receiver_loop(host, port, receiver, **kw)
            self.assertEqual(client.get('/api/state-version').get_json(), 1)
        self.boot(check)

    def test_disk_identity_changes_and_bad_settings_keep_last_good(self):
        def check(host, port, receiver, **kw):
            client = self.servers[-1]._app.test_client()
            for contents, note, version, section in [
                ('{"preset_section":"windows"}', 80, 1, 'windows'),
                ('{', 80, 1, 'windows'),
                ('{"preset_section":"missing"}', 80, 1, 'windows'),
                ('{"preset_section":"macbook"}', 36, 2, 'macbook'),
            ]:
                self.local.write_text(contents)
                self.assertTrue(kw['reload_event'].wait(1))
                with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                    self.run_receiver_loop(host, port, receiver, **kw)
                    self.assertEqual(emitted.call_args.args[1], note)
                self.assertEqual(client.get('/api/state-version').get_json(), version)
                self.assertEqual(client.get('/api/settings').get_json()['preset_section'], section)
        self.boot(check)

    def test_watcher_runs_in_tray_path_and_stops_with_main(self):
        import sys
        import types
        def check(host, port, receiver, **kw):
            (self.root / 'presets/default.json').write_text(json.dumps(self.macbook))
            self.assertTrue(kw['reload_event'].wait(1))
            self.run_receiver_loop(host, port, receiver, **kw)
            self.assertEqual(self.servers[-1]._app.test_client().get('/api/state-version').get_json(), 1)
        # The existing boot helper provides its own tray stub; wrap main's real
        # tray import while retaining the real watcher, loader and receiver.
        with patch.object(win_recv, 'open_midi_output', return_value=self.midi), \
             patch.object(win_recv, 'open_midi_input', return_value=None), \
             patch.object(win_recv, 'serve_forever', side_effect=check), \
             patch('windows.ui_server.MappingUIServer.run_in_thread', lambda server:self.servers.append(server)), \
             patch.dict(sys.modules, {'windows.tray':types.SimpleNamespace(
                 run_tray_mode=lambda **kw:kw['run_bridge'](),
                 setup_log_tee=lambda:None, acquire_single_instance_lock=lambda:(None,True))}):
            win_recv.main(['--map',str(self.base),'--no-engines','--no-pulse','--no-osc-relay',
                           '--tray','--preset-poll-interval','0.01'])
        self.assertFalse(any(t.name == 'preset-watch' for t in threading.enumerate()))

    def test_no_ui_bridge_still_watches_and_applies(self):
        def check(host, port, receiver, **kw):
            (self.root / 'presets/default.json').write_text(json.dumps(self.windows))
            self.assertTrue(kw['reload_event'].wait(1))
            with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                self.run_receiver_loop(host, port, receiver, **kw)
                emitted.assert_called_with(1, 80, 127)
            self.assertEqual(receiver.state_version, 1)
        self.boot(check, ui=False)
        self.assertFalse(any(t.name == 'preset-watch' for t in threading.enumerate()))

    def test_disk_active_marker_applies_new_scene(self):
        def check(host, port, receiver, **kw):
            presets = self.root / 'presets'
            (presets / 'Other.json').write_text(json.dumps(self.windows))
            (presets / '.active').write_text('Other.json')
            self.assertTrue(kw['reload_event'].wait(1))
            with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                self.run_receiver_loop(host, port, receiver, **kw)
                emitted.assert_called_with(1, 80, 127)
            client = self.servers[-1]._app.test_client()
            self.assertEqual(client.get('/api/state-version').get_json(), 1)
            self.assertEqual(Path(client.get('/api/settings').get_json()['map_path']),
                             (presets / 'Other.json').resolve())
        self.boot(check)

    def test_unchanged_settings_preserve_argv_on_explicit_reload(self):
        def check(host, port, receiver, **kw):
            client = self.servers[-1]._app.test_client()
            client.post('/api/reload')
            with patch.object(self.midi, 'note_on', wraps=self.midi.note_on) as emitted:
                self.run_receiver_loop(host, port, receiver, **kw)
                emitted.assert_called_with(1, 80, 127)
            self.assertEqual(client.get('/api/settings').get_json()['preset_section'], 'windows')
        self.boot(check, '--preset-section', 'windows')
