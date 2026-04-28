"""Interactive CLI wizard for capturing Deck keycodes via X11 XI2 raw events."""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import sys
import tempfile
import termios
import tty
from dataclasses import dataclass

from deck.xinput_send import Xi2RawListener


KEY_PRESS_RE = re.compile(r"^key press\s+(\d+)$")


@dataclass(frozen=True)
class LearnCandidate:
    token: str


class TerminalCbreak:
    def __enter__(self) -> "TerminalCbreak":
        self._fd = sys.stdin.fileno()
        self._old_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture Steam Deck xinput keycodes and write deck bindings"
    )
    parser.add_argument("--device-id", required=True, help="xinput device id")
    parser.add_argument(
        "--actions",
        required=True,
        help="path to actions.yaml containing the action list",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="output path for deck_bindings.json",
    )
    parser.add_argument(
        "--profile-name",
        default="default",
        help="profile name to store in the bindings file",
    )
    return parser


def load_actions(path: str) -> list[str]:
    actions: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or line == "actions:":
                    continue
                if not line.startswith("- "):
                    raise ValueError(f"unsupported actions line: {raw_line.rstrip()}")
                action = line[2:].strip()
                if not action:
                    raise ValueError("action names must be non-empty")
                actions.append(action)
    except FileNotFoundError as exc:
        raise ValueError(f"actions file not found: {path}") from exc

    if not actions:
        raise ValueError("no actions found in actions file")
    return actions


def load_existing_bindings(path: str) -> dict[str, str]:
    """Read a bindings file and return {action: token} mapping."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    bindings_raw = raw.get("bindings")
    if not isinstance(bindings_raw, dict):
        return {}
    return {
        action: token
        for token, action in bindings_raw.items()
        if isinstance(token, str) and isinstance(action, str)
    }


def parse_key_press(line: str) -> LearnCandidate | None:
    match = KEY_PRESS_RE.match(line.strip())
    if match is None:
        return None
    return LearnCandidate(token=match.group(1))


def find_duplicate_action(bindings: dict[str, str], token: str) -> str | None:
    for action, bound_token in bindings.items():
        if bound_token == token:
            return action
    return None


def is_skip_input(chars: bytes) -> bool:
    return chars == b"\x1b"


def write_bindings(path: str, profile_name: str, bindings: dict[str, str]) -> None:
    if os.path.isdir(path):
        raise ValueError(
            f"output path points to a directory, not a file: {path}"
        )

    payload = {
        "profile_name": profile_name,
        "bindings": {token: action for action, token in bindings.items()},
    }

    directory = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=directory
    ) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temp_path = handle.name
    os.replace(temp_path, path)


def print_header(device_id: str, output_path: str) -> None:
    print("Steam Deck Learn Wizard")
    print(f"Listening to xinput device: {device_id}")
    print(f"Output file: {output_path}")
    print("Instructions:")
    print("- Press the Steam Deck control you want to map")
    print("- Watch the latest captured keycode")
    print("- Press Enter to confirm the latest captured keycode")
    print("- Press Esc to skip the current action and leave it unmapped")
    print("- Press Ctrl+X at any time to exit without saving")
    print("- If you hit Enter too early, the wizard will warn and keep waiting")
    print("")


def prompt_action(action: str) -> None:
    print("")
    print(f"Map action: {action}")
    print("Waiting for key press, or press Esc to skip...")


def prompt_startup_menu(
    actions: list[str], existing_bindings: dict[str, str]
) -> str | bool | None:
    """Show startup menu when a bindings file already exists.

    Returns:
      None  — user chose quit
      True  — run full re-learn from scratch
      str   — action name to re-learn in single-action mode
    """
    print("A bindings file already exists.")
    print("1. Full re-learn (re-map all actions from scratch)")
    print("2. Re-learn one action")
    print("q. Quit")
    while True:
        choice = input("Selection: ").strip().lower()
        if choice == "q":
            return None
        if choice == "1":
            return True
        if choice == "2":
            break
        print("Invalid selection.")

    print("")
    print("Which action do you want to re-learn?")
    for i, action in enumerate(actions, start=1):
        token = existing_bindings.get(action)
        status = f"keycode {token}" if token else "unmapped"
        print(f"{i}. {action} ({status})")

    while True:
        choice = input(f"Selection (1-{len(actions)}): ").strip()
        try:
            idx = int(choice)
        except ValueError:
            print("Invalid selection.")
            continue
        if not (1 <= idx <= len(actions)):
            print("Invalid selection.")
            continue
        return actions[idx - 1]


def _run_relearn(
    action: str,
    bindings: dict[str, str],
    out_path: str,
    profile_name: str,
    selector: selectors.DefaultSelector,
) -> int:
    """Run single-action re-learn. Returns exit code."""
    print("")
    print(f"Re-learning: {action}")
    print("Press the control to assign, then press Enter to confirm.")
    print("Press Esc or Ctrl+X to cancel.")
    prompt_action(action)
    candidate: LearnCandidate | None = None

    try:
        with TerminalCbreak():
            while True:
                for key, _ in selector.select():
                    if key.data == "xinput":
                        xi_event = key.fileobj.read_event()
                        if xi_event is None or xi_event.state != "down":
                            continue
                        candidate = LearnCandidate(token=xi_event.keycode)
                        duplicate = find_duplicate_action(bindings, candidate.token)
                        print(
                            f"Latest candidate for {action}: keycode {candidate.token} — press Enter to commit"
                        )
                        if duplicate is not None and duplicate != action:
                            print(
                                f"Warning: keycode {candidate.token} is already assigned to {duplicate} and cannot be reused"
                            )
                    else:
                        chars = os.read(sys.stdin.fileno(), 8)
                        if b"\x18" in chars or is_skip_input(chars):
                            print("\nCancelled.")
                            return 1
                        if b"\n" not in chars and b"\r" not in chars:
                            continue
                        if candidate is None:
                            print("Warning: no candidate captured yet. Try again.")
                            continue
                        duplicate = find_duplicate_action(bindings, candidate.token)
                        if duplicate is not None and duplicate != action:
                            print(
                                f"Error: keycode {candidate.token} is already assigned to {duplicate}. Capture a different control."
                            )
                            candidate = None
                            continue
                        updated = dict(bindings)
                        updated[action] = candidate.token
                        print(f"Confirmed: {action} <- keycode {candidate.token}")
                        write_bindings(out_path, profile_name, updated)
                        print(f"Saved: {out_path}")
                        return 0
    except KeyboardInterrupt:
        print("\nWizard cancelled.")
        return 1
    return 0


def _run_full_learn(
    actions: list[str],
    device_id: str,
    out_path: str,
    profile_name: str,
    selector: selectors.DefaultSelector,
) -> int:
    """Run full learn for all actions. Returns exit code."""
    bindings: dict[str, str] = {}
    candidate: LearnCandidate | None = None
    action_index = 0

    print_header(device_id, out_path)
    prompt_action(actions[action_index])

    with TerminalCbreak():
        try:
            while action_index < len(actions):
                for key, _ in selector.select():
                    if key.data == "xinput":
                        xi_event = key.fileobj.read_event()
                        if xi_event is None or xi_event.state != "down":
                            continue
                        candidate = LearnCandidate(token=xi_event.keycode)
                        duplicate_action = find_duplicate_action(
                            bindings, candidate.token
                        )
                        print(
                            f"Latest candidate for {actions[action_index]}: keycode {candidate.token} press Enter to commit"
                        )
                        if duplicate_action is not None:
                            print(
                                f"Warning: keycode {candidate.token} is already assigned to {duplicate_action} and cannot be reused"
                            )
                    else:
                        chars = os.read(sys.stdin.fileno(), 8)
                        if b"\x18" in chars:
                            print("")
                            print("Wizard cancelled. No bindings were written.")
                            return 1
                        if is_skip_input(chars):
                            current_action = actions[action_index]
                            print(f"Skipped: {current_action}")
                            candidate = None
                            action_index += 1
                            if action_index < len(actions):
                                prompt_action(actions[action_index])
                            continue
                        if b"\n" not in chars and b"\r" not in chars:
                            continue
                        if candidate is None:
                            print("Warning: no candidate captured yet. Try again.")
                            continue

                        current_action = actions[action_index]
                        duplicate_action = find_duplicate_action(
                            bindings, candidate.token
                        )
                        if duplicate_action is not None and duplicate_action != current_action:
                            print(
                                f"Error: keycode {candidate.token} is already assigned to {duplicate_action}. Capture a different control."
                            )
                            candidate = None
                            continue
                        bindings[current_action] = candidate.token
                        print(
                            f"Confirmed: {current_action} <- keycode {candidate.token}"
                        )
                        candidate = None
                        action_index += 1
                        if action_index < len(actions):
                            prompt_action(actions[action_index])
            write_bindings(out_path, profile_name, bindings)
        except ValueError as exc:
            print("")
            print(f"Error: {exc}")
            return 2
        except KeyboardInterrupt:
            print("")
            print("Wizard cancelled. No bindings were written.")
            return 1

    print("")
    print(f"Wrote bindings to {out_path}")
    print("Summary:")
    for action in actions:
        token = bindings.get(action, "(skipped)")
        print(f"- {action}: {token}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        actions = load_actions(args.actions)
        if os.path.isdir(args.out):
            raise ValueError(f"--out must be a file path, not a directory: {args.out}")
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    # Show startup menu when an existing bindings file has content
    existing_bindings: dict[str, str] = {}
    relearn_action: str | None = None
    if os.path.exists(args.out):
        existing_bindings = load_existing_bindings(args.out)
        if existing_bindings:
            print("Steam Deck Learn Wizard")
            print("")
            menu_result = prompt_startup_menu(actions, existing_bindings)
            if menu_result is None:
                print("Wizard cancelled.")
                return 0
            if isinstance(menu_result, str):
                relearn_action = menu_result

    try:
        listener = Xi2RawListener(int(args.device_id))
    except OSError as exc:
        parser.error(f"failed to open X11 display: {exc}")
        return 2

    selector = selectors.DefaultSelector()
    selector.register(sys.stdin, selectors.EVENT_READ, "stdin")
    selector.register(listener, selectors.EVENT_READ, "xinput")

    try:
        if relearn_action is not None:
            return _run_relearn(
                relearn_action,
                existing_bindings,
                args.out,
                args.profile_name,
                selector,
            )
        return _run_full_learn(
            actions, args.device_id, args.out, args.profile_name, selector
        )
    finally:
        selector.close()
        listener.close()


if __name__ == "__main__":
    sys.exit(main())
