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

## Device Selection

The Deck launcher currently uses xinput device id `5` by default.

That value is stored in:

- `config/deck_runtime_settings.local.json`

If needed later, it can be changed there manually.
