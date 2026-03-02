# Steam Deck Install

Steam Deck uses a native Linux installer script, not a Windows `.exe`.

## One-File Installer

The downloadable installer entrypoint is:

```text
STEAMDECK-MIDI-SENDER-SETUP.sh
```

It will:

- clone or update the repo into `~/steam-deck-vj`
- create `config/deck_runtime_settings.local.json` if missing
- create two desktop launchers:
  - `Learn Steam Input Map`
  - `STEAMDECK-MIDI-SENDER`

## Install

From the Steam Deck terminal in Desktop Mode:

```bash
bash ./STEAMDECK-MIDI-SENDER-SETUP.sh
```

## Sender Presets

When `STEAMDECK-MIDI-SENDER` starts:

- it loads the saved target presets
- shows a numbered preset list
- always includes `Create new preset`
- asks for:
  - target IP address
  - target name
- saves the preset and returns to the preset list

Selecting a preset starts sender mode against that target IP on UDP port `45123`.

## First-Run Device Setup

If no xinput device id is saved yet, the launcher will:

- show the current `xinput list` output
- ask for the Steam Input xinput device id
- save it into `config/deck_runtime_settings.local.json`

The value is reused by both the sender and the learn wizard.
