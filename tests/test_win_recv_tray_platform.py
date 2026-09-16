"""sdauto A3: no sidecar tray on macOS (F5/F2) and the --no-browser flag."""

import contextlib
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from windows import win_recv
from windows.midi import DryRunMidiOut
from windows.ui_server import MappingUIServer


class ShouldStartReceiverTrayTests(unittest.TestCase):
    def test_platform_rule(self):
        self.assertTrue(win_recv._should_start_receiver_tray("win32", False))
        self.assertFalse(win_recv._should_start_receiver_tray("darwin", False))
        self.assertTrue(win_recv._should_start_receiver_tray("linux", False))

    def test_tray_mode_never_starts_the_sidecar(self):
        for platform in ("win32", "darwin", "linux"):
            with self.subTest(platform=platform):
                self.assertFalse(win_recv._should_start_receiver_tray(platform, True))


class MainTrayAndBrowserTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name) / "map.json"
        self.base.write_text('{"mappings":{}}')

    def boot(self, platform, *extra, loop=None):
        """Run main() with a mocked windows.tray on an injected sys.platform."""
        fake_tray = Mock()
        fake_tray.acquire_single_instance_lock.return_value = (None, True)
        fake_tray.setup_log_tee.return_value = None
        fake_tray.run_tray_mode.side_effect = lambda **kw: kw["run_bridge"]()
        seen = {}

        def serve(host, port, receiver, **kw):
            seen["receiver"] = receiver
            seen["tray_at_serve"] = list(fake_tray.ReceiverTray.call_args_list)
            if loop is not None:
                loop(receiver)

        midi = DryRunMidiOut()
        argv = ["--map", str(self.base), "--no-engines", "--no-pulse", "--no-osc-relay", *extra]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {"windows.tray": fake_tray}))
            stack.enter_context(patch.object(win_recv.sys, "platform", platform))
            stack.enter_context(patch.object(win_recv, "open_midi_output", return_value=midi))
            stack.enter_context(patch.object(win_recv, "open_midi_input", return_value=None))
            stack.enter_context(patch.object(win_recv, "serve_forever", side_effect=serve))
            stack.enter_context(patch.object(MappingUIServer, "run_in_thread", lambda s: None))
            stack.enter_context(patch.object(MappingUIServer, "stop"))
            seen["rc"] = win_recv.main(argv)
        return fake_tray, seen

    def test_darwin_non_tray_never_constructs_or_stops_receiver_tray(self):
        fake_tray, seen = self.boot("darwin", "--no-browser")
        self.assertEqual(seen["rc"], 0)
        self.assertEqual(fake_tray.ReceiverTray.call_count, 0)
        self.assertEqual(fake_tray.ReceiverTray.return_value.run_in_thread.call_count, 0)
        self.assertEqual(fake_tray.ReceiverTray.return_value.stop.call_count, 0)
        self.assertIn("receiver", seen)

    def test_win32_non_tray_constructs_runs_and_stops_receiver_tray(self):
        fake_tray, seen = self.boot("win32", "--no-browser")
        self.assertEqual(seen["rc"], 0)
        receiver = seen["receiver"]
        self.assertEqual(seen["tray_at_serve"], [
            call(ui_url="http://127.0.0.1:7723", quit_callback=receiver.request_shutdown),
        ])
        tray = fake_tray.ReceiverTray.return_value
        tray.run_in_thread.assert_called_once_with()
        tray.stop.assert_called_once_with()

    def test_darwin_tray_mode_is_refused_with_exit_2(self):
        """P0(c): --tray on darwin is refused before any tray module is touched.

        REPLACES test_darwin_tray_mode_still_runs_tray_mode, whose assertion
        (darwin --tray runs tray mode, rc 0) is the behaviour P0 removes.
        Nothing on the Mac launches --tray: scripts/mac/run_receiver.command
        line 40 already carries a comment forbidding it, and a repo-wide grep
        of mac/ and scripts/mac/ found no launch.
        """
        fake_tray, seen = self.boot("darwin", "--tray")
        self.assertEqual(seen["rc"], win_recv.TRAY_UNSUPPORTED_EXIT_CODE)
        self.assertEqual(seen["rc"], 2)
        self.assertEqual(fake_tray.run_tray_mode.call_count, 0)
        self.assertEqual(fake_tray.ReceiverTray.call_count, 0)
        # Refused BEFORE the log tee and the single-instance mutex, whose name
        # belongs to the INSTALLED Windows tray.
        self.assertEqual(fake_tray.setup_log_tee.call_count, 0)
        self.assertEqual(fake_tray.acquire_single_instance_lock.call_count, 0)
        # ...and before the bridge itself.
        self.assertNotIn("receiver", seen)

    def test_tray_mode_is_allowed_on_win32_and_linux(self):
        for platform in ("win32", "linux"):
            with self.subTest(platform=platform):
                fake_tray, seen = self.boot(platform, "--tray")
                self.assertEqual(seen["rc"], 0)
                self.assertEqual(fake_tray.run_tray_mode.call_count, 1)
                self.assertEqual(
                    fake_tray.run_tray_mode.call_args.kwargs["stop_bridge"],
                    seen["receiver"].request_shutdown,
                )
                self.assertEqual(fake_tray.ReceiverTray.call_count, 0)

    def test_the_refusal_message_is_plain_ascii(self):
        self.assertTrue(win_recv.TRAY_UNSUPPORTED_MESSAGE.isascii())
        self.assertIn("--tray", win_recv.TRAY_UNSUPPORTED_MESSAGE)
        self.assertIn("macOS", win_recv.TRAY_UNSUPPORTED_MESSAGE)

    def _browser_boot(self, *extra):
        def join_browser_threads(receiver):
            for thread in threading.enumerate():
                if thread.name == "browser-open":
                    thread.join(3)

        sleeps = []
        with patch.object(win_recv.webbrowser, "open") as browser_open, \
             patch.object(win_recv.time, "sleep", side_effect=lambda s: sleeps.append(s)):
            _, seen = self.boot("win32", *extra, loop=join_browser_threads)
            # join again after main returns, in case the thread started late
            for thread in threading.enumerate():
                if thread.name == "browser-open":
                    thread.join(3)
        self.assertEqual(seen["rc"], 0)
        return browser_open, sleeps

    def test_no_browser_never_opens_a_browser(self):
        browser_open, sleeps = self._browser_boot("--no-browser")
        self.assertEqual(browser_open.call_count, 0)
        self.assertNotIn(1.2, sleeps)

    def test_without_no_browser_opens_once_after_the_delay(self):
        browser_open, sleeps = self._browser_boot()
        browser_open.assert_called_once_with("http://127.0.0.1:7723")
        self.assertIn(1.2, sleeps)

    def _already_running(self, *extra):
        fake_tray = Mock()
        fake_tray.acquire_single_instance_lock.return_value = (None, False)
        fake_tray.setup_log_tee.return_value = None
        argv = ["--map", str(self.base), "--tray", "--ui-port", "7799", *extra]
        # P0: --tray is refused on darwin, and this exercises the
        # single-instance path, not the platform rule.
        with patch.object(win_recv.sys, "platform", "win32"), \
             patch.dict(sys.modules, {"windows.tray": fake_tray}), \
             patch("webbrowser.open") as browser_open, \
             patch.object(win_recv, "open_midi_output") as open_out, \
             patch.object(win_recv, "serve_forever") as serve:
            rc = win_recv.main(argv)
        self.assertEqual(open_out.call_count, 0)
        self.assertEqual(serve.call_count, 0)
        return rc, browser_open

    def test_already_running_with_no_browser_exits_without_opening(self):
        rc, browser_open = self._already_running("--no-browser")
        self.assertEqual(rc, 0)
        self.assertEqual(browser_open.call_count, 0)

    def test_already_running_without_flag_opens_existing_url(self):
        rc, browser_open = self._already_running()
        self.assertEqual(rc, 0)
        browser_open.assert_called_once_with("http://127.0.0.1:7799")


if __name__ == "__main__":
    unittest.main()
