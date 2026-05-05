# Windows Receiver

This receiver provides:

- UDP listener for JSON action events
- protocol validation for `action`, `state`, and `seq`
- per-sender sequence filtering for out-of-order packets
- action-to-MIDI mapping loaded from the active preset in `config/presets/`
- timeout and shutdown failsafes that release active notes/controls
- optional MIDI feedback input on a separate port such as `DECK_OUT`
- receiver-side cache for tracked `macro_cc` parameters
- manual Resolume override for active fades when inbound feedback diverges
- browser-based Mapping UI with live hot-reload, preset management, and macro library
- system tray icon with UI shortcut and quit

## Message Format

Incoming UDP datagrams are UTF-8 JSON objects:

```json
{
  "action": "BTN_A",
  "state": "down",
  "seq": 1,
  "profile_name": "default",
  "profile_hash": "abc123"
}
```

Required fields:

- `action`
- `state` with value `down` or `up`
- `seq` as a non-negative integer

## Preset System

Mappings are stored as named preset files in `config/presets/`. The active preset is tracked in
`config/presets/.active`. On first run, `ensure_presets_initialized()` bootstraps the directory
from `config/windows_midi_map.json` if it does not already exist.

The factory file `config/windows_midi_map.json` is never modified at runtime. "Factory Reset" in
the UI overwrites the currently active preset with its content, leaving other presets intact.

## Mapping UI

When the receiver starts, a browser-based editor opens automatically at `http://127.0.0.1:7723`.
It provides:

- **Mappings tab**: click any button chip to edit its mapping inline; Save & Apply hot-reloads
  the receiver without restarting
- **Macro Library tab**: saved behavior templates that can be applied to any compatible button;
  templates store gesture/timing/step fields only, not MIDI targeting
- **Global Settings tab**: edit `macro_settings` and `analog_settings` values

Use `--no-ui` to disable the UI and tray, or `--ui-port` to change the port (default 7723).

## MIDI Map Format

Preset files use the same JSON format as `config/windows_midi_map.json`:

```json
{
  "macro_settings": {
    "fade_duration_seconds": 2.0,
    "update_hz": 30,
    "min_value": 0,
    "max_value": 127
  },
  "mappings": {
    "BTN_A": { "type": "note", "channel": 0, "note": 60, "velocity": 127 },
    "DPAD_UP": { "type": "macro_cc", "channel": 0, "cc": 22, "gesture": "click" },
    "DPAD_UP_LONG_PRESS": {
      "type": "macro_cc",
      "channel": 0,
      "cc": 22,
      "gesture": "long_press",
      "fade_duration_seconds": 3.0
    }
  }
}
```

Supported mapping types:

- `note`
- `cc`
- `macro_cc`
- `relative_cc`
- `staged_note_macro`
- `axis_to_cc`

`macro_cc` uses the same CC for click and long-press actions. A click toggles immediately between
the configured min/max values, while a long press starts a receiver-side linear fade to the opposite
value and continues to completion even after button release. An optional `fade_duration_seconds`
field overrides the global `macro_settings.fade_duration_seconds` for that mapping only.

`relative_cc` emits repeated CC ticks while the action is held. It is intended for Resolume
relative encoder mappings such as clip browser scrolling. The receiver does not cache state for
these mappings; each sent CC value is a standalone increment/decrement step.

`staged_note_macro` sends a modifier `note_on` first, waits for a configured delay, then sends a
second trigger `note_on` on a different channel using the same note number. The modifier note is
held for a fixed receiver-side duration and then released automatically. Optional
`macro_delay_ms` and `modifier_hold_ms` fields override the global `macro_settings` values.

`axis_to_cc` maps a continuous analog axis value to a MIDI CC. Requires `input_range` (two-element
integer list), `output_range` (0–127 two-element integer list), `deadzone`, and `curve`
(`linear`, `quadratic`, or `s_curve`).

The receiver also maintains authoritative layer-state publishers for the Steam Input toggle layers:
- ABXY layer state uses the `START` CC number on Channels 1 and 2 as explicit Layer 1 / Layer 2 lamps
- bumper/trigger layer state uses the `SELECT` CC number on Channels 1 and 2 as explicit Layer 1 / Layer 2 lamps
- raw `START` and `SELECT` button presses remain available on Channel 3 as momentary CCs for MIDI Learn
- layer state self-heals from ground-truth action IDs such as `BTN_A_LAYER_2` or `L1_LAYER_2`
- lamp updates are sent on state change or resync only; the receiver does not continuously refresh them

Tracked `macro_cc` parameters are also the current feedback/cache subset. When `--feedback-port` is
configured, inbound CC feedback on the same channel/CC updates the cache. During an active fade, the
receiver ignores matching feedback values but cancels the fade if Resolume reports a different value,
so manual movement in Resolume wins over automation.

## Running

Dry-run mode logs MIDI events without requiring a real MIDI port, and opens the Mapping UI:

```bash
python -m windows.win_recv --map config/windows_midi_map.json --dry-run --verbose
```

To run without the browser UI or tray:

```bash
python -m windows.win_recv --map config/windows_midi_map.json --dry-run --no-ui
```

Send a test packet from the same machine:

```bash
python3 -m protocol.send_test --action BTN_A --state tap --target 127.0.0.1:45123
```

For real Windows MIDI output, install a `mido`-compatible backend on Windows and run:

```bash
py -m pip install -r requirements.txt
py -m windows.list_midi_ports
py -m windows.win_recv --map config/windows_midi_map.json --midi-port "DECK_IN" --feedback-port "DECK_OUT" --verbose
```

Use separate loopMIDI ports for each direction:

- `DECK_IN`: receiver output into Resolume MIDI input
- `DECK_OUT`: Resolume MIDI output back into the receiver for selected feedback-enabled mappings

Do not point Resolume MIDI output back at `DECK_IN`.

## Limitations

- WSL cannot fully validate Windows MIDI port behavior.
- Sequence handling currently assumes monotonically increasing integer counters.
- A receiver-side loop guard drops ultra-fast duplicate events and temporarily mutes output if the incoming event rate spikes abnormally.
- Startup cache initialization from inbound feedback is not implemented.
- Real MIDI output must be validated on Windows proper with loopMIDI or another visible output port.
