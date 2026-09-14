"""Interactive launcher for the Deck sender preset workflow."""

from __future__ import annotations

import argparse
import os
import sys

from deck.local_config import (
    describe_preset,
    ensure_local_settings,
    save_runtime_settings,
    with_added_preset,
    with_deleted_preset,
    with_renamed_preset,
    with_active_targets,
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

def prompt_new_preset(settings_path: str, settings):
    print("")
    print("Create New Preset")
    while True:
        host = input("What is your target IPv4 address or hostname? ").strip()
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


def prompt_rename_preset(settings_path: str, settings):
    if not settings.presets:
        print("No presets to rename.")
        return settings
    print("")
    print("Rename Preset")
    for index, preset in enumerate(settings.presets, start=1):
        print(describe_preset(index, preset, preset.name in settings.active_targets))
    while True:
        choice = input(f"Rename which preset? (1-{len(settings.presets)}): ").strip()
        try:
            selected = int(choice)
        except ValueError:
            print("Invalid selection.")
            continue
        if not (1 <= selected <= len(settings.presets)):
            print("Invalid selection.")
            continue
        old_name = settings.presets[selected - 1].name
        new_name = input(f"New name for '{old_name}': ").strip()
        try:
            updated = with_renamed_preset(settings, selected - 1, new_name)
        except ValueError as exc:
            print(f"Error: {exc}")
            continue
        save_runtime_settings(settings_path, updated)
        print(f"Renamed to: {updated.presets[selected - 1].name}")
        return updated


def prompt_delete_preset(settings_path: str, settings):
    if not settings.presets:
        print("No presets to delete.")
        return settings
    print("")
    print("Delete Preset")
    for index, preset in enumerate(settings.presets, start=1):
        print(describe_preset(index, preset, preset.name in settings.active_targets))
    while True:
        choice = input(f"Delete which preset? (1-{len(settings.presets)}): ").strip()
        try:
            selected = int(choice)
        except ValueError:
            print("Invalid selection.")
            continue
        if not (1 <= selected <= len(settings.presets)):
            print("Invalid selection.")
            continue
        preset = settings.presets[selected - 1]
        confirm = input(f"Delete '{preset.name}'? (y/n): ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return settings
        updated = with_deleted_preset(settings, selected - 1)
        save_runtime_settings(settings_path, updated)
        print(f"Deleted: {preset.name}")
        return updated


def prompt_select_multiple(settings_path: str, settings):
    names = list(settings.active_targets)
    while True:
        print("")
        print("Select multiple targets")
        for index, preset in enumerate(settings.presets, start=1):
            print(describe_preset(index, preset, preset.name in names))
        choice = input("Toggle a preset number, s to save, or q to cancel: ").strip().lower()
        if choice == "q":
            return settings
        if choice == "s":
            try:
                updated = with_active_targets(settings, names)
                save_runtime_settings(settings_path, updated)
            except (OSError, ValueError) as exc:
                print(f"Error: {exc}")
                continue
            return updated
        try:
            index = int(choice) - 1
        except ValueError:
            print("Invalid selection.")
            continue
        if not 0 <= index < len(settings.presets):
            print("Invalid selection.")
            continue
        name = settings.presets[index].name
        if name in names:
            names.remove(name)
        else:
            names.append(name)


def prompt_for_preset(settings_path: str, settings, device_id: str):
    while True:
        print("")
        print("STEAMDECK-MIDI-SENDER")
        print(f"Bindings: {settings.bindings_path}")
        print(f"Device ID: {device_id}")
        print("")
        print("Select a target preset:")
        if settings.presets:
            for index, preset in enumerate(settings.presets, start=1):
                print(describe_preset(index, preset, preset.name in settings.active_targets))
        else:
            print("No presets saved yet.")
        create_index = len(settings.presets) + 1
        print(f"{create_index}. Create new preset")
        if settings.presets:
            print("m. Select multiple targets")
            if settings.active_targets:
                print("s. Start active targets")
            print("r. Rename a preset")
            print("d. Delete a preset")
        print("q. Quit")
        print("")

        choice = input("Selection: ").strip().lower()
        if choice == "q":
            return None, settings
        if choice == "m" and settings.presets:
            settings = prompt_select_multiple(settings_path, settings)
            continue
        if choice == "s" and settings.active_targets:
            preset = next(p for p in settings.presets if p.name == settings.active_targets[0])
            return preset, settings
        if choice == str(create_index):
            settings = prompt_new_preset(settings_path, settings)
            continue
        if choice == "r" and settings.presets:
            settings = prompt_rename_preset(settings_path, settings)
            continue
        if choice == "d" and settings.presets:
            settings = prompt_delete_preset(settings_path, settings)
            continue
        try:
            selected_index = int(choice)
        except ValueError:
            print("Invalid selection.")
            continue
        if 1 <= selected_index <= len(settings.presets):
            if settings.active_targets:
                settings = with_active_targets(settings, [])
                save_runtime_settings(settings_path, settings)
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

    if not os.path.exists(settings.bindings_path):
        parser.error(
            f"bindings file not found: {settings.bindings_path}. Run Learn Steam Input Map first."
        )
        return 2

    device_id = settings.device_id or "5"
    preset, settings = prompt_for_preset(args.settings, settings, device_id)
    if preset is None:
        print("Sender cancelled.")
        return 0

    by_name = {p.name: p for p in settings.presets}
    selected = [by_name[name] for name in settings.active_targets] or [preset]
    targets = [(p.host, p.port) for p in selected]
    print("")
    print(f"Starting sender for presets: {', '.join(p.name for p in selected)}")
    print(f"Targets: {', '.join(f'{host}:{port}' for host, port in targets)}")
    print("")
    return run_sender(
        device_id=device_id,
        bindings_path=settings.bindings_path,
        targets=targets,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
    )


if __name__ == "__main__":
    sys.exit(main())
