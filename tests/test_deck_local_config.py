from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from deck.local_config import (
    ensure_local_settings,
    load_runtime_settings,
    validate_ipv4_address,
    with_added_preset,
    with_device_id,
)


class DeckLocalConfigTests(unittest.TestCase):
    def test_validate_ipv4_address_accepts_valid_address(self) -> None:
        self.assertEqual(validate_ipv4_address("10.10.10.20"), "10.10.10.20")

    def test_validate_ipv4_address_rejects_invalid_address(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid IPv4 address"):
            validate_ipv4_address("not-an-ip")

    def test_ensure_local_settings_copies_example_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            example = root / "example.json"
            local = root / "local.json"
            example.write_text(
                """
{
  "device_id": "5",
  "bindings_path": "config/deck_bindings.json",
  "actions_path": "config/actions.yaml",
  "default_port": 45123,
  "profile_name": "default",
  "profile_hash": null,
  "presets": []
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            settings = ensure_local_settings(str(local), str(example))

            self.assertTrue(local.exists())
            self.assertEqual(settings.default_port, 45123)
            self.assertEqual(settings.presets, [])
            self.assertEqual(settings.device_id, "5")

    def test_with_device_id_updates_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                """
{
  "device_id": null,
  "bindings_path": "config/deck_bindings.json",
  "actions_path": "config/actions.yaml",
  "default_port": 45123,
  "profile_name": "default",
  "profile_hash": null,
  "presets": []
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            settings = load_runtime_settings(str(path))
            updated = with_device_id(settings, "5")

            self.assertEqual(updated.device_id, "5")

    def test_with_added_preset_appends_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                """
{
  "device_id": "5",
  "bindings_path": "config/deck_bindings.json",
  "actions_path": "config/actions.yaml",
  "default_port": 45123,
  "profile_name": "default",
  "profile_hash": null,
  "presets": []
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            settings = load_runtime_settings(str(path))
            updated = with_added_preset(settings, name="Resolume PC", host="10.10.10.20")

            self.assertEqual(len(updated.presets), 1)
            self.assertEqual(updated.presets[0].name, "Resolume PC")
            self.assertEqual(updated.presets[0].host, "10.10.10.20")
