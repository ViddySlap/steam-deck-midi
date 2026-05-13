"""Gyro-driven NestDrop feedback engine (v0.4.4).

Wires the Steam Deck's gyro on/off state to:
1. A NestDrop "feedback" queue advance — toggles a nested Spout Sprite
   on a target deck (Deck 2 by default), creating a visual feedback loop.
2. A Resolume layer master master OSC value — typically the "GYRO FEEDBACK"
   layer that hosts the affected NestDrop deck's spout source.

## Gyro state signal

The engine subscribes to the L4 button's OWN MIDI mapping (ch 2 cc 74
by default — the L4 ControlChangeMapping in windows_midi_map.json).
Each press of L4 fires that CC with value 127 (release fires 0).
Engine treats every value-127 event as a TOGGLE: gyro state flips
on each L4 press. No dependency on the receiver's layer publisher
which requires a "ground truth" gyro motion before L4 has any effect.

Self-tracked state: `gyro_active: bool`. Boots False. Toggles per press.

## Sprite toggle gating

NestDrop's only known OSC for sprite state is a TOGGLE (each
`/Queue/Queue<N>` activate + `/Controls/Deck<M>/btSpace` toggles the
sprite preset on/off). To avoid drift, the engine maintains its own
`sprite_state` model:

- Boot: assume sprite is OFF (matches DefaultUserProfile.xml default).
- Gyro ON transition: if model says sprite_state==OFF, send toggle and
  flip model to ON. If model already says ON, skip toggle (idempotent).
- Gyro OFF transition: symmetric — toggle only if currently ON.
- Resolume layer master is set on EVERY transition (cheap, no drift risk).

If the user manually clicks the sprite in NestDrop UI, model can desync.
Workaround: a TouchOSC "reset gyro feedback" button calling
`POST /api/engines/refresh` resets the model to OFF. Spec links the
recovery path.

Spec: specs/nestdrop-integration.md § Gyro feedback
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from windows.engines._nestdrop_listener import subscribe as listener_subscribe
from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

DEFAULT_TRIGGER_CC = 74
DEFAULT_TRIGGER_CHANNEL = 2
DEFAULT_SPRITE_TRIGGER_PATH = "/PresetID/Queue5/0"
DEFAULT_NESTDROP_HOST = "127.0.0.1"
DEFAULT_NESTDROP_OUT_PORT = 8001  # NestDrop's OSC output broadcast port
DEFAULT_NESTDROP_PORT = 8000
DEFAULT_RESOLUME_LAYER_PATH = "/composition/layers/11/master"
DEFAULT_RESOLUME_LAYER_ON_VALUE = 1.0
DEFAULT_RESOLUME_LAYER_OFF_VALUE = 0.0
DEFAULT_RESOLUME_HOST = "127.0.0.1"
DEFAULT_RESOLUME_PORT = 7000


class GyroFeedbackEngine(Engine):
    type_name = "gyro_feedback"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        nestdrop_osc: OscClient | None = None,
        resolume_osc: OscClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        spawn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        # L4 button raw mapping (channel 2, CC 74 by default). Engine
        # toggles gyro state on every value-127 event. Kept as a fallback
        # path; the authoritative state source is the deck-side
        # GYRO_STATE_NOW axis broadcast handled in `on_axis_event`.
        self._trigger_cc = int(config.get("trigger_cc", DEFAULT_TRIGGER_CC))
        self._trigger_channel = int(
            config.get("trigger_channel", DEFAULT_TRIGGER_CHANNEL)
        )
        # Deck-side state ping action name. The deck sender broadcasts this
        # axis event after every L4 toggle AND every 0.5s, with value 1
        # (gyro on) or 0 (gyro off). Engine sets _gyro_active absolutely
        # from each event, so bridge restarts / missed L4 presses self-heal
        # at the next ping.
        self._state_axis_action = str(
            config.get("state_axis_action", "GYRO_STATE_NOW")
        )

        # Direct sprite-toggle trigger. /PresetID/Queue<N>/<idx> INT(1)
        # toggles the preset at that queue position on its assigned deck,
        # bypassing the active-queue / btSpace mechanic entirely. No
        # cross-engine race possible since this doesn't touch the
        # active-queue state shared across queues on the same deck.
        self._sprite_trigger_path = str(
            config.get("sprite_trigger_path", DEFAULT_SPRITE_TRIGGER_PATH)
        )
        # NestDrop's OSC output broadcast port. Engine subscribes to
        # /Deck<N>/Sprite messages so it always knows the actual sprite
        # state in NestDrop (no drift if the user manually clicks or
        # if NestDrop boots with a different state than assumed).
        listener_cfg = config.get("nestdrop_listener", {})
        self._listener_enabled = bool(listener_cfg.get("enabled", True))
        self._listener_host = str(
            listener_cfg.get("host", "0.0.0.0")
        )
        self._listener_port = int(
            listener_cfg.get("port", DEFAULT_NESTDROP_OUT_PORT)
        )
        nestdrop_osc_cfg = config.get("nestdrop_osc", {})
        self._nestdrop = nestdrop_osc or OscClient(
            host=str(nestdrop_osc_cfg.get("host", DEFAULT_NESTDROP_HOST)),
            port=int(nestdrop_osc_cfg.get("port", DEFAULT_NESTDROP_PORT)),
        )

        # Resolume layer master config
        self._resolume_layer_path = str(
            config.get("resolume_layer_path", DEFAULT_RESOLUME_LAYER_PATH)
        )
        self._resolume_on_value = float(
            config.get("resolume_layer_on_value", DEFAULT_RESOLUME_LAYER_ON_VALUE)
        )
        self._resolume_off_value = float(
            config.get("resolume_layer_off_value", DEFAULT_RESOLUME_LAYER_OFF_VALUE)
        )
        resolume_osc_cfg = config.get("resolume_osc", {})
        self._resolume = resolume_osc or OscClient(
            host=str(resolume_osc_cfg.get("host", DEFAULT_RESOLUME_HOST)),
            port=int(resolume_osc_cfg.get("port", DEFAULT_RESOLUME_PORT)),
        )

        # State model: gyro starts OFF. Each L4 press toggles.
        self._gyro_active: bool = False
        # NestDrop's sprite state across bridge restarts depends on whether
        # the sprite was active when the comp was last saved or last
        # left at the gig. Default to True since Ben's setup boots with
        # the sprite already active (left ON between sessions). Set to
        # False if your NestDrop boots with the sprite inactive — that's
        # the only knob needed to invert the gyro on/off polarity.
        self._sprite_active: bool = bool(
            config.get("initial_sprite_active", True)
        )
        # When True, outputs (NestDrop sprite + Resolume layer master) are
        # driven by the OPPOSITE of _gyro_active. Use this when the show
        # wants "gyro on = feedback hidden, gyro off = feedback visible".
        self._output_inverted: bool = bool(config.get("output_inverted", False))
        self._transition_count = 0
        self._toggle_send_count = 0
        self._layer_send_count = 0

        self._sleep = sleep
        self._spawn = spawn or (
            lambda fn: threading.Thread(target=fn, daemon=True).start()
        )
        self._lock = threading.Lock()

        # Subscribe to NestDrop's OSC output. Each /Deck<N>/Sprite
        # broadcast updates our internal sprite_active so the next
        # toggle decision is always correct relative to NestDrop's
        # actual state.
        if self._listener_enabled:
            listener_subscribe(
                self._listener_host,
                self._listener_port,
                self._on_nestdrop_broadcast,
            )

    # ------------------------------------------------------------------
    # Lifecycle

    def bind_registry(self, registry) -> None:
        """At init, probe NestDrop's current sprite state.

        Per manual page 49, sending the string "?" at `/Controls` (or
        `/Controls/Deck<N>`) makes NestDrop re-send its state bundle.
        We send the query and the listener catches whatever sprite
        broadcasts NestDrop replies with — so by the time the user
        presses L4 for the first time, sprite_active is in sync with
        actual NestDrop state.
        """
        self._spawn(self._probe_nestdrop_state)

    def _probe_nestdrop_state(self) -> None:
        try:
            # Some NestDrop versions accept the query on /Controls;
            # others on /Controls/Deck<N>. Send both forms to be safe.
            self._nestdrop.send("/Controls", "?")
            self._nestdrop.send("/Controls/Deck1", "?")
            self._nestdrop.send("/Controls/Deck2", "?")
        except Exception:
            LOGGER.debug("%s: state-probe send failed", self.name, exc_info=True)

    def refresh(self) -> None:
        """Flip the sprite state model (manual desync recovery).

        Triggered by `POST /api/engines/refresh`. Use after manually
        clicking the sprite in NestDrop UI to re-sync engine's mental
        model with NestDrop's actual sprite state. Does NOT send OSC;
        just flips the boolean. Next gyro transition fires toggle if
        needed.
        """
        with self._lock:
            self._sprite_active = not self._sprite_active
            LOGGER.info(
                "%s: sprite state model flipped (now %s)",
                self.name,
                "ON" if self._sprite_active else "OFF",
            )

    def resync_gyro_polarity(self) -> dict:
        """Flip _gyro_active and immediately re-fire sprite + layer outputs.

        Use when the bridge's gyro state has drifted out of sync with the
        deck's gyro_enabled (e.g. after a bridge restart, or when L4 events
        were missed during UDP sniffing). Each call inverts the polarity
        and pushes outputs to match the new state. Exposed via
        POST /api/engines/gyro-feedback/resync.
        """
        self._handle_gyro_transition()
        with self._lock:
            return {
                "gyro_active": self._gyro_active,
                "sprite_active": self._sprite_active,
                "transition_count": self._transition_count,
            }

    def shutdown(self) -> None:
        try:
            self._nestdrop.close()
        except Exception:
            pass
        try:
            self._resolume.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # NestDrop OSC OUT subscription — keep sprite_active synced

    def _on_nestdrop_broadcast(self, address: str, args: list) -> None:
        """Update sprite_active from NestDrop's /Deck<N>/Sprite broadcasts.

        Broadcast format (per page 51 of the manual + sniffer confirm):
        /Deck<N>/Sprite [<preset_path:str>, <name:str>, <active:int>,
                         <mode:str>, <fx:int>, <overlay_count:int>,
                         <nested_count:int>]

        Match by preset_path equality. The deck number in the address
        doesn't need to match — sprite state is identified by preset path.
        """
        if not address.startswith("/Deck") or not address.endswith("/Sprite"):
            return
        if len(args) < 3:
            return
        if args[0] != self._sprite_trigger_path:
            return
        try:
            broadcast_active = bool(int(args[2]))
        except (TypeError, ValueError):
            return
        with self._lock:
            if self._sprite_active != broadcast_active:
                self._sprite_active = broadcast_active
                LOGGER.info(
                    "%s: sprite state synced from broadcast: %s",
                    self.name,
                    "ON" if broadcast_active else "OFF",
                )

    # ------------------------------------------------------------------
    # Inbound: deck-side state broadcast (authoritative)

    def on_axis_event(self, action: str, value: int, now: float) -> None:
        """Set gyro state absolutely from deck's GYRO_STATE_NOW broadcast.

        Authoritative source for `_gyro_active`. Each broadcast is
        idempotent — repeats no-op once in the correct state. Recovers
        from any drift (bridge restart, missed L4 events, etc.) within
        the broadcast cadence (0.5s by default).
        """
        if action != self._state_axis_action:
            return
        self._set_gyro_state(value != 0)

    # ------------------------------------------------------------------
    # State transitions
    #
    # NOTE: The L4 toggle CC (ch 2 / cc 74) is no longer consumed here.
    # It was a legacy "toggle on each press" fallback, but the deck-side
    # GYRO_STATE_NOW broadcast is now authoritative — sent immediately on
    # every L4 toggle AND every 0.5s. Listening to both produced a
    # double-fire stutter (GYRO_STATE_NOW set state, L4 toggled it back,
    # next heartbeat corrected it). Single source of truth = no stutter.

    def _handle_gyro_transition(self) -> None:
        """Toggle gyro state. Kept for `resync_gyro_polarity` manual override."""
        with self._lock:
            new_active = not self._gyro_active
        self._set_gyro_state(new_active)

    def _set_gyro_state(self, active: bool) -> None:
        """Set gyro state absolutely. Idempotent: no-op if already matching."""
        need_toggle = False
        with self._lock:
            if active == self._gyro_active:
                return
            self._gyro_active = active
            self._transition_count += 1
            # Outputs follow gyro state, optionally inverted (see __init__).
            desired_outputs_on = active != self._output_inverted
            if desired_outputs_on != self._sprite_active:
                need_toggle = True
                self._sprite_active = desired_outputs_on
        # OSC sends outside the lock + on a daemon thread.
        self._spawn(
            lambda: self._fire_osc(
                active=active, outputs_on=desired_outputs_on, toggle=need_toggle
            )
        )

    def _fire_osc(self, *, active: bool, outputs_on: bool, toggle: bool) -> None:
        # Single-message sprite trigger. Each call flips NestDrop's
        # sprite state. We send it only on actual gyro transitions
        # (toggle=True) so the model stays aligned with NestDrop.
        if toggle:
            try:
                self._nestdrop.send(self._sprite_trigger_path, 1)
                self._toggle_send_count += 1
                LOGGER.info(
                    "%s: gyro %s -> sprite toggle (%s)",
                    self.name,
                    "on" if active else "off",
                    self._sprite_trigger_path,
                )
            except Exception:
                LOGGER.exception("%s: NestDrop sprite toggle send failed", self.name)
        else:
            LOGGER.info(
                "%s: gyro %s -> sprite already in correct state (no toggle)",
                self.name,
                "on" if active else "off",
            )
        # Resolume layer master: always set, every transition (no drift risk).
        layer_value = self._resolume_on_value if outputs_on else self._resolume_off_value
        try:
            self._resolume.send(self._resolume_layer_path, layer_value)
            self._layer_send_count += 1
        except Exception:
            LOGGER.exception("%s: Resolume layer master send failed", self.name)

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "gyro_active": self._gyro_active,
            "sprite_active": self._sprite_active,
            "trigger_cc": self._trigger_cc,
            "trigger_channel": self._trigger_channel,
            "sprite_trigger_path": self._sprite_trigger_path,
            "resolume_layer_path": self._resolume_layer_path,
            "transition_count": self._transition_count,
            "toggle_send_count": self._toggle_send_count,
            "layer_send_count": self._layer_send_count,
            "output_inverted": self._output_inverted,
        }
