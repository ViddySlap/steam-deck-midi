# Windows Branding Assets

Drop Windows branding assets for packaging here.

## Expected Files

- `appicon.ico`
  Primary Windows icon for:
  - `STEAMDECK-MIDI-RECEIVER.exe`
  - installer EXE
  - desktop and Start Menu shortcuts

- `appicon.png`
  Optional high-resolution source image for future exports and docs.

- `wordmark.png`
  Optional logo/wordmark for docs or future installer branding.

## Recommendations

- `appicon.ico`
  Include multiple sizes if possible:
  - 16x16
  - 32x32
  - 48x48
  - 256x256

- `appicon.png`
  Use a square source image when possible.

- `wordmark.png`
  Use a transparent background if possible.

## Notes

- The packaging scripts do not use these assets yet.
- Once you add them, the next step is wiring them into PyInstaller and Inno Setup.
