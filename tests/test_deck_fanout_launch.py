"""Exercise the actual menu, CLI and sender loop with hardware substituted."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from deck import launch_send, xinput_send
from deck.local_config import load_runtime_settings


class DeckFanoutLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings.json"
        self.bindings = Path(self.temp.name) / "bindings.json"
        self.bindings.write_text(json.dumps({"profile_name": "show", "bindings": {"14": "BTN_A"}}))
        self.raw = {"bindings_path": str(self.bindings), "presets": [
            {"name": "PC", "host": "192.0.2.1", "port": 45123},
            {"name": "Mac", "host": "viddymac.local", "port": 45124}]}
        self.path.write_text(json.dumps(self.raw))

    def launch_menu(self, choices):
        with patch("builtins.input", side_effect=choices), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                patch("deck.launch_send.run_sender", return_value=0) as run:
            self.assertEqual(launch_send.main(["--settings", str(self.path)]), 0)
        return run, output.getvalue()

    def test_toggle_save_start_and_relaunch_use_all_saved_hosts(self):
        run, output = self.launch_menu(["m", "invalid", "9", "1", "2", "1", "1", "s", "s"])
        self.assertEqual(json.loads(self.path.read_text())["active_targets"], ["Mac", "PC"])
        self.assertEqual(run.call_args.kwargs["targets"], [("viddymac.local", 45124), ("192.0.2.1", 45123)])
        self.assertIn("[active]", output)
        run_again, _ = self.launch_menu(["s"])
        self.assertEqual(run_again.call_args, run.call_args)

    def test_legacy_menu_starts_one_without_changing_settings(self):
        before = self.path.read_bytes()
        run, _ = self.launch_menu(["2"])
        self.assertEqual(run.call_args.kwargs["targets"], [("viddymac.local", 45124)])
        self.assertEqual(self.path.read_bytes(), before)

    def test_single_selection_clears_previous_multi_selection(self):
        self.path.write_text(json.dumps({**self.raw, "active_targets": ["PC", "Mac"]}))
        run, _ = self.launch_menu(["1"])
        self.assertEqual(run.call_args.kwargs["targets"], [("192.0.2.1", 45123)])
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, [])

    def test_cancel_multi_and_quit_leave_file_unchanged(self):
        before = self.path.read_bytes()
        run, _ = self.launch_menu(["m", "1", "q", "q"])
        run.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_saved_selection_returns_to_single_menu(self):
        self.path.write_text(json.dumps({**self.raw, "active_targets": ["PC"]}))
        def choices():
            yield from ["m", "1", "s"]
            # Observe the saved toggle before selecting one target can also clear it.
            self.assertEqual(load_runtime_settings(str(self.path)).active_targets, [])
            yield "2"
        run, _ = self.launch_menu(choices())
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, [])
        self.assertEqual(run.call_args.kwargs["targets"], [("viddymac.local", 45124)])

    def test_both_cli_spellings_reach_run_sender(self):
        for flag in ["--targets", "--target"]:
            with self.subTest(flag=flag), patch("deck.xinput_send.run_sender", return_value=0) as run:
                self.assertEqual(xinput_send.main(["--device-id", "5", "--bindings", str(self.bindings),
                                                   flag, "a:1,b:2"]), 0)
                self.assertEqual(run.call_args.kwargs["target"], "a:1,b:2")

    def test_actual_sender_loop_all_events_share_seq_across_targets(self):
        targets = [("192.0.2.1", 1), ("192.0.2.2", 2)]
        for kwargs in [{"targets": targets}, {"target": "192.0.2.1:1,192.0.2.2:2"},
                       {"targets": targets, "target": "ignored-because-list-wins"}]:
            with self.subTest(kwargs=kwargs), contextlib.ExitStack() as stack:
                listener = stack.enter_context(patch("deck.xinput_send.Xi2RawListener")).return_value
                listener.read_event.side_effect = [xinput_send.Xi2KeyEvent("14", "down"), None]
                sock = stack.enter_context(patch("deck.xinput_send.socket.socket")).return_value.__enter__.return_value
                stack.enter_context(patch("deck.xinput_send.TerminalNoEcho"))
                axes = stack.enter_context(patch("deck.xinput_send.HidrawAxisReader")).return_value.__enter__.return_value
                axes.drain.side_effect = [{"YAW": 64}, {}]
                selector = stack.enter_context(patch("deck.xinput_send.selectors.DefaultSelector")).return_value
                selector.select.side_effect = [[object()], [], KeyboardInterrupt()]
                stack.enter_context(patch("deck.xinput_send.time.monotonic", side_effect=range(100, 140)))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                result = xinput_send.run_sender(device_id="5", bindings_path=str(self.bindings),
                                                profile_name=None, profile_hash=None, **kwargs)
                self.assertEqual(result, 0)
                calls = sock.sendto.call_args_list
                self.assertEqual([c.args[1] for c in calls], targets * 3)
                payloads = [json.loads(c.args[0]) for c in calls]
                self.assertEqual([p["seq"] for p in payloads], [1, 1, 2, 2, 3, 3])
                self.assertEqual([p["kind"] for p in payloads],
                                 ["action", "action", "axis", "axis", "heartbeat", "heartbeat"])
                for i in [0, 2, 4]:
                    self.assertEqual(calls[i].args[0], calls[i + 1].args[0])
                listener.close.assert_called_once()

    def test_invalid_or_empty_targets_stop_before_opening_hardware(self):
        for kwargs in [{"targets": []}, {"target": "bad"}, {}, {"targets": [("host", 0)]}]:
            with self.subTest(kwargs=kwargs), patch("deck.xinput_send.Xi2RawListener") as listener, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(xinput_send.run_sender(device_id="5", bindings_path=str(self.bindings),
                                                        profile_name=None, profile_hash=None, **kwargs), 2)
                listener.assert_not_called()

    def test_native_libraries_loaded_on_listener_open_and_cached(self):
        x11, xi = MagicMock(), MagicMock()
        x11.XOpenDisplay.return_value = 0
        with patch("deck.xinput_send._LIB_X11", None), patch("deck.xinput_send._LIB_XI", None), \
                patch("deck.xinput_send._load_library", side_effect=[x11, xi]) as load:
            for _ in range(2):
                with self.assertRaisesRegex(OSError, "failed to open X display"):
                    xinput_send.Xi2RawListener(5)
            self.assertEqual([c.args[0] for c in load.call_args_list], ["X11", "Xi"])
            self.assertEqual(x11.XOpenDisplay.call_count, 2)


if __name__ == "__main__":
    unittest.main()
