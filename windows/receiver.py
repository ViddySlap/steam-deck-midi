"""Core Windows receiver logic."""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from protocol.messages import ActionEvent, AxisEvent, HeartbeatEvent, ProtocolError, parse_action_event
from windows.config import (
    AxisToCCMapping,
    AxisSplitCCMapping,
    ControlChangeMapping,
    MacroCCMapping,
    MacroSettings,
    MidiMapping,
    NoteMapping,
    RelativeCCMapping,
    StagedNoteMacroMapping,
)
from windows.midi import MidiControlChange, MidiError, MidiIn, MidiOut


LOGGER = logging.getLogger(__name__)

LAYER_UNKNOWN = "unknown"
LAYER_1 = "layer_1"
LAYER_2 = "layer_2"
STICK_ACTIONS = frozenset(
    {
        "L_STICK_UP",
        "L_STICK_DOWN",
        "L_STICK_LEFT",
        "L_STICK_RIGHT",
        "R_STICK_UP",
        "R_STICK_DOWN",
        "R_STICK_LEFT",
        "R_STICK_RIGHT",
        "LEFT_STICK_CLICK_L3",
        "RIGHT_STICK_CLICK_R3",
    }
)

ABXY_LAYER_1_ACTIONS = {"BTN_A", "BTN_B", "BTN_X", "BTN_Y"}
ABXY_LAYER_2_ACTIONS = {
    "BTN_A_LAYER_2",
    "BTN_B_LAYER_2",
    "BTN_X_LAYER_2",
    "BTN_Y_LAYER_2",
}
BUMPER_LAYER_1_ACTIONS = {"L1", "R1", "L2_SOFT", "L2_FULL", "R2_SOFT", "R2_FULL"}
BUMPER_LAYER_2_ACTIONS = {
    "L1_LAYER_2",
    "R1_LAYER_2",
    "L2_SOFT_LAYER_2",
    "L2_FULL_LAYER_2",
    "R2_SOFT_LAYER_2",
    "R2_FULL_LAYER_2",
}
GYRO_LAYER_2_ACTIONS = {"GYRO_FORWARD", "GYRO_BACKWARD"}
@dataclass
class SenderState:
    last_seq: int = -1
    last_seen: float = 0.0


@dataclass
class ActiveMacroFade:
    channel: int
    cc: int
    start_value: int
    target_value: int
    start_time: float
    duration_seconds: float


@dataclass
class ActiveRelativeCC:
    action: str
    channel: int
    cc: int
    step_value: int
    repeat_interval_seconds: float
    next_send_time: float


@dataclass
class ActiveStagedNoteMacro:
    action: str
    modifier_channel: int
    trigger_channel: int
    note: int
    velocity: int
    trigger_time: float
    off_time: float
    refresh_actions: frozenset[str]
    trigger_sent: bool = False


@dataclass
class LayerStatePublisher:
    cc: int
    raw_channel: int
    layer_1_channel: int
    layer_2_channel: int
    state: str = LAYER_UNKNOWN
    last_published_state: str | None = None


class ActionReceiver:
    """Receive action messages and emit mapped MIDI output."""

    def __init__(
        self,
        midi_out: MidiOut,
        mappings: dict[str, MidiMapping],
        *,
        timeout_seconds: float = 2.0,
        macro_settings: MacroSettings | None = None,
        dedupe_window_seconds: float = 0.015,
        stick_dedupe_window_seconds: float = 0.005,
        rate_limit_window_seconds: float = 1.0,
        rate_limit_max_events: int = 200,
        rate_limit_cooldown_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        engine_registry: Any = None,
    ) -> None:
        self._midi_out = midi_out
        self._mappings = mappings
        self._timeout_seconds = timeout_seconds
        self._macro_settings = macro_settings or MacroSettings()
        self._dedupe_window_seconds = dedupe_window_seconds
        self._stick_dedupe_window_seconds = stick_dedupe_window_seconds
        self._rate_limit_window_seconds = rate_limit_window_seconds
        self._rate_limit_max_events = rate_limit_max_events
        self._rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._clock = clock
        self._engine_registry = engine_registry
        self._sender_states: dict[tuple[str, int], SenderState] = {}
        self._active_actions: dict[str, MidiMapping] = {}
        self._active_axis_actions: set[str] = set()
        self._axis_split_directions: dict[str, str] = {}
        self._recent_events: dict[tuple[str, str], float] = {}
        self._event_times: deque[float] = deque()
        self._loop_guard_until = 0.0
        self._macro_values: dict[tuple[int, int], int] = {}
        self._active_macro_fades: dict[tuple[int, int], ActiveMacroFade] = {}
        self._active_relative_ccs: dict[str, ActiveRelativeCC] = {}
        self._active_staged_note_macros: dict[str, ActiveStagedNoteMacro] = {}
        self._abxy_layer_publisher = self._build_layer_publisher("START")
        self._bumper_layer_publisher = self._build_layer_publisher("SELECT")
        self._gyro_layer_publisher = self._build_layer_publisher("L4")
        self._tracked_macro_keys = {
            (mapping.channel, mapping.cc)
            for mapping in mappings.values()
            if isinstance(mapping, MacroCCMapping)
        }
        self._publish_initial_layer_states()

    def _emit_note_on(self, channel: int, note: int, velocity: int) -> bool:
        """Emit a MIDI note_on through the registry's pre-emit filter.

        Returns True if the note was sent, False if an engine filter deferred
        it. Filters can return False to take responsibility for re-emitting
        (e.g. autopilot quantizing a column trigger to the next beat).

        On successful emit, also fans the note out to subscribed engines via
        `on_note_in`. This lets the SteamInput layer tracker self-correct
        from deck button presses (notes 60-70 chaser, 61-71 flash) instead
        of relying solely on the SELECT CC toggle.
        """
        if self._engine_registry is not None:
            allowed = self._engine_registry.should_emit_note(
                channel, note, velocity, self._clock()
            )
            if not allowed:
                LOGGER.debug(
                    "note_on ch=%s note=%s vel=%s deferred by engine filter",
                    channel,
                    note,
                    velocity,
                )
                return False
        self._midi_out.note_on(channel, note, velocity)
        if self._engine_registry is not None:
            self._engine_registry.on_note_in(channel, note, velocity, self._clock())
        return True

    def _emit_cc(self, channel: int, cc: int, value: int) -> None:
        """Emit a MIDI CC and fan it out to subscribed engines.

        Why: deck-originated CCs (e.g. L_TRIGGER_PRESSURE → CC 1 ch0) flow
        OUT via the MIDI output port to Resolume. Engines that listen on
        on_midi_in only see the feedback port, so without this fanout the
        engines never observe deck triggers. This makes "engines subscribe
        to deck CCs directly" actually work for the per-surface V-C-B
        designs (flash_blast / bumper_blast / chaser_stack_dispatcher).
        """
        self._midi_out.control_change(channel, cc, value)
        if self._engine_registry is not None:
            self._engine_registry.on_midi_in(channel, cc, value, self._clock())

    @property
    def fade_poll_interval_seconds(self) -> float | None:
        intervals: list[float] = []
        if self._active_macro_fades:
            intervals.append(self._macro_settings.step_interval_seconds)
        if self._active_relative_ccs:
            intervals.extend(
                active.repeat_interval_seconds for active in self._active_relative_ccs.values()
            )
        if self._active_staged_note_macros:
            intervals.append(0.01)
        if not intervals:
            return None
        return min(intervals)

    def handle_datagram(
        self, payload: bytes, addr: tuple[str, int], now: float | None = None
    ) -> bool:
        timestamp = self._clock() if now is None else now
        self.advance_fades(now=timestamp)
        self.advance_relative_ccs(now=timestamp)
        self.advance_staged_note_macros(now=timestamp)

        try:
            event = parse_action_event(payload)
        except ProtocolError as exc:
            LOGGER.warning("ignored invalid packet from %s:%s: %s", addr[0], addr[1], exc)
            return False

        sender = self._sender_states.setdefault(addr, SenderState())
        if event.seq <= sender.last_seq:
            LOGGER.warning(
                "ignored out-of-order packet from %s:%s seq=%s last_seq=%s",
                addr[0],
                addr[1],
                event.seq,
                sender.last_seq,
            )
            return False

        sender.last_seq = event.seq
        sender.last_seen = timestamp
        if isinstance(event, HeartbeatEvent):
            LOGGER.debug("heartbeat seq=%s from %s:%s", event.seq, addr[0], addr[1])
            return True
        if isinstance(event, AxisEvent):
            return self._handle_axis_event(event)
        if not self._allow_event(event, timestamp):
            return False
        self._update_layer_state_from_action(event, timestamp)
        self._refresh_staged_note_macros(event.action, timestamp)
        try:
            return self._dispatch_event(event, timestamp)
        except MidiError as exc:
            LOGGER.error("MIDI output error while handling %s: %s", event.action, exc)
            self._active_actions.pop(event.action, None)
            return False

    def check_timeouts(self, now: float | None = None) -> bool:
        timestamp = self._clock() if now is None else now
        self.advance_fades(now=timestamp)
        self.advance_relative_ccs(now=timestamp)
        self.advance_staged_note_macros(now=timestamp)
        if not self._sender_states:
            return False

        timed_out = all(
            (timestamp - sender.last_seen) >= self._timeout_seconds
            for sender in self._sender_states.values()
        )
        if not timed_out:
            return False

        if self._active_actions:
            LOGGER.warning("input timeout reached; releasing active MIDI state")
            self.release_all()
        return True

    def release_all(self) -> None:
        for action, mapping in list(self._active_actions.items()):
            try:
                self._release_mapping(action, mapping)
            except MidiError as exc:
                LOGGER.error("MIDI output error while releasing %s: %s", action, exc)
        self._active_actions.clear()
        self._active_macro_fades.clear()
        self._active_relative_ccs.clear()
        for active in list(self._active_staged_note_macros.values()):
            try:
                self._midi_out.note_off(active.modifier_channel, active.note, 0)
            except MidiError as exc:
                LOGGER.error(
                    "MIDI output error while releasing staged note macro %s: %s",
                    active.action,
                    exc,
                )
        self._active_staged_note_macros.clear()
        try:
            self._midi_out.panic()
        except MidiError as exc:
            LOGGER.error("MIDI output error during panic reset: %s", exc)

    def reload_mappings(
        self,
        new_mappings: dict[str, MidiMapping],
        new_macro_settings: MacroSettings | None = None,
    ) -> None:
        """Hot-reload mappings and macro settings. Call from the serve_forever thread."""
        self._mappings = new_mappings
        if new_macro_settings is not None:
            self._macro_settings = new_macro_settings
        self._tracked_macro_keys = {
            (mapping.channel, mapping.cc)
            for mapping in new_mappings.values()
            if isinstance(mapping, MacroCCMapping)
        }
        # Rebuild layer publishers from new mappings
        self._abxy_layer_publisher = self._build_layer_publisher("START")
        self._bumper_layer_publisher = self._build_layer_publisher("SELECT")
        self._gyro_layer_publisher = self._build_layer_publisher("L4")
        LOGGER.info("hot-reloaded mappings: %s actions", len(new_mappings))

    def advance_fades(self, now: float | None = None) -> None:
        timestamp = self._clock() if now is None else now
        if not self._active_macro_fades or timestamp < self._loop_guard_until:
            return

        for key, fade in list(self._active_macro_fades.items()):
            elapsed = max(0.0, timestamp - fade.start_time)
            progress = min(1.0, elapsed / fade.duration_seconds)
            next_value = round(
                fade.start_value + (fade.target_value - fade.start_value) * progress
            )

            if self._macro_values.get(key) != next_value:
                self._send_macro_value(fade.channel, fade.cc, next_value)

            if progress >= 1.0:
                self._active_macro_fades.pop(key, None)

    def handle_midi_feedback(
        self,
        channel: int,
        cc: int,
        value: int,
        *,
        now: float | None = None,
    ) -> bool:
        key = (channel, cc)
        if key not in self._tracked_macro_keys:
            return False

        timestamp = self._clock() if now is None else now
        fade = self._active_macro_fades.get(key)
        if fade is not None:
            expected_value = self._fade_value_at(fade, timestamp)
            current_value = self._macro_values.get(key)
            if self._feedback_matches_active_fade(
                value,
                expected_value=expected_value,
                current_value=current_value,
            ):
                LOGGER.debug(
                    "ignored feedback for active fade channel=%s cc=%s value=%s",
                    channel,
                    cc,
                    value,
                )
                return False

            LOGGER.info(
                "manual override detected; canceling fade channel=%s cc=%s value=%s",
                channel,
                cc,
                value,
            )
            self._active_macro_fades.pop(key, None)

        self._macro_values[key] = value
        LOGGER.debug(
            "updated macro cache from feedback channel=%s cc=%s value=%s",
            channel,
            cc,
            value,
        )
        return True

    def classify_midi_feedback(
        self,
        channel: int,
        cc: int,
        value: int,
        *,
        now: float | None = None,
    ) -> str:
        key = (channel, cc)
        if key not in self._tracked_macro_keys:
            return "untracked_cc"

        fade = self._active_macro_fades.get(key)
        if fade is None:
            return "tracked_update"

        timestamp = self._clock() if now is None else now
        expected_value = self._fade_value_at(fade, timestamp)
        current_value = self._macro_values.get(key)
        if self._feedback_matches_active_fade(
            value,
            expected_value=expected_value,
            current_value=current_value,
        ):
            return "tracked_ignored_active_fade_match"
        return "tracked_manual_override_update"

    def advance_relative_ccs(self, now: float | None = None) -> None:
        timestamp = self._clock() if now is None else now
        if not self._active_relative_ccs or timestamp < self._loop_guard_until:
            return

        for active in list(self._active_relative_ccs.values()):
            while timestamp >= active.next_send_time:
                self._emit_cc(active.channel, active.cc, active.step_value)
                active.next_send_time += active.repeat_interval_seconds

    def advance_staged_note_macros(self, now: float | None = None) -> None:
        timestamp = self._clock() if now is None else now
        if not self._active_staged_note_macros or timestamp < self._loop_guard_until:
            return

        for action, active in list(self._active_staged_note_macros.items()):
            if not active.trigger_sent and timestamp >= active.trigger_time:
                self._emit_note_on(active.trigger_channel, active.note, active.velocity)
                active.trigger_sent = True
            if timestamp < active.off_time:
                continue
            self._midi_out.note_off(active.modifier_channel, active.note, 0)
            self._active_staged_note_macros.pop(action, None)

    def _allow_event(self, event: ActionEvent, timestamp: float) -> bool:
        if timestamp < self._loop_guard_until:
            LOGGER.warning(
                "dropping event during loop-guard cooldown: action=%s state=%s seq=%s",
                event.action,
                event.state,
                event.seq,
            )
            return False

        event_key = (event.action, event.state)
        previous = self._recent_events.get(event_key)
        dedupe_window_seconds = (
            self._stick_dedupe_window_seconds
            if event.action in STICK_ACTIONS
            else self._dedupe_window_seconds
        )
        if previous is not None and (timestamp - previous) < dedupe_window_seconds:
            if event.state == "up" and event.action in self._active_actions:
                self._recent_events[event_key] = timestamp
            else:
                LOGGER.debug(
                    "dropped duplicate event inside %.1fms window: action=%s state=%s seq=%s",
                    dedupe_window_seconds * 1000,
                    event.action,
                    event.state,
                    event.seq,
                )
                self._recent_events[event_key] = timestamp
                return False
            LOGGER.debug(
                "accepting active release inside %.1fms window: action=%s state=%s seq=%s",
                dedupe_window_seconds * 1000,
                event.action,
                event.state,
                event.seq,
            )
        self._recent_events[event_key] = timestamp

        self._event_times.append(timestamp)
        cutoff = timestamp - self._rate_limit_window_seconds
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

        if len(self._event_times) <= self._rate_limit_max_events:
            return True

        self._loop_guard_until = timestamp + self._rate_limit_cooldown_seconds
        self._event_times.clear()
        LOGGER.error(
            "loop guard tripped: received %s events in %.2fs; muting MIDI for %.2fs",
            self._rate_limit_max_events + 1,
            self._rate_limit_window_seconds,
            self._rate_limit_cooldown_seconds,
        )
        self.release_all()
        return False

    def _dispatch_event(self, event: ActionEvent, timestamp: float) -> bool:
        mapping = self._mappings.get(event.action)
        if mapping is None:
            LOGGER.warning("no MIDI mapping for action %s", event.action)
            return False

        if isinstance(mapping, MacroCCMapping):
            handled = self._handle_macro_event(event, mapping, timestamp)
            if handled:
                LOGGER.info("action=%s state=%s seq=%s", event.action, event.state, event.seq)
            return handled
        if isinstance(mapping, RelativeCCMapping):
            handled = self._handle_relative_cc_event(event, mapping, timestamp)
            if handled:
                LOGGER.info("action=%s state=%s seq=%s", event.action, event.state, event.seq)
            return handled
        if isinstance(mapping, StagedNoteMacroMapping):
            handled = self._handle_staged_note_macro_event(event, mapping, timestamp)
            if handled:
                LOGGER.info("action=%s state=%s seq=%s", event.action, event.state, event.seq)
            return handled

        if event.state == "down":
            self._apply_down(mapping)
            self._active_actions[event.action] = mapping
            LOGGER.info("action=%s state=down seq=%s", event.action, event.seq)
            return True

        if event.action in self._active_actions:
            self._release_mapping(event.action, mapping)
            self._active_actions.pop(event.action, None)
        LOGGER.info("action=%s state=up seq=%s", event.action, event.seq)
        return True

    def _apply_down(self, mapping: MidiMapping) -> None:
        if isinstance(mapping, NoteMapping):
            self._emit_note_on(mapping.channel, mapping.note, mapping.velocity)
            return
        if isinstance(mapping, ControlChangeMapping):
            self._emit_cc(mapping.channel, mapping.cc, mapping.on_value)
            return
        if isinstance(mapping, MacroCCMapping):
            raise TypeError("macro mappings must be handled via _handle_macro_event")
        if isinstance(mapping, RelativeCCMapping):
            raise TypeError("relative CC mappings must be handled via _handle_relative_cc_event")
        if isinstance(mapping, StagedNoteMacroMapping):
            raise TypeError(
                "staged note macro mappings must be handled via _handle_staged_note_macro_event"
            )
        raise TypeError(f"unsupported mapping type: {type(mapping)!r}")

    def _release_mapping(self, action: str, mapping: MidiMapping) -> None:
        if isinstance(mapping, NoteMapping):
            self._midi_out.note_off(mapping.channel, mapping.note, 0)
            LOGGER.info("released note mapping for %s", action)
            return
        if isinstance(mapping, ControlChangeMapping):
            self._emit_cc(mapping.channel, mapping.cc, mapping.off_value)
            LOGGER.info("released CC mapping for %s", action)
            return
        if isinstance(mapping, MacroCCMapping):
            return
        if isinstance(mapping, RelativeCCMapping):
            return
        if isinstance(mapping, StagedNoteMacroMapping):
            return
        raise TypeError(f"unsupported mapping type: {type(mapping)!r}")

    def _handle_macro_event(
        self, event: ActionEvent, mapping: MacroCCMapping, timestamp: float
    ) -> bool:
        if event.state != "down":
            return True

        key = (mapping.channel, mapping.cc)
        self._active_macro_fades.pop(key, None)

        current_value = self._macro_values.get(key, self._macro_settings.min_value)
        target_value = self._toggle_target(current_value)

        if mapping.gesture == "click":
            self._send_macro_value(mapping.channel, mapping.cc, target_value)
            return True

        if key not in self._macro_values:
            self._send_macro_value(mapping.channel, mapping.cc, current_value)

        duration = (
            mapping.fade_duration_seconds
            if mapping.fade_duration_seconds is not None
            else self._macro_settings.fade_duration_seconds
        )
        self._active_macro_fades[key] = ActiveMacroFade(
            channel=mapping.channel,
            cc=mapping.cc,
            start_value=current_value,
            target_value=target_value,
            start_time=timestamp,
            duration_seconds=duration,
        )
        self.advance_fades(now=timestamp)
        return True

    def _handle_relative_cc_event(
        self,
        event: ActionEvent,
        mapping: RelativeCCMapping,
        timestamp: float,
    ) -> bool:
        if event.state == "up":
            self._active_relative_ccs.pop(event.action, None)
            return True

        self._cancel_relative_ccs_for_target(mapping.channel, mapping.cc)
        repeat_interval_seconds = mapping.repeat_interval_ms / 1000.0
        self._emit_cc(mapping.channel, mapping.cc, mapping.step_value)
        self._active_relative_ccs[event.action] = ActiveRelativeCC(
            action=event.action,
            channel=mapping.channel,
            cc=mapping.cc,
            step_value=mapping.step_value,
            repeat_interval_seconds=repeat_interval_seconds,
            next_send_time=timestamp + repeat_interval_seconds,
        )
        return True

    def _cancel_relative_ccs_for_target(self, channel: int, cc: int) -> None:
        for action, active in list(self._active_relative_ccs.items()):
            if active.channel == channel and active.cc == cc:
                self._active_relative_ccs.pop(action, None)

    def _handle_staged_note_macro_event(
        self,
        event: ActionEvent,
        mapping: StagedNoteMacroMapping,
        timestamp: float,
    ) -> bool:
        if event.state != "down":
            return True

        existing = self._active_staged_note_macros.pop(event.action, None)
        if existing is not None:
            self._midi_out.note_off(existing.modifier_channel, existing.note, 0)

        delay_ms = (
            mapping.macro_delay_ms
            if mapping.macro_delay_ms is not None
            else self._macro_settings.macro_delay_ms
        )
        hold_ms = (
            mapping.modifier_hold_ms
            if mapping.modifier_hold_ms is not None
            else self._macro_settings.modifier_hold_ms
        )
        self._emit_note_on(mapping.modifier_channel, mapping.note, mapping.velocity)
        self._active_staged_note_macros[event.action] = ActiveStagedNoteMacro(
            action=event.action,
            modifier_channel=mapping.modifier_channel,
            trigger_channel=mapping.trigger_channel,
            note=mapping.note,
            velocity=mapping.velocity,
            trigger_time=timestamp + (delay_ms / 1000.0),
            off_time=timestamp + (hold_ms / 1000.0),
            refresh_actions=frozenset(mapping.refresh_actions),
        )
        return True

    def _refresh_staged_note_macros(self, action: str, timestamp: float) -> None:
        if not self._active_staged_note_macros:
            return

        refreshed = False
        extension = self._macro_settings.modifier_hold_ms / 1000.0
        for active in self._active_staged_note_macros.values():
            if action not in active.refresh_actions:
                continue
            active.off_time = timestamp + extension
            refreshed = True

        if refreshed:
            LOGGER.debug(
                "refreshed staged modifier hold from action=%s until=%.3f",
                action,
                timestamp + extension,
            )

    def _update_layer_state_from_action(self, event: ActionEvent, timestamp: float) -> None:
        if event.state != "down":
            return
        self._handle_layer_toggle_hint(event.action, timestamp)
        self._handle_layer_ground_truth(event.action, timestamp)

    def _handle_layer_toggle_hint(self, action: str, timestamp: float) -> None:
        if action == "START":
            self._toggle_known_layer_state(self._abxy_layer_publisher, timestamp)
        elif action == "SELECT":
            self._toggle_known_layer_state(self._bumper_layer_publisher, timestamp)
        elif action == "L4":
            self._toggle_known_layer_state(self._gyro_layer_publisher, timestamp)

    def _handle_layer_ground_truth(self, action: str, timestamp: float) -> None:
        if action in ABXY_LAYER_1_ACTIONS:
            self._set_layer_state(self._abxy_layer_publisher, LAYER_1, timestamp, action)
        elif action in ABXY_LAYER_2_ACTIONS:
            self._set_layer_state(self._abxy_layer_publisher, LAYER_2, timestamp, action)

        if action in BUMPER_LAYER_1_ACTIONS:
            self._set_layer_state(self._bumper_layer_publisher, LAYER_1, timestamp, action)
        elif action in BUMPER_LAYER_2_ACTIONS:
            self._set_layer_state(self._bumper_layer_publisher, LAYER_2, timestamp, action)

        if action in GYRO_LAYER_2_ACTIONS:
            self._set_layer_state(self._gyro_layer_publisher, LAYER_2, timestamp, action)

    def _toggle_known_layer_state(
        self,
        publisher: LayerStatePublisher | None,
        timestamp: float,
    ) -> None:
        if publisher is None or publisher.state == LAYER_UNKNOWN:
            return
        next_state = LAYER_2 if publisher.state == LAYER_1 else LAYER_1
        self._set_layer_state(publisher, next_state, timestamp, "toggle")

    def _set_layer_state(
        self,
        publisher: LayerStatePublisher | None,
        state: str,
        timestamp: float,
        source: str,
    ) -> bool:
        if publisher is None:
            return False
        changed = publisher.state != state
        if publisher.state not in {LAYER_UNKNOWN, state}:
            LOGGER.info(
                "layer state resync for cc=%s from=%s to=%s via=%s",
                publisher.cc,
                publisher.state,
                state,
                source,
            )
        publisher.state = state
        if publisher.last_published_state == state:
            return changed
        self._publish_layer_state(publisher, timestamp)
        return changed

    def _publish_layer_state(self, publisher: LayerStatePublisher, timestamp: float) -> None:
        # Route through _emit_cc so the layer-state CCs are fanned out to
        # subscribed engines (e.g. gyro_feedback listens on cc 74 ch0/1).
        # The direct _midi_out.control_change path hid the publish from
        # engines, breaking the L4-driven gyro feedback hook.
        if publisher.state == LAYER_2:
            self._emit_cc(publisher.layer_1_channel, publisher.cc, 0)
            self._emit_cc(publisher.layer_2_channel, publisher.cc, 127)
        elif publisher.state == LAYER_1:
            self._emit_cc(publisher.layer_1_channel, publisher.cc, 127)
            self._emit_cc(publisher.layer_2_channel, publisher.cc, 0)
        else:
            self._emit_cc(publisher.layer_1_channel, publisher.cc, 0)
            self._emit_cc(publisher.layer_2_channel, publisher.cc, 0)
        publisher.last_published_state = publisher.state

    def _build_layer_publisher(self, action: str) -> LayerStatePublisher | None:
        mapping = self._mappings.get(action)
        if not isinstance(mapping, ControlChangeMapping):
            return None
        return LayerStatePublisher(
            cc=mapping.cc,
            raw_channel=mapping.channel,
            layer_1_channel=0,
            layer_2_channel=1,
        )

    def _publish_initial_layer_states(self) -> None:
        timestamp = self._clock()
        self._set_layer_state(self._abxy_layer_publisher, LAYER_UNKNOWN, timestamp, "startup")
        self._set_layer_state(self._bumper_layer_publisher, LAYER_UNKNOWN, timestamp, "startup")
        self._set_layer_state(self._gyro_layer_publisher, LAYER_UNKNOWN, timestamp, "startup")

    def _toggle_target(self, current_value: int) -> int:
        midpoint = (self._macro_settings.min_value + self._macro_settings.max_value) / 2
        if current_value > midpoint:
            return self._macro_settings.min_value
        return self._macro_settings.max_value

    def _fade_value_at(self, fade: ActiveMacroFade, timestamp: float) -> int:
        elapsed = max(0.0, timestamp - fade.start_time)
        progress = min(1.0, elapsed / fade.duration_seconds)
        return round(
            fade.start_value + (fade.target_value - fade.start_value) * progress
        )

    def _feedback_matches_active_fade(
        self,
        value: int,
        *,
        expected_value: int,
        current_value: int | None,
    ) -> bool:
        tolerance = self._macro_settings.feedback_match_tolerance
        if abs(value - expected_value) <= tolerance:
            return True
        if current_value is not None and abs(value - current_value) <= tolerance:
            return True
        return False

    def _handle_axis_event(self, event: AxisEvent) -> bool:
        # Fan every axis event to engines first — including ones with no
        # CC mapping (e.g. deck-side state pings like GYRO_STATE_NOW).
        try:
            self._engine_registry.on_axis_event(
                event.action, event.value, self._clock()
            )
        except Exception:  # noqa: BLE001 - engines shouldn't break the loop
            LOGGER.exception("engine_registry.on_axis_event failed")
        mapping = self._mappings.get(event.action)
        if isinstance(mapping, AxisSplitCCMapping):
            return self._handle_axis_split_event(event, mapping)
        if not isinstance(mapping, AxisToCCMapping):
            return False

        if abs(event.value) <= mapping.deadzone:
            if event.action in self._active_axis_actions:
                self._active_axis_actions.discard(event.action)
                center_cc = self._axis_to_cc_value(0, mapping)
                key = (mapping.channel, mapping.cc)
                self._active_macro_fades.pop(key, None)
                self._emit_cc(mapping.channel, mapping.cc, center_cc)
                LOGGER.debug("axis center action=%s cc=%s", event.action, center_cc)
                return True
            return False

        self._active_axis_actions.add(event.action)
        cc_value = self._axis_to_cc_value(event.value, mapping)
        key = (mapping.channel, mapping.cc)
        self._active_macro_fades.pop(key, None)
        self._emit_cc(mapping.channel, mapping.cc, cc_value)
        LOGGER.debug("axis action=%s value=%s cc=%s", event.action, event.value, cc_value)
        return True

    def _handle_axis_split_event(
        self, event: AxisEvent, mapping: AxisSplitCCMapping
    ) -> bool:
        raw = event.value
        pos_key = (mapping.channel, mapping.cc_positive)
        neg_key = (mapping.channel, mapping.cc_negative)
        last_direction = self._axis_split_directions.get(event.action, "zero")

        if abs(raw) <= mapping.deadzone:
            current_direction = "zero"
        elif raw > 0:
            current_direction = "pos"
        else:
            current_direction = "neg"

        transition = current_direction != last_direction
        if transition:
            if last_direction == "pos":
                self._active_macro_fades.pop(pos_key, None)
                self._emit_cc(mapping.channel, mapping.cc_positive, 0)
            elif last_direction == "neg":
                self._active_macro_fades.pop(neg_key, None)
                self._emit_cc(mapping.channel, mapping.cc_negative, 0)
            self._axis_split_directions[event.action] = current_direction

        if current_direction == "zero":
            if transition:
                self._active_axis_actions.discard(event.action)
                LOGGER.debug("axis split center action=%s", event.action)
                return True
            return False

        self._active_axis_actions.add(event.action)
        if current_direction == "pos":
            cc_value = self._axis_split_to_cc_value(raw, mapping)
            self._active_macro_fades.pop(pos_key, None)
            self._emit_cc(mapping.channel, mapping.cc_positive, cc_value)
            LOGGER.debug(
                "axis split + action=%s value=%s cc=%s", event.action, raw, cc_value
            )
        else:
            cc_value = self._axis_split_to_cc_value(-raw, mapping)
            self._active_macro_fades.pop(neg_key, None)
            self._emit_cc(mapping.channel, mapping.cc_negative, cc_value)
            LOGGER.debug(
                "axis split - action=%s value=%s cc=%s", event.action, raw, cc_value
            )
        return True

    def _axis_to_cc_value(self, value: int, mapping: AxisToCCMapping) -> int:
        input_min, input_max = mapping.input_range
        output_min, output_max = mapping.output_range
        clamped = max(input_min, min(input_max, value))
        t = (clamped - input_min) / (input_max - input_min)
        cc = output_min + t * (output_max - output_min)
        return max(0, min(127, round(cc)))

    def _axis_split_to_cc_value(
        self, magnitude: int, mapping: AxisSplitCCMapping
    ) -> int:
        if magnitude >= mapping.input_max:
            return 127
        span = mapping.input_max - mapping.deadzone
        if span <= 0:
            return 127
        t = (magnitude - mapping.deadzone) / span
        return max(0, min(127, round(t * 127)))

    def _send_macro_value(self, channel: int, cc: int, value: int) -> None:
        self._emit_cc(channel, cc, value)
        self._macro_values[(channel, cc)] = value


def serve_forever(
    listen_host: str,
    listen_port: int,
    receiver: ActionReceiver,
    *,
    midi_in: MidiIn | None = None,
    pulse_in: MidiIn | None = None,
    poll_interval: float = 0.25,
    reload_event: threading.Event | None = None,
    reload_config_fn: Callable[[], tuple[dict[str, MidiMapping], MacroSettings]] | None = None,
    engine_registry=None,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((listen_host, listen_port))

    LOGGER.info("listening on udp://%s:%s", listen_host, listen_port)
    if midi_in is not None:
        LOGGER.info(
            "listening for MIDI feedback: name=%s index=%s",
            midi_in.port_name,
            midi_in.port_index if midi_in.port_index is not None else "n/a",
        )
    if pulse_in is not None:
        LOGGER.info(
            "listening for MIDI clock: name=%s index=%s",
            pulse_in.port_name,
            pulse_in.port_index if pulse_in.port_index is not None else "n/a",
        )
    if engine_registry is not None and engine_registry.engines:
        LOGGER.info(
            "engines loaded: %s",
            ", ".join(f"{e.name}({e.type_name})" for e in engine_registry.engines),
        )
    try:
        while True:
            _drain_midi_feedback(receiver, midi_in, engine_registry)
            _drain_midi_clock(pulse_in, engine_registry)
            if engine_registry is not None:
                engine_registry.tick(time.monotonic())
            if reload_event is not None and reload_event.is_set():
                reload_event.clear()
                if reload_config_fn is not None:
                    try:
                        new_mappings, new_macro_settings = reload_config_fn()
                        receiver.reload_mappings(new_mappings, new_macro_settings)
                    except Exception as exc:
                        LOGGER.error("hot-reload failed: %s", exc)
            try:
                fade_poll = receiver.fade_poll_interval_seconds
                timeout = poll_interval if fade_poll is None else min(poll_interval, fade_poll)
                if engine_registry is not None:
                    engine_tick = engine_registry.shortest_tick_interval()
                    if engine_tick is not None:
                        timeout = min(timeout, engine_tick)
                sock.settimeout(timeout)
                payload, addr = sock.recvfrom(4096)
            except socket.timeout:
                _drain_midi_feedback(receiver, midi_in, engine_registry)
                _drain_midi_clock(pulse_in, engine_registry)
                if engine_registry is not None:
                    engine_registry.tick(time.monotonic())
                receiver.advance_fades()
                receiver.check_timeouts()
                continue
            receiver.handle_datagram(payload, addr)
            _drain_midi_feedback(receiver, midi_in, engine_registry)
            _drain_midi_clock(pulse_in, engine_registry)
            if engine_registry is not None:
                engine_registry.tick(time.monotonic())
            receiver.advance_fades()
            receiver.check_timeouts()
    except KeyboardInterrupt:
        LOGGER.info("shutdown requested")
    finally:
        if engine_registry is not None:
            engine_registry.shutdown()
        receiver.release_all()
        sock.close()
        if midi_in is not None:
            midi_in.close()
        if pulse_in is not None:
            pulse_in.close()


def _drain_midi_feedback(
    receiver: ActionReceiver,
    midi_in: MidiIn | None,
    engine_registry=None,
) -> None:
    if midi_in is None:
        return
    for message in midi_in.poll_control_changes():
        _handle_feedback_message(receiver, midi_in, message, engine_registry)


def _drain_midi_clock(
    pulse_in: MidiIn | None,
    engine_registry=None,
) -> None:
    """Drain MIDI System Real-Time messages from `pulse_in` and dispatch."""
    if pulse_in is None or engine_registry is None:
        return
    for message in pulse_in.poll_clock_messages():
        engine_registry.on_midi_clock(message.type, message.received_at)


def _handle_feedback_message(
    receiver: ActionReceiver,
    midi_in: MidiIn,
    message: MidiControlChange,
    engine_registry=None,
) -> None:
    now = time.monotonic()
    route = receiver.classify_midi_feedback(
        message.channel,
        message.control,
        message.value,
        now=now,
    )
    updated = route != "untracked_cc" and route != "tracked_ignored_active_fade_match"
    LOGGER.debug(
        "midi feedback rx ts=%s port=%s channel=%s cc=%s value=%s tracked=%s updated=%s route=%s",
        datetime.now().isoformat(timespec="milliseconds"),
        midi_in.port_name,
        message.channel + 1,
        message.control,
        message.value,
        route != "untracked_cc",
        updated,
        route,
    )
    if engine_registry is not None:
        engine_registry.on_midi_in(
            message.channel,
            message.control,
            message.value,
            now,
        )
    try:
        receiver.handle_midi_feedback(
            message.channel,
            message.control,
            message.value,
            now=now,
        )
    except Exception:
        LOGGER.exception(
            "failed to process MIDI feedback channel=%s cc=%s value=%s",
            message.channel,
            message.control,
            message.value,
        )
