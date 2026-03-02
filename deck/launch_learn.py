"""Desktop-friendly launcher for the Learn Wizard."""

from __future__ import annotations

import argparse
import sys

from deck.learn_wizard import main as learn_main
from deck.local_config import ensure_local_settings


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

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = ensure_local_settings(args.settings, args.settings_example)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    device_id = settings.device_id or "5"

    return learn_main(
        [
            "--device-id",
            device_id,
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
