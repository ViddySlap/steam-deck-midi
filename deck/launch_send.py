"""Interactive launcher for the Deck sender preset workflow."""

from __future__ import annotations

import argparse
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
from deck.control_api import ControlServer, SenderController, add_api_arguments, interrupt_launcher


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
    add_api_arguments(parser)
    return parser

def _save_menu_settings(path, updated, previous, controller):
    if controller is None:
        save_runtime_settings(path, updated)
    else:
        controller.commit_settings(updated, expected=previous)


def prompt_new_preset(settings_path: str, settings, controller=None):
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
        _save_menu_settings(settings_path, updated, settings, controller)
        print(f"Saved preset: {updated.presets[-1].name} ({updated.presets[-1].host})")
        return updated


def prompt_rename_preset(settings_path: str, settings, controller=None):
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
        _save_menu_settings(settings_path, updated, settings, controller)
        print(f"Renamed to: {updated.presets[selected - 1].name}")
        return updated


def prompt_delete_preset(settings_path: str, settings, controller=None):
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
        _save_menu_settings(settings_path, updated, settings, controller)
        print(f"Deleted: {preset.name}")
        return updated


def prompt_select_multiple(settings_path: str, settings, controller=None):
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
                _save_menu_settings(settings_path, updated, settings, controller)
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


def prompt_for_preset(settings_path: str, settings, device_id: str, controller=None):
    while True:
        if controller is not None:
            settings = controller.snapshot()
            device_id = settings.device_id or "5"
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
        if controller is not None:
            print("t. Stop sender")
            print("x. Restart sender")
        print("q. Quit")
        print("")

        choice = input("Selection: ").strip().lower()
        if choice == "q":
            return None, settings
        if controller is not None and controller.snapshot() != settings:
            print("Settings changed; menu refreshed. Select again.")
            continue
        if controller is not None and choice in {"t", "x"}:
            if choice == "t":
                controller.stop()
            else:
                controller.restart()
            continue
        if choice == "m" and settings.presets:
            settings = prompt_select_multiple(settings_path, settings, controller)
            continue
        if choice == "s" and settings.active_targets:
            preset = next(p for p in settings.presets if p.name == settings.active_targets[0])
            return preset, settings
        if choice == str(create_index):
            settings = prompt_new_preset(settings_path, settings, controller)
            continue
        if choice == "r" and settings.presets:
            settings = prompt_rename_preset(settings_path, settings, controller)
            continue
        if choice == "d" and settings.presets:
            settings = prompt_delete_preset(settings_path, settings, controller)
            continue
        try:
            selected_index = int(choice)
        except ValueError:
            print("Invalid selection.")
            continue
        if 1 <= selected_index <= len(settings.presets):
            if settings.active_targets:
                updated = with_active_targets(settings, [])
                _save_menu_settings(settings_path, updated, settings, controller)
                settings = updated
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

    controller = SenderController(args.settings, settings, run=run_sender)
    try:
        server = ControlServer(controller, bind=args.api_bind, port=args.api_port, on_shutdown=interrupt_launcher)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    server.start()
    print(f"Deck control API: http://{server.server_address[0]}:{server.server_address[1]}")
    try:
        while True:
            try:
                settings = controller.snapshot()
                preset, settings = prompt_for_preset(args.settings, settings, settings.device_id or "5", controller)
                if preset is None:
                    return 0
                with controller.lock:
                    if controller.snapshot() != settings:
                        raise ValueError("Settings changed; select again.")
                    controller.stop()
                    status = controller.start(single_target=preset.name)
                print(f"Sender requested for targets: {status['active_targets']}")
            except (OSError, ValueError) as exc:
                print(f"Error: {exc}")
    except (KeyboardInterrupt, EOFError):
        return 0
    finally:
        if controller.learn is not None:
            controller.learn.cancel()
        controller.stop()
        server.close()


if __name__ == "__main__":
    sys.exit(main())
