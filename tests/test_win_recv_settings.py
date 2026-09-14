"""Source-entrypoint tests for local identity and last-good reload behavior."""

import contextlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.test_receiver import FakeMidiOut
from windows import win_recv
from windows.bridge_settings import BridgeSettings
from windows.config import ConfigError
from windows.receiver import serve_forever
from windows.ui_server import MappingUIServer


class BridgeStartupSettingsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.base = self.root / "windows_midi_map.json"
        self.local = self.root / "bridge.local.json"
        self.macbook = {"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 36}}}
        self.windows = {"mappings": {"BTN_A": {"type": "note", "channel": 1, "note": 80}}}
        self.base.write_text(json.dumps({"sections": {
            "macbook": self.macbook, "windows": self.windows,
        }}))
        self.local.write_text(json.dumps({"preset_section": "macbook"}))
        self.servers = []
        self.midi = FakeMidiOut()
        self.midi.port_name = "resolved output"
        self.midi.port_index = 2

    def boot(self, check, *extra, ui=False):
        argv = ["--map", str(self.base), "--no-engines", "--no-pulse", "--no-osc-relay"]
        if not ui:
            argv.append("--no-ui")
        argv.extend(extra)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(win_recv, "open_midi_output", return_value=self.midi))
            stack.enter_context(patch.object(win_recv, "open_midi_input", return_value=None))
            stack.enter_context(patch.object(win_recv, "serve_forever", side_effect=check))
            stack.enter_context(patch.object(win_recv, "_open_browser_delayed"))
            stack.enter_context(patch.object(MappingUIServer, "run_in_thread", lambda server: self.servers.append(server)))
            stack.enter_context(patch.dict(sys.modules, {"windows.tray": types.SimpleNamespace(ReceiverTray=Mock())}))
            self.assertEqual(win_recv.main(argv), 0)

    def emit(self, receiver, seq=1):
        receiver.handle_datagram(
            json.dumps({"action": "BTN_A", "state": "down", "seq": seq}).encode(),
            ("127.0.0.1", 12345),
        )

    def test_startup_reads_machine_file(self):
        self.boot(lambda host, port, receiver, **kw: self.emit(receiver))
        self.assertEqual(self.midi.calls[0], ("note_on", 0, 36, 127))

    def test_argv_section_beats_machine_file_without_overwriting_it(self):
        before = self.local.read_bytes()
        self.boot(lambda host, port, receiver, **kw: self.emit(receiver), "--preset-section", "windows")
        self.assertEqual(self.midi.calls[0], ("note_on", 1, 80, 127))
        self.assertEqual(self.local.read_bytes(), before)

    def test_old_install_with_no_machine_file_and_legacy_preset_boots(self):
        self.local.unlink()
        self.base.write_text(json.dumps(self.macbook))
        self.boot(lambda host, port, receiver, **kw: self.emit(receiver))
        self.assertEqual(self.midi.calls[0], ("note_on", 0, 36, 127))
        self.assertFalse(self.local.exists())

    def test_put_switch_is_used_by_real_reload_loop_and_next_startup(self):
        def check(host, port, receiver, **kw):
            client = self.servers[-1]._app.test_client()
            self.assertEqual(client.get("/api/settings").get_json(), {
                "preset_section": "macbook", "listen": "127.0.0.1:49000",
                "midi_port": "resolved output", "feedback_port": None, "pulse_port": None,
                "ui_port": 7900, "map_path": str((self.root / "presets/default.json").resolve()),
            })
            response = client.put("/api/settings", json={"preset_section": "windows"})
            self.assertEqual(response.status_code, 200)
            self.run_receiver_loop(host, port, receiver, **kw)
            self.assertEqual(self.midi.calls[:2], [
                ("note_on", 1, 80, 127), ("note_off", 1, 80, 0),
            ])
        self.boot(check, "--listen", "127.0.0.1:49000", "--ui-port", "7900", ui=True)
        self.assertEqual(json.loads(self.local.read_text()), {"preset_section": "windows"})
        self.midi.calls.clear()
        self.boot(lambda host, port, receiver, **kw: self.emit(receiver))
        self.assertEqual(self.midi.calls[0], ("note_on", 1, 80, 127))

    def run_receiver_loop(self, host, port, receiver, **kw):
        sock = Mock()
        sock.recvfrom.side_effect = [
            (b'{"action":"BTN_A","state":"down","seq":1}', ("127.0.0.1", 12345)),
            (b'{"action":"BTN_A","state":"up","seq":2}', ("127.0.0.1", 12345)),
            KeyboardInterrupt(),
        ]
        with patch("windows.receiver.socket.socket", return_value=sock):
            serve_forever(host, port, receiver, **kw)

    def test_bad_active_preset_switch_keeps_last_good_midi(self):
        def check(host, port, receiver, **kw):
            presets = self.root / "presets"
            (presets / "bad.json").write_text(json.dumps({"sections": {"windows": self.windows}}))
            client = self.servers[-1]._app.test_client()
            response = client.post("/api/presets/load", json={"name": "bad.json"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(kw["reload_event"].is_set())
            self.run_receiver_loop(host, port, receiver, **kw)
            self.assertEqual(self.midi.calls[:2], [
                ("note_on", 0, 36, 127), ("note_off", 0, 36, 0),
            ])
        self.boot(check, ui=True)

    def test_missing_selection_on_sectioned_startup_names_sections(self):
        import io
        # An explicitly cleared selection remains an error on every platform.
        self.local.write_text('{"preset_section": null}')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            win_recv.main(["--map", str(self.base), "--no-ui"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("available sections: macbook, windows", stderr.getvalue())

    def test_local_settings_validation_and_windows_bom(self):
        for raw in ("not json", "[]", '{"preset_section": false}', '{"preset_section":"bad/name"}'):
            with self.subTest(raw=raw):
                self.local.write_text(raw)
                with self.assertRaises(ConfigError):
                    BridgeSettings.load(self.local)
                self.assertEqual(BridgeSettings.load(self.local, "windows").preset_section, "windows")
        self.local.write_text('{"preset_section":"macbook"}', encoding="utf-8-sig")
        self.assertEqual(BridgeSettings.load(self.local).preset_section, "macbook")


if __name__ == "__main__":
    unittest.main()
