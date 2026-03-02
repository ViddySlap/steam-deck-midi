"""Interactive launcher for the Deck sender preset workflow."""

from __future__ import annotations

import argparse
import os
import sys

from deck.local_config import (
    DeckRuntimeSettings,
    describe_preset,
    ensure_local_settings,
    get_xinput_list_output,
    save_runtime_settings,
    with_added_preset,
    with_device_id,
)
from deck.xinput_send import run_sender


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch STEAMDECK-MIDI-SENDER")
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


def prompt_device_id(settings_path: str, settings: DeckRuntimeSettings) -> DeckRuntimeSettings:
    print("STEAMDECK-MIDI-SENDER")
    print("")
    print("A Steam Input xinput device id is required before sending can start.")
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


def prompt_new_preset(settings_path: str, settings: DeckRuntimeSettings) -> DeckRuntimeSettings:
    print("")
    print("Create New Preset")
    while True:
        host = input("What is your target IP address? ").strip()
        name = input("What is the name of the target? ").strip()
        try:
            updated = with_added_preset(settings, name=name, host=host)
        except ValueError as exc:
            print(f"Error: {exc}")
            print("Try again.")
            print("")
            continue
        save_runtime_settings(settings_path, updated)
        print(f"Saved preset: {updated.presets[-1].name} ({updated.presets[-1].host})")
        return updated


def prompt_for_preset(settings_path: str, settings: DeckRuntimeSettings):
    while True:
        print("")
        print("STEAMDECK-MIDI-SENDER")
        print(f"Bindings: {settings.bindings_path}")
        print(f"Device ID: {settings.device_id or '(not set)'}")
        print("")
        print("Select a target preset:")
        if settings.presets:
            for index, preset in enumerate(settings.presets, start=1):
                print(describe_preset(index, preset))
        else:
            print("No presets saved yet.")
        create_index = len(settings.presets) + 1
        print(f"{create_index}. Create new preset")
        print("q. Quit")
        print("")

        choice = input("Selection: ").strip().lower()
        if choice == "q":
            return None, settings
        if choice == str(create_index):
            settings = prompt_new_preset(settings_path, settings)
            continue
        try:
            selected_index = int(choice)
        except ValueError:
            print("Invalid selection.")
            continue
        if 1 <= selected_index <= len(settings.presets):
            return settings.presets[selected_index - 1], settings
        print("Invalid selection.")


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

    if not os.path.exists(settings.bindings_path):
        parser.error(
            f"bindings file not found: {settings.bindings_path}. Run Learn Steam Input Map first."
        )
        return 2

    preset, settings = prompt_for_preset(args.settings, settings)
    if preset is None:
        print("Sender cancelled.")
        return 0

    target = f"{preset.host}:{preset.port}"
    print("")
    print(f"Starting sender for preset: {preset.name}")
    print(f"Target: {target}")
    print("")
    return run_sender(
        device_id=settings.device_id or "",
        bindings_path=settings.bindings_path,
        target=target,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
    )


if __name__ == "__main__":
    sys.exit(main())
