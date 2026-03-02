# Windows Branding Assets

Drop Windows branding assets for packaging here.

## Expected Files

- `receiver.ico`
  Primary Windows receiver icon for:
  - `STEAMDECK-MIDI-RECEIVER.exe`
  - desktop and Start Menu shortcuts

- `receiver.png`
  High-resolution source image for the receiver icon.

- `install-wizard.ico`
  Installer EXE icon.

- `install-wizard.png`
  High-resolution source image for the installer icon.

- `wordmark.png`
  Optional logo/wordmark for docs or future installer branding.

## Recommendations

- `receiver.ico`
  Include multiple sizes if possible:
  - 16x16
  - 32x32
  - 48x48
  - 256x256

- `receiver.png`
  Use a square source image when possible.

- `install-wizard.png`
  Use a square source image when possible.

## Notes

- The Windows build uses `receiver.ico` for PyInstaller.
- The Windows installer build uses `install-wizard.ico` for the setup executable.
- The `.ico` files can be generated from the PNG sources when needed.
