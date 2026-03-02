"""Desktop-friendly launcher for the Learn Wizard."""

from __future__ import annotations

import argparse
import sys

from deck.learn_wizard import main as learn_main
from deck.local_config import ensure_local_settings, get_xinput_list_output, save_runtime_settings, with_device_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch Learn Steam Input Map")
    parser.add_argument(
        "--settings",
        default="config/deck_runtime_settings.local.json",
        help="path to deck runtime settings JSON",
    )
    parser.add_argument(
        "--settings-example",
        default="config/deck_runtime_settings.example.json",
        help="path to example deck runtime settings JSON",
    )
    return parser


def prompt_device_id(settings_path: str, settings):
    print("Learn Steam Input Map")
    print("")
    print("A Steam Input xinput device id is required before learning can start.")
    xinput_output = get_xinput_list_output()
    if xinput_output:
        print("")
        print("Current xinput devices:")
        print(xinput_output)
    print("")
    while True:
        device_id = input("Enter the xinput device id to use: ").strip()
        if not device_id:
            print("Device id cannot be empty.")
            continue
        updated = with_device_id(settings, device_id)
        save_runtime_settings(settings_path, updated)
        print(f"Saved device id: {device_id}")
        return updated


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = ensure_local_settings(args.settings, args.settings_example)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
        return 2

    if settings.device_id is None:
        settings = prompt_device_id(args.settings, settings)

    return learn_main(
        [
            "--device-id",
            settings.device_id or "",
            "--actions",
            settings.actions_path,
            "--out",
            settings.bindings_path,
            "--profile-name",
            settings.profile_name or "default",
        ]
    )


if __name__ == "__main__":
    sys.exit(main())
