# PyInstaller spec for the Windows receiver console executable (v2).

from pathlib import Path
from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH)
icon_path = project_root / "assets" / "windows" / "receiver.ico"
version_file_path = project_root / "build" / "windows-file-version.txt"

flask_datas, flask_binaries, flask_hiddenimports = collect_all("flask")
jinja2_datas, jinja2_binaries, jinja2_hiddenimports = collect_all("jinja2")
werkzeug_datas, werkzeug_binaries, werkzeug_hiddenimports = collect_all("werkzeug")

datas = [
    (str(project_root / "config" / "windows_midi_map.json"), "config"),
    (
        str(project_root / "config" / "windows_receiver_settings.example.json"),
        "config",
    ),
    (str(project_root / "config" / "macro_library.json"), "config"),
    (str(project_root / "config" / "presets" / "default.json"), "config/presets"),
    (str(project_root / "config" / "actions.yaml"), "config"),
    (str(project_root / "windows" / "static"), "windows/static"),
] + flask_datas + jinja2_datas + werkzeug_datas

hiddenimports = [
    "mido.backends.rtmidi",
    "windows.ui_server",
    "windows.tray",
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
] + flask_hiddenimports + jinja2_hiddenimports + werkzeug_hiddenimports


a = Analysis(
    ["windows/win_recv.py"],
    pathex=[str(project_root)],
    binaries=[] + flask_binaries + jinja2_binaries + werkzeug_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="STEAMDECK-MIDI-RECEIVER-2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    icon=str(icon_path),
    version=str(version_file_path),
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Second target: windowed (no console window) build for tray-mode launches.
# Same analysis, just different PE subsystem. The desktop shortcut and the
# Windows auto-start Run-key entry point at this EXE so there is no console
# flash on launch. Console output is routed to the rotating log via the
# tray module's stdout/stderr tee.
exe_tray = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="STEAMDECK-MIDI-RECEIVER-2-Tray",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    icon=str(icon_path),
    version=str(version_file_path),
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
