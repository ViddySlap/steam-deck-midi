"""CLI entrypoint for the Windows UDP receiver."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path

from windows import build_fingerprint
from windows.bridge_settings import BridgeSettings
from windows.config import (
    ConfigError,
    ReceiverConfig,
    ensure_presets_initialized,
    get_active_preset_path,
    load_midi_map,
)
from windows.engines import load_engines
from windows.live_events import LiveEvents, LiveMidiOut
from windows.midi import (
    MidiError,
    get_output_port_names,
    open_midi_input,
    open_midi_output,
    resolve_available_input_port_name,
    resolve_available_output_port_name,
)
from windows.osc_relay import OscRelay, OscRelayError, load_osc_relay_config
from windows.receiver import ActionReceiver, serve_forever
from windows.preset_watch import PresetWatcher, file_signature


def load_startup_config(
    base_map_path: Path, override: str | None = None, *, platform: str,
) -> tuple[BridgeSettings, Path, ReceiverConfig]:
    """Load the active preset and initialize an absent macOS identity if usable."""
    settings = BridgeSettings.load(base_map_path.parent / "bridge.local.json", override)
    ensure_presets_initialized(base_map_path)
    active = get_active_preset_path(base_map_path.parent / "presets", base_map_path)
    section = settings.preset_section
    if platform == "darwin" and section is None and not settings.path.exists():
        try:
            raw = json.loads(active.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None  # The normal loader below supplies the existing error.
        if isinstance(raw, dict) and isinstance(raw.get("sections"), dict) and "macbook" in raw["sections"]:
            section = "macbook"
    config = load_midi_map(active, section)
    if section != settings.preset_section:
        try:
            created = settings.save_if_missing(section)
        except OSError as exc:
            raise ConfigError(f"cannot create bridge settings {settings.path}: {exc}") from exc
        if created:
            logging.info("created bridge settings %s with preset_section=macbook", settings.path)
        else:
            # Another launcher created the file after our read; respect its choice.
            config = load_midi_map(active, settings.preset_section)
    return settings, active, config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Receive action events and emit MIDI")
    parser.add_argument(
        "--listen",
        default="0.0.0.0:45123",
        help="listen address in host:port form (default: 0.0.0.0:45123)",
    )
    parser.add_argument(
        "--midi-port",
        default="DECK_IN",
        help='Windows MIDI output port name (default: "DECK_IN")',
    )
    parser.add_argument(
        "--feedback-port",
        help='Windows MIDI input port name for Resolume feedback (example: "DECK_OUT")',
    )
    parser.add_argument(
        "--map",
        dest="map_path",
        help="path to windows_midi_map.json",
    )
    parser.add_argument(
        "--preset-section",
        help="named preset section for this bridge (overrides config/bridge.local.json)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="seconds before active notes/controls are released",
    )
    parser.add_argument(
        "--preset-poll-interval", type=float, default=0.5,
        help="seconds between preset disk polls (default: 0.5)",
    )
    parser.add_argument("--dry-run", action="store_true", help="log MIDI output only")
    parser.add_argument("--verbose", action="store_true", help="enable verbose logging")
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="list available MIDI output ports and exit",
    )
    parser.add_argument(
        "--check-midi-port",
        action="store_true",
        help="validate the configured MIDI port and exit",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="disable the mapping web UI and system tray",
    )
    parser.add_argument(
        "--ui-port",
        type=int,
        default=7723,
        help="port for the mapping web UI (default: 7723)",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help=(
            "run in auto-start tray mode: bridge runs in a worker thread, "
            "tray owns the main thread, console output is teed to a "
            "rotating log under %%LOCALAPPDATA%%. Closing the console "
            "window does NOT stop the bridge; only the Quit tray menu "
            "stops it."
        ),
    )
    parser.add_argument(
        "--engines",
        dest="engines_path",
        help=(
            "path to engines config — directory of <type>.json files (preferred) "
            "or legacy engines.json file (auto-migrated). "
            "Default: <map dir>/../engines/"
        ),
    )
    parser.add_argument(
        "--no-engines",
        action="store_true",
        help="disable the v0.3.0 engine framework",
    )
    parser.add_argument(
        "--pulse-port",
        dest="pulse_port",
        default="PULSE_OUT",
        help=(
            "MIDI input port carrying System Real-Time clock from Pulse "
            "(default: PULSE_OUT). Use --no-pulse to skip."
        ),
    )
    parser.add_argument(
        "--no-pulse",
        action="store_true",
        help="don't open a clock-source MIDI input (for shows without Pulse)",
    )
    parser.add_argument(
        "--osc-relay-config",
        dest="osc_relay_config_path",
        help=(
            "path to osc_relay.json (fan Resolume's single OSC output out to "
            "multiple control surfaces). Default: <map dir>/osc_relay.json. "
            "A missing file disables the relay."
        ),
    )
    parser.add_argument(
        "--no-osc-relay",
        action="store_true",
        help="disable the OSC fan-out relay even if osc_relay.json exists",
    )
    return parser


def parse_listen(value: str) -> tuple[str, int]:
    try:
        host, port_text = value.rsplit(":", 1)
        return host, int(port_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("listen must be in host:port form") from exc


def _open_browser_delayed(url: str, delay: float = 1.2) -> None:
    def _open() -> None:
        time.sleep(delay)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True, name="browser-open").start()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    logging.info(
        "build fingerprint: version=%s commit=%s built_utc=%s",
        build_fingerprint.APP_VERSION,
        build_fingerprint.GIT_COMMIT_SHORT,
        build_fingerprint.BUILD_TIME_UTC,
    )

    # Tray mode is single-instance: if another tray-mode process already
    # holds the named mutex, surface the existing instance's web UI in the
    # default browser and exit silently. This prevents the v0.4.4 collision
    # class where a double-click on the desktop icon crashed the second
    # bootloader with WinError 10048 on UDP 45123. Acquired BEFORE any port
    # binding so we never compete for sockets with the running instance.
    _instance_lock_handle = None
    if getattr(args, "tray", False):
        # Install the rotating-file log tee BEFORE anything else logs.
        # In windowed PyInstaller builds sys.stderr is None and the default
        # basicConfig() StreamHandler raises on emit, swallowing every
        # startup log line and masking real errors behind useless "---
        # Logging error ---" diagnostics. setup_log_tee installs a file
        # handler and (in windowed mode) strips the broken stream handler.
        try:
            from windows.tray import setup_log_tee

            setup_log_tee()
        except Exception:
            logging.exception("tray-mode: setup_log_tee failed")

        from windows.tray import acquire_single_instance_lock

        _instance_lock_handle, is_first = acquire_single_instance_lock()
        if not is_first:
            ui_url = f"http://127.0.0.1:{args.ui_port}"
            logging.info(
                "single-instance: another tray-mode process is running; "
                "opening %s and exiting",
                ui_url,
            )
            try:
                import webbrowser

                webbrowser.open(ui_url)
            except Exception:
                logging.exception("single-instance: failed to open browser")
            return 0

    try:
        if args.list_ports:
            port_names = get_output_port_names()
            if not port_names:
                print("No MIDI output ports found.")
                return 1
            print("Available MIDI output ports:")
            for index, port_name in enumerate(port_names):
                print(f"- [{index}] {port_name}")
            return 0

        if args.check_midi_port:
            resolved_port_name = resolve_available_output_port_name(args.midi_port)
            print(
                "MIDI output port is available:"
                f" requested={args.midi_port} resolved={resolved_port_name}"
            )
            if args.feedback_port:
                resolved_feedback_port = resolve_available_input_port_name(
                    args.feedback_port
                )
                print(
                    "MIDI input port is available:"
                    f" requested={args.feedback_port} resolved={resolved_feedback_port}"
                )
            return 0

        if not args.map_path:
            raise ConfigError("--map is required unless --list-ports or --check-midi-port is used")

        base_map_path = Path(args.map_path)
        bridge_settings, active_preset_path, receiver_config = load_startup_config(
            base_map_path, args.preset_section, platform=sys.platform,
        )
        presets_dir = base_map_path.parent / "presets"
        macro_library_path = base_map_path.parent / "macro_library.json"

        listen_host, listen_port = parse_listen(args.listen)
        live_events = LiveEvents()
        midi_out = LiveMidiOut(open_midi_output(args.midi_port, args.dry_run), live_events)
        midi_in = open_midi_input(args.feedback_port, args.dry_run)
    except (argparse.ArgumentTypeError, ConfigError, MidiError) as exc:
        parser.error(str(exc))
        return 2

    logging.info(
        "selected MIDI output port: name=%s index=%s",
        midi_out.port_name,
        midi_out.port_index if midi_out.port_index is not None else "n/a",
    )
    if midi_in is not None:
        logging.info(
            "selected MIDI input feedback port: name=%s index=%s",
            midi_in.port_name,
            midi_in.port_index if midi_in.port_index is not None else "n/a",
        )

    reload_event = threading.Event()
    try:
        preset_watcher = PresetWatcher(
            presets_dir, bridge_settings.path, reload_event,
            poll_interval=args.preset_poll_interval,
        )
    except ValueError as exc:
        parser.error(str(exc))
    settings_stamp = file_signature(bridge_settings.path)
    preset_watcher.start()
    actions_yaml = base_map_path.parent / "actions.yaml"

    def reload_config_fn():
        nonlocal settings_stamp
        new_stamp = file_signature(bridge_settings.path)
        section = bridge_settings.preset_section
        if new_stamp != settings_stamp:
            section = BridgeSettings.load(bridge_settings.path).preset_section
        active = get_active_preset_path(presets_dir, base_map_path)
        cfg = load_midi_map(active, section)
        # Apply the preset's per-engine on/off states on the receiver thread
        # (this runs inside serve_forever's reload path, so no cross-thread race
        # with engine dispatch). Engines absent from the map are left as-is.
        if engine_registry is not None:
            engine_registry.apply_engine_states(cfg.engine_states)
        # Publish identity only after the complete candidate has loaded. An
        # unchanged file preserves startup argv; PUT still supersedes it live.
        bridge_settings.preset_section = section
        settings_stamp = new_stamp
        return cfg.mappings, cfg.macro_settings

    engine_registry = None
    if not args.no_engines:
        if args.engines_path:
            engines_path = Path(args.engines_path)
        else:
            engines_path = base_map_path.parent / "engines"
        engine_registry = load_engines(engines_path, midi_out)
        # Honor the active preset's engine on/off states at startup so a
        # PTZ-style preset boots with show engines already disabled.
        engine_registry.apply_engine_states(receiver_config.engine_states)
        if engine_registry.engines:
            logging.info(
                "engine config: path=%s count=%d active=%d",
                engines_path,
                len(engine_registry.engines),
                sum(1 for e in engine_registry.engines if e.active),
            )

    pulse_in = None
    if not args.no_pulse and args.pulse_port:
        try:
            pulse_in = open_midi_input(args.pulse_port, args.dry_run)
        except MidiError as exc:
            logging.warning(
                "pulse port '%s' not available: %s (continuing without clock)",
                args.pulse_port,
                exc,
            )

    receiver = ActionReceiver(
        midi_out,
        receiver_config.mappings,
        timeout_seconds=args.timeout,
        macro_settings=receiver_config.macro_settings,
        engine_registry=engine_registry,
        live_events=live_events,
    )

    # OSC fan-out relay. Core infrastructure, not an engine -- deliberately
    # has no per-preset toggle, because an off toggle here would kill OSC
    # feedback to every control surface at once with no visible symptom.
    osc_relay = None
    if not args.no_osc_relay:
        if args.osc_relay_config_path:
            osc_relay_path = Path(args.osc_relay_config_path)
        else:
            osc_relay_path = base_map_path.parent / "osc_relay.json"
        try:
            osc_relay_config = load_osc_relay_config(osc_relay_path)
        except OscRelayError as exc:
            # Bad relay config must not stop the bridge; MIDI is the
            # show-critical path and it does not depend on the relay.
            logging.warning("osc_relay config invalid (%s); relay disabled", exc)
        else:
            if osc_relay_config.active:
                osc_relay = OscRelay(osc_relay_config)
                if not osc_relay.start():
                    osc_relay = None
            else:
                logging.debug("osc_relay: not configured at %s", osc_relay_path)

    tray = None
    ui_server = None
    if not args.no_ui:
        from windows.ui_server import MappingUIServer
        ui_server = MappingUIServer(
            base_map_path=base_map_path,
            presets_dir=presets_dir,
            macro_library_path=macro_library_path,
            actions_yaml_path=actions_yaml,
            reload_event=reload_event,
            shutdown_fn=receiver.request_shutdown,
            port=args.ui_port,
            engine_registry=engine_registry,
            bridge_settings=bridge_settings,
            state_version_fn=lambda: receiver.state_version,
            live_events=live_events,
            listen=f"{listen_host}:{listen_port}",
            midi_port=midi_out.port_name,
            feedback_port=midi_in.port_name if midi_in is not None else None,
            pulse_port=pulse_in.port_name if pulse_in is not None else None,
        )
        ui_server.run_in_thread()
        logging.info("mapping UI available at %s", ui_server.url)
        if not args.tray:
            # Tray mode shows the browser via the tray menu instead.
            _open_browser_delayed(ui_server.url)

        if not args.tray:
            try:
                from windows.tray import ReceiverTray
                tray = ReceiverTray(ui_url=ui_server.url, quit_callback=receiver.request_shutdown)
                tray.run_in_thread()
            except Exception as exc:
                logging.warning("system tray unavailable: %s", exc)

    def _run_bridge_loop() -> None:
        serve_forever(
            listen_host,
            listen_port,
            receiver,
            midi_in=midi_in,
            pulse_in=pulse_in,
            reload_event=reload_event,
            reload_config_fn=reload_config_fn,
            engine_registry=engine_registry,
        )

    if args.tray:
        # Auto-start tray mode: bridge runs in worker thread, tray owns
        # main thread. Disabling --no-ui in tray mode is nonsensical
        # because the tray needs a UI URL; warn and continue with a
        # placeholder.
        ui_url = ui_server.url if ui_server is not None else f"http://127.0.0.1:{args.ui_port}"
        try:
            from windows.tray import run_tray_mode

            run_tray_mode(
                ui_url=ui_url,
                run_bridge=_run_bridge_loop,
                stop_bridge=receiver.request_shutdown,
            )
        finally:
            preset_watcher.stop()
            preset_watcher.join()
            midi_out.close()
            if osc_relay is not None:
                osc_relay.shutdown()
            if ui_server is not None:
                ui_server.stop()
        return 0

    try:
        _run_bridge_loop()
    finally:
        preset_watcher.stop()
        preset_watcher.join()
        midi_out.close()
        if osc_relay is not None:
            osc_relay.shutdown()
        if ui_server is not None:
            ui_server.stop()
        if tray is not None:
            tray.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
