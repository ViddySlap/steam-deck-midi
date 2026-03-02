# PyInstaller spec for the Windows receiver console executable.

from pathlib import Path


project_root = Path(SPECPATH)

datas = [
    (str(project_root / "config" / "windows_midi_map.json"), "config"),
    (
        str(project_root / "config" / "windows_receiver_settings.example.json"),
        "config",
    ),
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
    name="steam-deck-vj-receiver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
