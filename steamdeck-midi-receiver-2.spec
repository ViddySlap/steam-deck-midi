# PyInstaller spec for the Windows receiver console executable (v2).

from pathlib import Path


project_root = Path(SPECPATH)
icon_path = project_root / "assets" / "windows" / "receiver.ico"
version_file_path = project_root / "build" / "windows-file-version.txt"

datas = [
    (str(project_root / "config" / "windows_midi_map.json"), "config"),
    (
        str(project_root / "config" / "windows_receiver_settings.example.json"),
        "config",
    ),
    (str(project_root / "config" / "macro_library.json"), "config"),
    (str(project_root / "config" / "presets" / "default.json"), "config/presets"),
]

hiddenimports = [
    "mido.backends.rtmidi",
]


a = Analysis(
    ["windows/win_recv.py"],
    pathex=[str(project_root)],
    binaries=[],
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
