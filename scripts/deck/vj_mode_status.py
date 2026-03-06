#!/usr/bin/env python3
import os
import shutil
import socket
import subprocess
from pathlib import Path


def run_cmd(cmd):
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return out.strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def yes_no(value):
    return "yes" if value else "no"


def print_section(title):
    print(f"\n=== {title} ===")


def main():
    home = Path.home()
    touchosc_bin = home / "Applications" / "TouchOSC" / "TouchOSC"
    touchosc_layout = home / "Documents" / "TouchOSC" / "STEAMDECK V1.tosc"
    inputleap_conf = (
        home
        / ".var"
        / "app"
        / "io.github.input_leap.input-leap"
        / "config"
        / "InputLeap"
        / "InputLeap.conf"
    )
    sender_cmd = home / "steam-deck-midi" / "scripts" / "deck" / "run_sender.sh"

    print_section("Session")
    print(f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE', '')}")
    print(f"DESKTOP_SESSION={os.environ.get('DESKTOP_SESSION', '')}")
    print(f"DISPLAY={os.environ.get('DISPLAY', '')}")
    print(f"WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', '')}")
    print(f"GAMESCOPE_WAYLAND_DISPLAY={os.environ.get('GAMESCOPE_WAYLAND_DISPLAY', '')}")

    print_section("Binaries")
    checks = [
        "startplasma-x11",
        "startplasma-wayland",
        "gamescope",
        "flatpak",
        "python3",
    ]
    for name in checks:
        print(f"{name}: {shutil.which(name) or 'MISSING'}")
    print(f"TouchOSC: {touchosc_bin} ({yes_no(touchosc_bin.exists())})")
    print(f"Sender script: {sender_cmd} ({yes_no(sender_cmd.exists())})")

    print_section("InputLeap Flatpak")
    flatpak_id = "io.github.input_leap.input-leap"
    print(run_cmd(["flatpak", "info", flatpak_id]))
    print(f"InputLeap config: {inputleap_conf} ({yes_no(inputleap_conf.exists())})")
    print("input-leaps path:")
    print(run_cmd(["flatpak", "run", "--command=sh", flatpak_id, "-lc", "command -v input-leaps || true"]))
    print("input-leapc path:")
    print(run_cmd(["flatpak", "run", "--command=sh", flatpak_id, "-lc", "command -v input-leapc || true"]))

    print_section("TouchOSC")
    print(f"Layout file: {touchosc_layout} ({yes_no(touchosc_layout.exists())})")

    print_section("Network")
    print(run_cmd(["ip", "-4", "addr", "show"]))
    try:
        host = socket.gethostname()
        ips = sorted({addr[4][0] for addr in socket.getaddrinfo(host, None, family=socket.AF_INET)})
        print(f"Hostname: {host}")
        print("IPv4 (hostname lookup): " + ", ".join(ips))
        print("Has 10.10.10.x: " + yes_no(any(ip.startswith("10.10.10.") for ip in ips)))
    except Exception as exc:
        print(f"Hostname/IP lookup failed: {exc}")


if __name__ == "__main__":
    main()
