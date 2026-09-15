# Autopilot channel state across restarts

A bridge crash or restart mid-show used to turn every autopilot channel off:
the engine rebuilt its channels from config defaults. Since sdauto A1 the
engine keeps the operator's choices on disk and puts them back.

## What persists

Per channel (`video`, `fx`, `logo`), the five user-intent fields the Wire patch
sets:

| Field | Stored as |
| --- | --- |
| `enabled` | boolean |
| `beats_per_clip` | integer (the looked-up beats, not the CC value) |
| `transition_seconds` | number (seconds, not the CC value) |
| `clip_mode` | mode NAME: `NONE`, `LINEAR` or `RANDOM` |
| `layer_enabled` | object, layer number as a string key to boolean |

## What does not persist, and why

`cycle_index`, `beat_in_clip`, `visible_layer`, `target_layer`,
`crossfade_start_time`, `bag`, `last_clip` and `clip_count_cache` are runtime
position, not intent. They describe a moment (a crossfade start is a monotonic
clock reading that means nothing in a new process; a clip bag and clip counts
belong to a composition that may have changed). A restarted engine starts them
fresh, exactly as v0.4.9 did.

## The file

`config/state/autopilot_channels.local.json`, beside `config/engines/` (never
inside it: every `*.json` there is loaded as an engine). On an installed
Windows bridge that is `C:\Program Files\STEAMDECK MIDI Receiver 2\config\state\`
(the installer grants users modify on `config`). It is machine-local and
git-ignored.

```json
{
  "engines": {
    "Autopilot": {
      "channels": {
        "video": {"beats_per_clip": 8, "clip_mode": "RANDOM", "enabled": true,
                  "layer_enabled": {"1": true, "2": false, "3": true, "4": false},
                  "transition_seconds": 2.52}
      }
    }
  },
  "schema": 1
}
```

Keys are the engine instance name, then the channel key. Entries for other
engine names are kept when the file is rewritten.

## When it is written

On every change to one of the five fields (a Wire patch CC that actually
changes the value, or the clear route). `on_midi_in` only hands a snapshot to a
writer thread; the file I/O never runs on the receiver loop. The writer always
writes the newest snapshot (temp file in the same directory, fsync, then
`os.replace`), so a fader drag coalesces rather than queueing. Engine shutdown
waits for the last change to reach disk. A write failure is logged at most once
per 60 seconds and never raises into the MIDI path; the next change retries.

## Restore

On construction, the persisted fields overlay the config defaults for channels
and layers that still exist in config; unknown channels or layers are ignored
and logged once. A malformed file, a wrong field type, or a schema newer than
this build keeps the defaults and leaves the file byte-identical until the next
valid change replaces it.

The Resolume side effects of a restore run on the engine's FIRST dispatch (the
first feedback CC, clock message or tick the registry delivers), through the
same code a live CC uses: a restored `transition_seconds` is pushed to the
selected layers, and a restored `enabled: true` runs the enable path
(`_snap_to_first_selected`: layer masters and transitions). They are deferred
from construction because the registry delivers nothing to an inactive engine:
a preset that keeps autopilot off must not have it write layer masters at
startup, just as it would ignore a live enable CC.

## How to clear it

- `POST /api/engines/autopilot/state/clear` resets every channel's five fields
  to config defaults (all channels and layers off, default beats, transition
  and mode), writes that to the file, and returns `{"ok": true, "persisted":
  <bool>, "channels": {...}}`. It deletes nothing.
- Or stop the bridge and delete `config/state/autopilot_channels.local.json`.

## Not covered

`autopilot_ptz` does not use this: it has its own channel state and the same
restart hazard (see docs/sdauto-a1/REPORT.md).
