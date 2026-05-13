---
title: NestDrop Integration (Queue Advance Engine)
slug: nestdrop-integration
status: in_progress
priority: 3
created: 2026-05-13
last_updated: 2026-05-13
agent_runnable: true
depends_on: [feedback-rework, feedback-engine-investigation]
parent_research: wiki/research/feedback-options.md
---

# NestDrop Integration (Queue Advance Engine)

## Goal

Drive NestDrop's per-deck queue advance from the Steam Deck's X (Deck 1)
and B (Deck 2) buttons, gated by Resolume Layer 9's ~1.25s feedback fade
so that rapid double-tap re-flashes the same preset and single-tap-then-wait
advances to a new preset.

## Architecture (final, post-2026-05-13 grilling + live OSC probe)

```
Steam Deck X press (CHASER or FLASH SteamInput layer)
  ├── existing path: bridge emits note 40 or 41 on ch0
  │      → Resolume MIDI Learn fires Layer 9 col 1
  │      → master 0→1, fades to 0 over ~1.25s
  └── new: nestdrop_engine.on_note_in sees the same note
       → both treated as "X press" for Deck 1
       → if no timer armed: start 1.25s threading.Timer(_advance, deck=1)
       → if timer already armed: cancel + re-flash (no advance)
       → on timer expiry: send /Controls/Deck1/btSpace INT32(1) via OSC
         NestDrop advances its own queue position internally
         next X press flashes the new preset (which NestDrop has already loaded)
```

Bridge is stateless. NestDrop owns its queue position per deck. The engine
just times button presses and pokes NestDrop's "next preset" trigger.

## Key locked decisions

- **`/Controls/Deck<N>/btSpace INT32(1)` is the advance trigger.** Discovered
  via NestDrop's built-in OSC Path discovery (left-click any control in
  Settings to see its OSC path; the Spacebar default-hotkey area exposes
  the per-deck path). Confirmed live for both Deck 1 and Deck 2 via OSC
  probe (2026-05-13).
- **No XML parsing, no preset library scanning, no path resolution.**
  NestDrop manages its own queue state. Bridge sends a 1-arg OSC trigger
  and trusts NestDrop to do the right thing. This was the big simplification
  vs. the original `/Deck<N>/Preset <path> <name> 1 1 1.0` design.
- **2 decks (1 and 2), no SteamInput-layer queue swap.** Engine subscribes
  to X notes on both CHASER (40) and FLASH (41) layer publishers and B
  notes on both (38 + 39); all treat as one logical press per button.
- **1.25s fade window is a configurable engine knob.** Resolume's actual
  fade source is not REST-visible (likely a hand-set master parameter
  animation). If Ben changes the visual fade, the engine config must move
  in lockstep.
- **NestDrop OSC Input must be enabled** in NestDrop UI before this works.
  Defaults to disabled in `DefaultUserProfile.xml` even on Pro. Engine
  doesn't probe this state; if NestDrop isn't listening, the OSC just
  drops on the floor and the bridge no-ops gracefully.

## Phase 0 findings (verified 2026-05-13)

### NestDrop OSC config

From `C:/Users/Ben/OneDrive/Documents/NestDrop/DefaultUserProfile.xml`:

```xml
<Settings_General
    OscInputEnable="True"     ← enabled in this session
    OscOutputEnable="False"
    OscPort="8000"             ← OSC In port
    OscOutputPort="8001"
    OscOutputIp="127.0.0.1" />
```

### MIDI map: X/B button identities

From `config/windows_midi_map.json`. X and B are NOTES (not CCs) on channel 0:

| Button | SteamInput layer | Channel | Note |
|--------|------------------|---------|------|
| BTN_X | CHASER (default) | 0 | 40 |
| BTN_X_LAYER_2 | FLASH | 0 | 41 |
| BTN_B | CHASER | 0 | 38 |
| BTN_B_LAYER_2 | FLASH | 0 | 39 |

Engine subscribes via `on_note_in(channel, note, velocity, now)`.

### Confirmed NestDrop OSC paths (live-tested)

| Path | Args | Effect |
|------|------|--------|
| `/Controls/Deck1/btSpace` | `INT32(1)` | Advance Deck 1's currently-assigned queue to next preset |
| `/Controls/Deck2/btSpace` | `INT32(1)` | Advance Deck 2's currently-assigned queue to next preset |

Discovery mechanism: NestDrop UI → Settings → OSC Path textbox. Left-click any
control / button / preset in NestDrop to see its OSC path appear in the textbox.

### 1.25s fade source on Layer 9 — NOT REST-visible

Investigated; not exposed via `/api/v1/composition`. Bridge uses 1.25s as a
configurable default. If Ben ever tunes the visual fade, the engine config
knob must move with it.

## Bridge engine spec

Module: `windows/engines/nestdrop_engine.py`. Subclass `Engine`. ~150 lines.

### State per deck

```python
@dataclass
class DeckState:
    deck: int
    timer: threading.Timer | None = None
    timer_armed_at: float = 0.0
    advance_count: int = 0
    cancel_count: int = 0
    press_count: int = 0
```

No preset list, no current_index. NestDrop owns the queue position.

### Behavior

```python
def on_note_in(self, channel, note, velocity, now):
    if channel != self._channel or velocity == 0:
        return
    if note in self._x_notes:    self._handle_press(deck=1, now=now)
    elif note in self._b_notes:  self._handle_press(deck=2, now=now)

def _handle_press(self, deck, now):
    state = self._decks[deck]
    if state.timer is not None and state.timer.is_alive():
        state.timer.cancel(); state.timer = None
        # no advance; NestDrop hasn't moved, Resolume re-flashes same preset
        return
    state.timer = self._timer_factory(self._fade_window, self._advance, args=(deck,))
    state.timer.start()

def _advance(self, deck):
    addr = self._osc_path_template.format(deck=deck)
    self._osc.send(addr, 1)   # /Controls/Deck<N>/btSpace INT32(1)
```

### Config (factory default)

`config/engines.factory/nestdrop.json`:

```json
{
  "name": "NestDrop",
  "type": "nestdrop",
  "enabled": true,
  "inputs": {
    "channel": 0,
    "x_notes": [40, 41],
    "b_notes": [38, 39]
  },
  "fade_window_seconds": 1.25,
  "osc": {"host": "127.0.0.1", "port": 8000},
  "osc_path_template": "/Controls/Deck{deck}/btSpace"
}
```

## Implementation status

### Phase 0 — Pre-build verification (DONE 2026-05-13)

- NestDrop OSC ports discovered (8000 in, 8001 out, 127.0.0.1).
- X/B note identities pinned from MIDI map.
- Live OSC probe confirmed `/Controls/Deck<N>/btSpace INT32(1)` works for
  both decks (Ben visually confirmed Queue1→Deck1 and Queue2→Deck2 advanced).
- Layer 9 1.25s fade source not REST-visible; use configurable default.

### Phase 1 — NestDrop curation (ongoing, Ben at own pace)

Queue1 (5 presets) and Queue2 (4 presets) already exist. Ben curates more
on his own time. Engine doesn't care about count.

### Phase 2 — Engine code (DONE 2026-05-13)

- `windows/engines/nestdrop_engine.py` — ~150 lines, Engine ABC subclass.
- `config/engines.factory/nestdrop.json` — factory default.
- `tests/test_nestdrop_engine.py` — 13 tests, all passing.
- Registered in `windows/engines/registry.py` (10 engine types total now).

### Phase 3 — Live test (NEXT SESSION)

Plan:

- Start dev bridge. Verify 10 engines load (was 9).
- Single-tap X on Steam Deck → Layer 9 flashes → after 1.25s, NestDrop
  advances Deck 1 → next X press shows new preset.
- Double-tap X within 1.25s → bridge logs "re-press within fade window;
  advance cancelled" → same preset flashes both times.
- Same for B / Deck 2.
- Both SteamInput layers (note 40 vs note 41 for X) yield identical NestDrop
  behavior.

### Phase 4 — Ship gate

- 4.1 Bump version.py to 0.4.4.
- 4.2 Final wiki/log.md entry.
- 4.3 Build installer + GitHub release.
- Blocked on v0.4.3 ship (P5 OSC Sync engineenable bug, P4 tray decisions).

## Files touched this session

New:
- `windows/engines/nestdrop_engine.py`
- `tests/test_nestdrop_engine.py`
- `config/engines.factory/nestdrop.json`

Updated:
- `windows/engines/osc_client.py` (added `send_multi` — not used by final
  engine since `send` handles single INT32 fine, but kept for future engines)
- `windows/engines/registry.py` (registered `NestdropEngine`)
- `tests/_engine_helpers.py` (added `send_multi` to `FakeOscClient`)
- `wiki/components/engine-framework.md` (nestdrop entry)
- `wiki/log.md` (session entry)
- This spec.

Deleted:
- `windows/engines/_nestdrop_profile.py` (XML parser was never needed)

## Out of scope

- Spout Sprite feedback loop, audio-reactive queue weighting, Sprite/text
  overlays, ASIO routing, preset authoring, OSC Output subscription (engine
  doesn't read NestDrop state — NestDrop owns it).

## Acceptance test (Phase 3)

Per deck, both buttons:

1. Single press → Layer 9 flashes; bridge log shows `deck N advance
   (/Controls/DeckN/btSpace)` ~1.25s later.
2. Wait 2 seconds. Second press → Layer 9 flashes a DIFFERENT preset.
3. Two rapid presses within 1.25s → flashes same preset twice → bridge
   log shows "re-press within fade window; advance cancelled".
4. Switch SteamInput layer (note 40 → note 41 for X) → identical behavior;
   no perceptible difference.

## Wiki context

- `wiki/components/engine-framework.md` — Engine ABC + EngineRegistry pattern
- `wiki/operations/midi-osc-binding-workflows.md` — protocol preference + hot-path hazard
- `wiki/research/feedback-options.md` — original research
- `wiki/log.md` 2026-05-13 entry — this session
- NestDrop manual: `C:/Users/Ben/OneDrive/Documents/NestDrop/NestDrop User Manual V2.x.1.3.pdf` pages 30-52 (OSC discovery + Output + Default Hotkeys)
