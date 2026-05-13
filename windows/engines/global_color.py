"""Global color engine — MIDI-only.

Consumes:
- MIDI ch15 CCs 40-45: channel index updates from the COLOR PALETTE Wire
  patch (CHASER, VIDEO_HL, VIDEO_SH, LOGO_HL, LOGO_SH, GLOBAL). Raw value
  0..9 (Write CC normalize=false at source) is the new palette index.
  CC range chosen to avoid the V-C-B Wire patch's pre-slim emissions on
  ch15 50-59.
- MIDI ch15 CC 46: fade time. Normalized 0..127 maps to 0..max_fade_seconds
  (default 5.0s). Applies to subsequent channel index changes AND palette
  slot tweaks: each consumer's color is interpolated from current to new
  over the fade duration at ~30Hz. Value <= 0 snaps.
- MIDI ch14 CCs 0-29: palette slot R/G/B updates. 3 CCs per slot, with
  normalize=true at source so CC value 0..127 represents 0..1 float per
  component. Alpha is fixed to #ff.

Emits:
- OSC: hex_rgba_string to each consumer in the active channel's config.
- MIDI ch15 CC 99: dashboard Resync trigger on the COLOR PALETTE comp-level
  effect (MIDI Learned to the Resync Trigger In). Fired once from
  `bind_registry` so the engine boots with the patch's current state, and
  again from `refresh()`. The Wire patch's MIDI In node does NOT receive
  external MIDI when embedded in Arena, so the resync path goes through
  Arena's MIDI Learn shortcut rather than a Filter CC.

Channels:
- chaser, video_highlight, video_shadow, logo_highlight, logo_shadow: each
  tracks an active palette index. On its CC, the engine writes
  palette[new_index] to every consumer in that channel's config.
- global: stateless macro on CC 45. Fans current palette[new_index] to all
  5 sub-channels' consumers, then discards. No persistent global state,
  no sub-channel active-index updates.

Spec: specs/global-color-engine.md
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

DEFAULT_INPUT_CHANNEL = 14  # MIDI ch15 (1-indexed); Python channel index 14.
DEFAULT_PALETTE_CHANNEL = 13  # MIDI ch14 (1-indexed); Python channel index 13.
DEFAULT_CC_BASE = 40  # CCs 40-45 for the 6 channel selectors (ch15-relative).
DEFAULT_PALETTE_CC_BASE = 0  # CCs 0..29 for 10 slots * 3 RGB components.
DEFAULT_RESYNC_CC = 99  # MIDI Learn target for the dashboard Resync trigger.
DEFAULT_FADE_CC = 46  # Fade time CC, ch15. Normalized 0..127 -> 0..max_fade_seconds.
DEFAULT_FADE_SECONDS = 1.0  # Seeded so first writes look right pre-resync.
DEFAULT_MAX_FADE_SECONDS = 5.0  # Wire dashboard caps Fade Time at 5s.
TICK_INTERVAL_SECONDS = 1.0 / 30.0  # 30Hz interpolation rate.

PALETTE_SIZE = 10

# Channel name -> ch15-relative CC. First 6 entries match the original CHANNELS
# group on the COLOR PALETTE Wire patch (CHASER..GLOBAL at CC 40..45). The 6
# replace-white / replace-black channels (added 2026-05-12) bind to VIDDY-COLOR
# ISF V2's REPLACE WHITE / REPLACE BLACK color inputs and use hand-picked CCs:
# 47-49 for whites (avoid V-C-B flooding of 50-59), 92-94 for blacks (after the
# OSC Sync CC 90, StageFlow rescan CC 91, before the GLOBAL Resync CC 99).
CHANNEL_CC: dict[str, int] = {
    "chaser": 40,
    "video_highlight": 41,
    "video_shadow": 42,
    "logo_highlight": 43,
    "logo_shadow": 44,
    "global": 45,
    "video_white": 47,
    "logo_white": 48,
    "chaser_white": 49,
    "video_black": 92,
    "logo_black": 93,
    "chaser_black": 94,
}
CHANNEL_ORDER = tuple(CHANNEL_CC.keys())
GLOBAL_CHANNEL = "global"
# ALL COLORS (GLOBAL fan-out) drives normal channels + replace-white channels
# but NOT replace-black channels — by design, replace-black is set by hand and
# usually left alone show-over-show.
GLOBAL_EXCLUDES: frozenset[str] = frozenset(
    {"video_black", "logo_black", "chaser_black"}
)

DEFAULT_PALETTE_HEXES = (
    "#ff0000ff",  # red
    "#ff5b00ff",  # orange
    "#ffff00ff",  # yellow
    "#00ff00ff",  # green
    "#00ffffff",  # cyan
    "#0000ffff",  # blue
    "#7f00ffff",  # purple
    "#ff00ffff",  # magenta
    "#ffffffff",  # white
    "#000000ff",  # black
)


@dataclass
class ConsumerSpec:
    name: str
    osc_path: str
    format: str = "hex_rgba_string"


@dataclass
class Channel:
    name: str
    cc: int
    consumers: list[ConsumerSpec] = field(default_factory=list)
    active_index: int = 0  # ignored for the 'global' channel (stateless macro).


@dataclass
class FadeState:
    from_hex: str
    to_hex: str
    t_start: float
    duration: float


def _hex_from_cc(r_cc: int, g_cc: int, b_cc: int) -> str:
    """Build `#rrggbbff` from three MIDI CC bytes (0..127 -> 0..255)."""
    r = round(max(0, min(127, r_cc)) * 255 / 127)
    g = round(max(0, min(127, g_cc)) * 255 / 127)
    b = round(max(0, min(127, b_cc)) * 255 / 127)
    return "#{:02x}{:02x}{:02x}ff".format(r, g, b)


def _cc_from_hex(hex_str: str) -> tuple[int, int, int]:
    """Extract R/G/B as 0..127 from `#rrggbb[aa]` for default seeding."""
    h = hex_str.lstrip("#")
    if len(h) < 6:
        return (0, 0, 0)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (round(r * 127 / 255), round(g * 127 / 255), round(b * 127 / 255))


def _lerp_hex(from_hex: str, to_hex: str, t: float) -> str:
    """Linear-interpolate two `#rrggbbaa` strings. t clamped to [0,1]."""
    t = max(0.0, min(1.0, t))
    fh = from_hex.lstrip("#")
    th = to_hex.lstrip("#")
    if len(fh) == 6:
        fh += "ff"
    if len(th) == 6:
        th += "ff"
    out = []
    for i in (0, 2, 4, 6):
        f = int(fh[i:i + 2], 16)
        v = int(th[i:i + 2], 16)
        out.append(round(f + (v - f) * t))
    return "#{:02x}{:02x}{:02x}{:02x}".format(*out)


class GlobalColorEngine(Engine):
    type_name = "global_color"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        osc_client: OscClient | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        self._channel_input_channel = int(
            config.get("channel", DEFAULT_INPUT_CHANNEL)
        )
        self._palette_input_channel = int(
            config.get("palette_channel", DEFAULT_PALETTE_CHANNEL)
        )
        self._cc_base = int(config.get("cc_base", DEFAULT_CC_BASE))
        self._palette_cc_base = int(
            config.get("palette_cc_base", DEFAULT_PALETTE_CC_BASE)
        )
        self._resync_cc = int(config.get("resync_cc", DEFAULT_RESYNC_CC))
        self._fade_cc = int(config.get("fade_cc", DEFAULT_FADE_CC))
        self._max_fade_seconds = float(
            config.get("max_fade_seconds", DEFAULT_MAX_FADE_SECONDS)
        )
        self._fade_seconds = float(
            config.get("default_fade_seconds", DEFAULT_FADE_SECONDS)
        )

        outputs = config.get("outputs", {})
        osc_cfg = outputs.get("osc", {})
        self._osc = osc_client or OscClient(
            host=str(osc_cfg.get("host", "127.0.0.1")),
            port=int(osc_cfg.get("port", 7000)),
        )

        palette_defaults = tuple(
            str(h) for h in config.get("palette_defaults", DEFAULT_PALETTE_HEXES)
        )
        if len(palette_defaults) != PALETTE_SIZE:
            raise ValueError(
                f"global_color: palette_defaults must have {PALETTE_SIZE} entries"
            )
        self._palette: list[str] = list(palette_defaults)
        self._palette_raw: list[list[int]] = [
            list(_cc_from_hex(h)) for h in self._palette
        ]

        channels_cfg = config.get("channels", {})
        self._channels: dict[str, Channel] = {}
        for name in CHANNEL_ORDER:
            cc = CHANNEL_CC[name]
            consumers: list[ConsumerSpec] = []
            for raw in channels_cfg.get(name, []) or ():
                if not isinstance(raw, dict):
                    continue
                consumers.append(
                    ConsumerSpec(
                        name=str(
                            raw.get("name", raw.get("osc_path", "consumer"))
                        ),
                        osc_path=str(raw["osc_path"]),
                        format=str(raw.get("format", "hex_rgba_string")),
                    )
                )
            self._channels[name] = Channel(name=name, cc=cc, consumers=consumers)

        self._channel_cc_to_channel = {
            ch.cc: ch.name for ch in self._channels.values()
        }

        self._channel_cc_count = 0
        self._palette_cc_count = 0
        self._consumer_write_count = 0
        self._resync_emit_count = 0
        self._fade_cc_count = 0

        self._consumer_state: dict[str, str] = {}
        self._fades: dict[str, FadeState] = {}

    # ------------------------------------------------------------------
    # Lifecycle

    def bind_registry(self, registry) -> None:
        self._emit_resync()

    def shutdown(self) -> None:
        try:
            self._osc.close()
        except Exception:
            pass

    def refresh(self) -> None:
        self._emit_resync()

    def _emit_resync(self) -> None:
        try:
            self._midi_out.control_change(
                self._channel_input_channel, self._resync_cc, 127
            )
            self._resync_emit_count += 1
        except Exception as exc:
            LOGGER.warning(
                "%s: failed to emit resync CC %d on channel index %d: %s",
                self.name,
                self._resync_cc,
                self._channel_input_channel,
                exc,
            )

    # ------------------------------------------------------------------
    # MIDI input

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel == self._channel_input_channel:
            if cc == self._fade_cc:
                self._handle_fade_cc(value)
            else:
                self._handle_channel_cc(cc, value, now)
        elif channel == self._palette_input_channel:
            self._handle_palette_cc(cc, value, now)

    def _handle_fade_cc(self, value: int) -> None:
        clamped = max(0, min(127, int(value)))
        self._fade_seconds = (clamped / 127.0) * self._max_fade_seconds
        self._fade_cc_count += 1

    def _handle_channel_cc(self, cc: int, value: int, now: float) -> None:
        target = self._channel_cc_to_channel.get(cc)
        if target is None:
            return
        self._channel_cc_count += 1
        new_index = max(0, min(PALETTE_SIZE - 1, int(value)))
        hex_value = self._palette[new_index]

        if target == GLOBAL_CHANNEL:
            for name, ch in self._channels.items():
                if name == GLOBAL_CHANNEL or name in GLOBAL_EXCLUDES:
                    continue
                self._write_consumers(ch.consumers, hex_value, now)
            return

        ch = self._channels[target]
        ch.active_index = new_index
        self._write_consumers(ch.consumers, hex_value, now)

    def _handle_palette_cc(self, cc: int, value: int, now: float) -> None:
        rel = cc - self._palette_cc_base
        if rel < 0 or rel >= PALETTE_SIZE * 3:
            return
        slot = rel // 3
        component = rel % 3
        clamped = max(0, min(127, int(value)))
        if self._palette_raw[slot][component] == clamped:
            return
        self._palette_raw[slot][component] = clamped

        new_hex = _hex_from_cc(
            self._palette_raw[slot][0],
            self._palette_raw[slot][1],
            self._palette_raw[slot][2],
        )
        if new_hex == self._palette[slot]:
            return
        self._palette[slot] = new_hex
        self._palette_cc_count += 1

        for ch_name, ch in self._channels.items():
            if ch_name == GLOBAL_CHANNEL:
                continue
            if ch.active_index != slot:
                continue
            self._write_consumers(ch.consumers, new_hex, now)

    # ------------------------------------------------------------------
    # Consumer write

    def _write_consumers(
        self, consumers: list[ConsumerSpec], hex_value: str, now: float
    ) -> None:
        for consumer in consumers:
            self._write_consumer(consumer, hex_value, now)

    def _write_consumer(
        self, consumer: ConsumerSpec, hex_value: str, now: float
    ) -> None:
        if consumer.format != "hex_rgba_string":
            LOGGER.warning(
                "%s: consumer %r has unknown format %r; skipping",
                self.name,
                consumer.name,
                consumer.format,
            )
            return

        path = consumer.osc_path
        existing = self._consumer_state.get(path)
        if (
            self._fade_seconds <= 0
            or existing is None
            or existing == hex_value
        ):
            self._fades.pop(path, None)
            self._send_color(path, hex_value)
            return

        active = self._fades.get(path)
        from_hex = (
            _lerp_hex(active.from_hex, active.to_hex, (now - active.t_start) / active.duration)
            if active and active.duration > 0
            else existing
        )
        self._fades[path] = FadeState(
            from_hex=from_hex,
            to_hex=hex_value,
            t_start=now,
            duration=self._fade_seconds,
        )

    def _send_color(self, path: str, hex_value: str) -> None:
        self._osc.send_color(path, hex_value)
        self._consumer_state[path] = hex_value
        self._consumer_write_count += 1

    # ------------------------------------------------------------------
    # Tick (fade interpolation)

    def tick_interval_seconds(self) -> float | None:
        return TICK_INTERVAL_SECONDS

    def tick(self, now: float) -> None:
        if not self._fades:
            return
        for path in list(self._fades.keys()):
            fade = self._fades[path]
            if fade.duration <= 0:
                self._send_color(path, fade.to_hex)
                del self._fades[path]
                continue
            progress = (now - fade.t_start) / fade.duration
            if progress >= 1.0:
                self._send_color(path, fade.to_hex)
                del self._fades[path]
            else:
                self._send_color(path, _lerp_hex(fade.from_hex, fade.to_hex, progress))

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "palette": list(self._palette),
            "channels": {
                ch.name: {
                    "cc": ch.cc,
                    "active_index": (
                        ch.active_index if ch.name != GLOBAL_CHANNEL else None
                    ),
                    "consumer_count": len(ch.consumers),
                }
                for ch in self._channels.values()
            },
            "channel_cc_count": self._channel_cc_count,
            "palette_cc_count": self._palette_cc_count,
            "consumer_write_count": self._consumer_write_count,
            "resync_emit_count": self._resync_emit_count,
            "fade_cc_count": self._fade_cc_count,
            "fade_seconds": self._fade_seconds,
            "max_fade_seconds": self._max_fade_seconds,
            "active_fades": len(self._fades),
            "channel_input_channel": self._channel_input_channel,
            "palette_input_channel": self._palette_input_channel,
            "palette_cc_base": self._palette_cc_base,
            "resync_cc": self._resync_cc,
            "fade_cc": self._fade_cc,
        }
