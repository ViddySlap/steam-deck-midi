"""Smoke test for the ``windows.tray`` module.

Anything richer than this (clicking menu items, running the icon) is
hard to do headless without a real Windows session, so we just verify
that the module imports cleanly and that the menu factory + entry
points exist with the expected shape. Behavioral tests for tray mode
are deferred until Ben drives a manual test pass per
``installer-changes.md``.
"""

from __future__ import annotations

import unittest


class TrayImportTests(unittest.TestCase):
    def test_module_imports(self) -> None:
        import windows.tray  # noqa: F401

    def test_menu_factory_exists_and_returns_menu(self) -> None:
        import pystray

        from windows.tray import build_tray_menu

        menu = build_tray_menu(
            ui_url="http://127.0.0.1:7723",
            on_quit=lambda: None,
        )
        self.assertIsInstance(menu, pystray.Menu)

        # pystray Menu items are exposed via __call__ -> tuple of MenuItems.
        # Separators don't have their own marker attribute in pystray 0.19;
        # they're MenuItems with the SEPARATOR sentinel text. Filter on
        # identity against the SEPARATOR MenuItem.
        items = list(menu)
        labels = [
            str(item.text)
            for item in items
            if item is not pystray.Menu.SEPARATOR
        ]
        # We expect three actionable items: Open Web UI / View Terminal / Quit.
        self.assertEqual(labels, ["Open Web UI", "View Terminal", "Quit"])

    def test_run_tray_mode_callable_exists(self) -> None:
        from windows.tray import run_tray_mode

        self.assertTrue(callable(run_tray_mode))

    def test_default_log_path_under_localappdata(self) -> None:
        from windows.tray import default_log_path

        log_path = default_log_path()
        parts = [p.lower() for p in log_path.parts]
        # Expect "...AppData/Local/STEAMDECK MIDI Receiver 2/logs/bridge.log"
        # (or the env-override variant); regardless, the trailing
        # filename + parent must match.
        self.assertEqual(log_path.name, "bridge.log")
        self.assertEqual(log_path.parent.name, "logs")
        self.assertIn("steamdeck midi receiver 2", " ".join(parts))


if __name__ == "__main__":
    unittest.main()
