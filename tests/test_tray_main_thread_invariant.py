"""P0(b): the tray main-thread invariant, locked against the REAL tray module.

Every automated run so far set PYSTRAY_BACKEND=dummy, which removes the real
tray and so hid the macOS sidecar spin that sdauto A3 fixed (94.3% of one core
to 0.3%) - and A3's own tests mock `windows.tray` wholesale, so they cannot see
which thread an Icon runs on.

This test mocks ONE thing: `pystray.Icon`. The real `windows.tray` code
(ReceiverTray, TrayApp, run_tray_mode) and the real `win_recv.main` wiring run.
`setup_log_tee` and `acquire_single_instance_lock` are mocked because the
single-instance mutex name belongs to the INSTALLED Windows tray; nothing here
may ever take it.

Locked invariants:
  darwin,  no --tray : no Icon is ever constructed (A3's fix).
  win32,   no --tray : an Icon IS constructed and runs OFF the main thread.
  linux,   no --tray : likewise (the intended sidecar design).
  win32/linux --tray : the Icon runs ON the main thread (tray mode owns it).
  darwin      --tray : refused, exit 2 - see test_win_recv_tray_platform.

Thread joins are deterministic: the stub Icon signals when `run()` is entered
and `stop()`/`setup` end it. No sleep is used as synchronisation.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from windows import tray as real_tray
from windows import win_recv
from windows.midi import DryRunMidiOut
from windows.ui_server import MappingUIServer


class RecordingIcon:
    """Stand-in for pystray.Icon that records the thread its run() used."""

    instances: list["RecordingIcon"] = []

    def __init__(self, name=None, icon=None, title=None, menu=None, **kwargs):
        self.name = name
        self.title = title
        self.visible = False
        self.run_thread: threading.Thread | None = None
        self.run_entered = threading.Event()
        self.stopped = threading.Event()
        self._release = threading.Event()
        RecordingIcon.instances.append(self)

    def run(self, setup=None):
        self.run_thread = threading.current_thread()
        self.run_entered.set()
        if setup is not None:
            setup(self)
        # Block until stop() - exactly like a real tray event loop - so the
        # "which thread am I on" question is asked of a LIVE loop, not a
        # returned one. No sleep: a real Event does the waiting.
        self._release.wait(10)

    def stop(self):
        self.stopped.set()
        self._release.set()

    def notify(self, *args, **kwargs):
        pass

    @classmethod
    def reset(cls):
        cls.instances = []


class TrayMainThreadInvariantTests(unittest.TestCase):
    def setUp(self):
        RecordingIcon.reset()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name) / "map.json"
        self.base.write_text('{"mappings":{}}')
        self.log_path = Path(tmp.name) / "bridge.log"

    def boot(self, platform, *extra):
        """Run the REAL win_recv + windows.tray with only pystray.Icon stubbed."""
        seen = {"main_thread": threading.current_thread()}
        started = threading.Event()

        def serve(host, port, receiver, **kw):
            seen["receiver"] = receiver
            seen["serve_thread"] = threading.current_thread()
            started.set()
            # In --tray mode the tray owns the main thread and this runs in the
            # bridge thread; ending the tray loop is what ends the process.
            for icon in RecordingIcon.instances:
                icon.run_entered.wait(10)
                icon.stop()

        midi = DryRunMidiOut()
        argv = ["--map", str(self.base), "--no-engines", "--no-pulse",
                "--no-osc-relay", "--no-browser", *extra]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(real_tray, "pystray_Icon_unused", None, create=True))
            stack.enter_context(patch.object(real_tray.pystray, "Icon", RecordingIcon))
            # The single-instance mutex name is the INSTALLED tray's: never taken.
            stack.enter_context(patch.object(real_tray, "acquire_single_instance_lock",
                                             return_value=(None, True)))
            stack.enter_context(patch.object(real_tray, "setup_log_tee",
                                             return_value=self.log_path))
            stack.enter_context(patch.object(win_recv.sys, "platform", platform))
            stack.enter_context(patch.object(win_recv, "open_midi_output", return_value=midi))
            stack.enter_context(patch.object(win_recv, "open_midi_input", return_value=None))
            stack.enter_context(patch.object(win_recv, "serve_forever", side_effect=serve))
            stack.enter_context(patch.object(MappingUIServer, "run_in_thread", lambda s: None))
            stack.enter_context(patch.object(MappingUIServer, "stop"))
            seen["rc"] = win_recv.main(argv)

        # Deterministic teardown: every tray thread this boot created is joined.
        for thread in threading.enumerate():
            if thread.name in ("tray", "bridge") and thread is not threading.current_thread():
                thread.join(10)
                self.assertFalse(thread.is_alive(), f"{thread.name} thread outlived main()")
        return seen

    # ---- non-tray: the sidecar -------------------------------------------

    def test_darwin_non_tray_never_constructs_an_icon(self):
        seen = self.boot("darwin")
        self.assertEqual(seen["rc"], 0)
        self.assertEqual(RecordingIcon.instances, [],
                         "macOS must not construct a pystray Icon: its AppKit "
                         "backend off the main thread is the A3 CPU spin")

    def test_win32_non_tray_runs_the_sidecar_icon_off_the_main_thread(self):
        seen = self.boot("win32")
        self.assertEqual(seen["rc"], 0)
        self.assertEqual(len(RecordingIcon.instances), 1)
        icon = RecordingIcon.instances[0]
        self.assertTrue(icon.run_entered.is_set())
        self.assertIsNot(icon.run_thread, seen["main_thread"])
        self.assertEqual(icon.run_thread.name, "tray")
        self.assertTrue(icon.stopped.is_set(), "the sidecar tray must be stopped on exit")
        # The bridge keeps the main thread in the sidecar design.
        self.assertIs(seen["serve_thread"], seen["main_thread"])

    def test_linux_non_tray_runs_the_sidecar_icon_off_the_main_thread(self):
        seen = self.boot("linux")
        self.assertEqual(seen["rc"], 0)
        self.assertEqual(len(RecordingIcon.instances), 1)
        self.assertIsNot(RecordingIcon.instances[0].run_thread, seen["main_thread"])
        self.assertIs(seen["serve_thread"], seen["main_thread"])

    # ---- --tray mode: the tray owns the main thread ----------------------

    def test_win32_tray_mode_runs_the_icon_on_the_main_thread(self):
        seen = self.boot("win32", "--tray")
        self.assertEqual(seen["rc"], 0)
        self.assertEqual(len(RecordingIcon.instances), 1)
        icon = RecordingIcon.instances[0]
        self.assertIs(icon.run_thread, seen["main_thread"],
                      "tray mode: pystray MUST own the main thread")
        # ...and the bridge is the one pushed off it.
        self.assertIsNot(seen["serve_thread"], seen["main_thread"])
        self.assertEqual(seen["serve_thread"].name, "bridge")

    def test_linux_tray_mode_runs_the_icon_on_the_main_thread(self):
        seen = self.boot("linux", "--tray")
        self.assertEqual(seen["rc"], 0)
        icon = RecordingIcon.instances[0]
        self.assertIs(icon.run_thread, seen["main_thread"])
        self.assertIsNot(seen["serve_thread"], seen["main_thread"])

    def test_darwin_tray_mode_constructs_no_icon_at_all(self):
        """The b/c reconciliation: P0(c) refuses --tray on darwin, so the
        darwin --tray main-thread arm is unreachable by construction."""
        seen = self.boot("darwin", "--tray")
        self.assertEqual(seen["rc"], win_recv.TRAY_UNSUPPORTED_EXIT_CODE)
        self.assertEqual(RecordingIcon.instances, [])
        self.assertNotIn("serve_thread", seen)


if __name__ == "__main__":
    unittest.main()
