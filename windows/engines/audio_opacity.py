"""Audio opacity engine.

Listens to the comp-level `Audio Engine` Wire patch on DECK_OUT (CC 100-106 on
ch15 by default) and drives the VIDEO + LOGO group masters on DECK_IN
(CC 110/111 on ch15 by default).

Logic mirrors the original per-group `Opacity` Wire patch, but with the
threshold/sample/duration/transition logic moved into this module so it can be
extended (auto-bypass, more engines) without touching the Wire patch.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)


def _midpoint_bool(value: int) -> bool:
    return value > 63


class AudioOpacityEngine(Engine):
    type_name = "audio_opacity"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        inputs = config.get("inputs", {})
        outputs = config.get("outputs", {})
        defaults = config.get("defaults", {})

        # Inputs (mido channels are 0-indexed; Wire's "Channel 15" = mido 14)
        self._input_channel = int(inputs.get("channel", 14))
        self._cc_audio = int(inputs.get("cc_audio", 100))
        self._cc_enable = int(inputs.get("cc_enable", 101))
        self._cc_video_stomp = int(inputs.get("cc_video_stomp", 102))
        self._cc_logo_stomp = int(inputs.get("cc_logo_stomp", 103))
        self._cc_tipping = int(inputs.get("cc_tipping", 104))
        self._cc_duration = int(inputs.get("cc_duration", 105))
        self._cc_transition = int(inputs.get("cc_transition", 106))
        self._duration_max_seconds = float(inputs.get("duration_max_seconds", 5.0))
        self._transition_max_seconds = float(inputs.get("transition_max_seconds", 10.0))

        # Outputs — protocol: "osc" (default) | "midi"
        self._output_protocol = str(outputs.get("protocol", "osc")).lower()
        # OSC routing
        osc = outputs.get("osc", {})
        self._osc_host = str(osc.get("host", "127.0.0.1"))
        self._osc_port = int(osc.get("port", 7000))
        self._osc_video_path = str(osc.get("video_path", "/composition/groups/1/master"))
        self._osc_logo_path = str(osc.get("logo_path", "/composition/groups/2/master"))
        self._osc: OscClient | None = (
            OscClient(self._osc_host, self._osc_port) if self._output_protocol == "osc" else None
        )
        # MIDI routing (kept as fallback if user picks "midi")
        self._output_channel = int(outputs.get("channel", 0))
        self._cc_video_master = int(outputs.get("cc_video_master", 110))
        self._cc_logo_master = int(outputs.get("cc_logo_master", 111))

        # Defaults / runtime config
        self._sample_size = int(config.get("sample_size", 8))
        self._update_hz = float(config.get("update_hz", 30.0))
        self._tipping_point = float(defaults.get("tipping_point", 0.65))
        self._duration_seconds = float(defaults.get("duration_seconds", 1.0))
        self._transition_seconds = float(defaults.get("transition_seconds", 1.5))

        # State
        self._enabled = False
        self._video_stomp = False
        self._logo_stomp = False
        self._audio_buffer: deque[float] = deque(maxlen=self._sample_size)
        self._below_since: float | None = None
        # target = where we want masters to be; current = smoothed value emitted
        # When engine is OFF we drive both to 1.0 (full on, manual takeover).
        self._target_video = 1.0
        self._target_logo = 1.0
        self._current_video = 1.0
        self._current_logo = 1.0
        self._last_video_sent: int | None = None
        self._last_logo_sent: int | None = None
        self._last_tick = 0.0
        # Send initial 127/127 so masters are full on at startup.
        self._initial_send_pending = True

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel:
            return
        if cc == self._cc_audio:
            self._audio_buffer.append(value / 127.0)
        elif cc == self._cc_enable:
            self._enabled = _midpoint_bool(value)
        elif cc == self._cc_video_stomp:
            self._video_stomp = _midpoint_bool(value)
        elif cc == self._cc_logo_stomp:
            self._logo_stomp = _midpoint_bool(value)
        elif cc == self._cc_tipping:
            self._tipping_point = value / 127.0
        elif cc == self._cc_duration:
            self._duration_seconds = (value / 127.0) * self._duration_max_seconds
        elif cc == self._cc_transition:
            self._transition_seconds = (value / 127.0) * self._transition_max_seconds

    def tick_interval_seconds(self) -> float:
        return 1.0 / self._update_hz

    def tick(self, now: float) -> None:
        if self._initial_send_pending:
            self._send_if_changed(127, 127)
            self._initial_send_pending = False
            self._last_tick = now
            return

        interval = 1.0 / self._update_hz
        if (now - self._last_tick) < interval:
            return
        dt = now - self._last_tick
        self._last_tick = now

        target_video, target_logo = self._compute_targets(now)
        self._target_video = target_video
        self._target_logo = target_logo

        # Smooth toward target. transition_seconds = time to reach 99% of target.
        if self._transition_seconds > 0.001:
            alpha = min(1.0, dt / self._transition_seconds)
        else:
            alpha = 1.0
        self._current_video += (target_video - self._current_video) * alpha
        self._current_logo += (target_logo - self._current_logo) * alpha

        video_int = max(0, min(127, int(round(self._current_video * 127))))
        logo_int = max(0, min(127, int(round(self._current_logo * 127))))
        self._send_if_changed(video_int, logo_int)

    def _compute_targets(self, now: float) -> tuple[float, float]:
        if not self._enabled:
            return 1.0, 1.0
        if self._video_stomp and self._logo_stomp:
            return 0.0, 0.0
        if self._video_stomp:
            return 1.0, 0.0
        if self._logo_stomp:
            return 0.0, 1.0
        if not self._audio_buffer:
            return self._target_video, self._target_logo
        avg = sum(self._audio_buffer) / len(self._audio_buffer)
        if avg > self._tipping_point:
            self._below_since = None
            return 1.0, 0.0
        if self._below_since is None:
            self._below_since = now
        if (now - self._below_since) >= self._duration_seconds:
            return 0.0, 1.0
        return self._target_video, self._target_logo

    def _send_if_changed(self, video_int: int, logo_int: int) -> None:
        if self._last_video_sent != video_int:
            self._send_master(self._cc_video_master, self._osc_video_path, video_int, self._current_video)
            self._last_video_sent = video_int
        if self._last_logo_sent != logo_int:
            self._send_master(self._cc_logo_master, self._osc_logo_path, logo_int, self._current_logo)
            self._last_logo_sent = logo_int

    def _send_master(self, cc: int, osc_path: str, int_value: int, float_value: float) -> None:
        if self._output_protocol == "osc" and self._osc is not None:
            self._osc.send(osc_path, max(0.0, min(1.0, float(float_value))))
        else:
            self._midi_out.control_change(self._output_channel, cc, int_value)

    def shutdown(self) -> None:
        if self._osc is not None:
            self._osc.close()
            self._osc = None

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "enabled": self._enabled,
            "video_stomp": self._video_stomp,
            "logo_stomp": self._logo_stomp,
            "tipping_point": round(self._tipping_point, 3),
            "duration_seconds": round(self._duration_seconds, 3),
            "transition_seconds": round(self._transition_seconds, 3),
            "audio_window_avg": (
                round(sum(self._audio_buffer) / len(self._audio_buffer), 3)
                if self._audio_buffer
                else 0.0
            ),
            "target_video_master": round(self._target_video, 3),
            "target_logo_master": round(self._target_logo, 3),
            "current_video_master": round(self._current_video, 3),
            "current_logo_master": round(self._current_logo, 3),
        }
