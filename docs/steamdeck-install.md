# Steam Deck Install

Steam Deck uses a native Linux installer script, not a Windows `.exe`.

## Installer Bundle

The downloadable Steam Deck installer bundle is:

```text
STEAMDECK-MIDI-SENDER-SETUP.tar.gz
```

After extraction, the double-click installer entrypoint is:

```text
steamdeck-midi-installer/STEAMDECK-MIDI-INSTALL.desktop
```

It will:

- clone or update the repo into `~/steam-deck-midi`
- create `config/deck_runtime_settings.local.json` if missing
- create desktop launchers:
  - `Learn Steam Input Map`
  - `STEAMDECK-MIDI-SENDER`
  - `VJ Mode`
- create VJ Mode runtime files:
  - `~/vj-mode/vj_mode.sh`
  - `~/vj-mode/vj_mode_status.py`
  - `~/vj-mode/vj_mode.env` (created once and preserved on updates)

## Install

From Steam Deck Desktop Mode:

1. Extract `STEAMDECK-MIDI-SENDER-SETUP.tar.gz`.
2. Open the extracted `steamdeck-midi-installer` folder.
3. Double-click `STEAMDECK-MIDI-INSTALL.desktop`.

SteamOS may ask for one-time permission to execute the launcher because it was downloaded from the internet.

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

## VJ Mode

`VJ Mode` is a Game Mode launcher helper that starts TouchOSC with a target layout
and can optionally start InputLeap (headless) and the Deck sender.

Default TouchOSC target layout:

- `~/Documents/TouchOSC/STEAMDECK V1.tosc`

Local VJ overrides live in:

- `~/vj-mode/vj_mode.env`

## Device Selection

The Deck launcher currently uses xinput device id `5` by default.

That value is stored in:

- `config/deck_runtime_settings.local.json`

If needed later, it can be changed there manually.
