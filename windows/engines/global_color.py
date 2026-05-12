"""Global color engine (Pass 2, new).

6-channel color routing engine. Single 10-hex palette lives in a
comp-level Wire patch (`COLOR PALETTE`, created in Pass 3). Engine reads
the palette via REST GET on a 1Hz refresh tick + subscribes to CCs 50-55
on channel index 14 (MIDI ch15) from DECK_OUT, where the Wire patch
emits a CC whenever a CHANNELS Int In dashboard input changes.

Spec: specs/global-color-engine.md

Channels:
- chaser, video_highlight, video_shadow, logo_highlight, logo_shadow:
  each tracks an active palette index. On its CC, the engine writes
  palette[new_index] to every consumer in that channel's config.
- global: stateless macro. On CC 55, the engine writes palette[new_index]
  to all consumers of all 5 sub-channels in one pass, then forgets. No
  persistent global state, no sub-channel index updates.

v1 ships chaser channel consumers (Color Bump COLOR.Color + ShockWave
.Flash Color). Other 4 sub-channels declared with empty consumer lists,
ready to populate when video/logo colorize effects ship.

Palette refresh: every `palette_refresh_hz`, engine REST-GETs the
COLOR PALETTE comp-level effect's PALETTE group. For each slot that
changed since the last refresh, engine re-writes to any sub-channel
currently pointing at that slot (so live-tweaking a palette slot during
a show propagates to active consumers within ~1s).

Outputs are OSC only. REST is read-only and runs at low frequency.

Consumer format (v1):
- "hex_rgba_string": send hex string directly via OSC. Resolume accepts
  this for color params like Color Bump COLOR.Color. (Live test will
  verify; if Resolume needs 4-tuple RGBA floats instead, the engine can
  switch to "rgba_floats" without code changes in this engine.)

v2 hook (designed-in, not built): per-channel `hue_offsets` modifier
applied before consumer write -- empty dict in v1. Future addition takes
a gyro CC and writes per-channel offsets.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from windows.engines._resolume_lookup import find_effect_params, find_param_value
from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.engines.resolume_rest import ResolumeRestClient, ResolumeRestError
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

DEFAULT_INPUT_CHANNEL = 14  # MIDI ch15 (1-indexed); Python channel index 14.
DEFAULT_PALETTE_REFRESH_HZ = 1.0
DEFAULT_PALETTE_PATCH_SLUG = "colorpalette"
DEFAULT_PALETTE_INPUT_NAMES = (
    "red",
    "orange",
    "yellow",
    "green",
    "cyan",
    "blue",
    "purple",
    "magenta",
    "white",
    "black",
)
DEFAULT_PALETTE_DEFAULTS = (
    "#ff0000ff",
    "#ff5b00ff",
    "#ffff00ff",
    "#00ff00ff",
    "#00ffffff",
    "#0000ffff",
    "#7f00ffff",
    "#ff00ffff",
    "#ffffffff",
    "#000000ff",
)
PALETTE_SIZE = 10

# Channel order matches the COLOR PALETTE Wire patch's CHANNELS group.
# CC offsets are added to CHANNELS_CC_BASE (default 50) to yield the
# per-channel CC numbers (50, 51, 52, 53, 54, 55).
CHANNEL_ORDER = (
    "chaser",
    "video_highlight",
    "video_shadow",
    "logo_highlight",
    "logo_shadow",
    "global",
)
DEFAULT_CC_BASE = 50

GLOBAL_CHANNEL = "global"


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
    active_index: int = 0  # ignored for the 'global' channel (stateless macro)


class GlobalColorEngine(Engine):
    type_name = "global_color"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        rest_client: ResolumeRestClient | None = None,
        osc_client: OscClient | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        self._input_channel = int(config.get("channel", DEFAULT_INPUT_CHANNEL))
        self._cc_base = int(config.get("cc_base", DEFAULT_CC_BASE))
        self._palette_refresh_hz = float(
            config.get("palette_refresh_hz", DEFAULT_PALETTE_REFRESH_HZ)
        )
        self._palette_patch_slug = str(
            config.get("palette_patch_slug", DEFAULT_PALETTE_PATCH_SLUG)
        )
        self._palette_input_names = tuple(
            str(n) for n in config.get(
                "palette_input_names", DEFAULT_PALETTE_INPUT_NAMES
            )
        )
        if len(self._palette_input_names) != PALETTE_SIZE:
            raise ValueError(
                f"global_color: palette_input_names must have {PALETTE_SIZE} entries"
            )
        palette_defaults = tuple(
            str(h) for h in config.get(
                "palette_defaults", DEFAULT_PALETTE_DEFAULTS
            )
        )
        if len(palette_defaults) != PALETTE_SIZE:
            raise ValueError(
                f"global_color: palette_defaults must have {PALETTE_SIZE} entries"
            )
        self._palette: list[str] = list(palette_defaults)

        outputs = config.get("outputs", {})
        osc_cfg = outputs.get("osc", {})
        self._osc = osc_client or OscClient(
            host=str(osc_cfg.get("host", "127.0.0.1")),
            port=int(osc_cfg.get("port", 7000)),
        )

        rest_cfg = config.get("rest", {})
        self._rest = rest_client or ResolumeRestClient(
            base_url=str(rest_cfg.get("base_url", "http://127.0.0.1:8080")),
            timeout_seconds=float(rest_cfg.get("timeout_seconds", 1.5)),
        )

        # Parse channels config. Each entry maps channel_name -> list of
        # consumer dicts. The 'global' channel is always present and is
        # always stateless (no consumers of its own; fans to sub-channels).
        channels_cfg = config.get("channels", {})
        self._channels: dict[str, Channel] = {}
        for idx, name in enumerate(CHANNEL_ORDER):
            cc = self._cc_base + idx
            consumers: list[ConsumerSpec] = []
            for raw in channels_cfg.get(name, []) or ():
                if not isinstance(raw, dict):
                    continue
                consumers.append(
                    ConsumerSpec(
                        name=str(raw.get("name", raw.get("osc_path", "consumer"))),
                        osc_path=str(raw["osc_path"]),
                        format=str(raw.get("format", "hex_rgba_string")),
                    )
                )
            self._channels[name] = Channel(name=name, cc=cc, consumers=consumers)

        # CC -> channel name lookup for fast dispatch.
        self._cc_to_channel = {ch.cc: ch.name for ch in self._channels.values()}

        # Tick state.
        self._last_palette_refresh: float | None = None
        self._cc_event_count = 0
        self._palette_refresh_count = 0
        self._consumer_write_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

    def bind_registry(self, registry) -> None:
        # Pull palette from Resolume once at init. Failures (Resolume not
        # running yet) are harmless -- defaults stay in place and the
        # tick handler will retry.
        self._refresh_palette()

    def shutdown(self) -> None:
        try:
            self._osc.close()
        except Exception:
            pass

    def tick_interval_seconds(self) -> float | None:
        if self._palette_refresh_hz <= 0:
            return None
        return 1.0 / self._palette_refresh_hz

    def tick(self, now: float) -> None:
        if self._palette_refresh_hz <= 0:
            return
        interval = 1.0 / self._palette_refresh_hz
        if (
            self._last_palette_refresh is not None
            and (now - self._last_palette_refresh) < interval
        ):
            return
        self._last_palette_refresh = now
        self._refresh_palette()

    # ------------------------------------------------------------------
    # MIDI input

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel:
            return
        target = self._cc_to_channel.get(cc)
        if target is None:
            return
        self._cc_event_count += 1
        new_index = self._cc_to_index(value)
        hex_value = self._palette[new_index]

        if target == GLOBAL_CHANNEL:
            # Stateless macro: fan out to all sub-channel consumers, then
            # discard. Sub-channel active indices are NOT updated.
            for name, ch in self._channels.items():
                if name == GLOBAL_CHANNEL:
                    continue
                self._write_consumers(ch.consumers, hex_value)
            return

        ch = self._channels[target]
        ch.active_index = new_index
        self._write_consumers(ch.consumers, hex_value)

    @staticmethod
    def _cc_to_index(value: int) -> int:
        """Map a 7-bit MIDI value to a palette index 0..9 (inclusive)."""
        v = max(0, min(127, int(value)))
        return int(round(v / 127.0 * (PALETTE_SIZE - 1)))

    # ------------------------------------------------------------------
    # Palette refresh

    def _refresh_palette(self) -> None:
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            LOGGER.debug(
                "%s: palette refresh skipped (REST unreachable: %s)",
                self.name,
                exc,
            )
            return
        params = find_effect_params(comp, self._palette_patch_slug)
        if not params:
            LOGGER.debug(
                "%s: COLOR PALETTE effect %r not found in comp",
                self.name,
                self._palette_patch_slug,
            )
            return
        self._palette_refresh_count += 1

        for slot_idx, input_name in enumerate(self._palette_input_names):
            new_hex = self._read_palette_slot(params, input_name)
            if new_hex is None or new_hex == self._palette[slot_idx]:
                continue
            self._palette[slot_idx] = new_hex
            # Re-write any sub-channels currently pointing at this slot.
            for ch_name, ch in self._channels.items():
                if ch_name == GLOBAL_CHANNEL:
                    continue
                if ch.active_index != slot_idx:
                    continue
                self._write_consumers(ch.consumers, new_hex)

    @staticmethod
    def _read_palette_slot(params: dict, input_name: str) -> str | None:
        value = find_param_value(params, (input_name, input_name.lower()))
        if value is None:
            return None
        if isinstance(value, str):
            return value
        # Resolume Color In may also expose rgba float tuples; convert.
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            try:
                r, g, b = (max(0.0, min(1.0, float(c))) for c in value[:3])
                a = float(value[3]) if len(value) >= 4 else 1.0
                a = max(0.0, min(1.0, a))
                return "#{:02x}{:02x}{:02x}{:02x}".format(
                    int(round(r * 255)),
                    int(round(g * 255)),
                    int(round(b * 255)),
                    int(round(a * 255)),
                )
            except (TypeError, ValueError):
                return None
        return None

    # ------------------------------------------------------------------
    # Consumer write

    def _write_consumers(
        self, consumers: list[ConsumerSpec], hex_value: str
    ) -> None:
        for consumer in consumers:
            self._write_consumer(consumer, hex_value)

    def _write_consumer(self, consumer: ConsumerSpec, hex_value: str) -> None:
        if consumer.format == "hex_rgba_string":
            # Resolume requires OSC type 'r' (32-bit packed RGBA) for
            # ParamColor inputs. String hex + 4-float fail silently on the
            # Arena OSC handler (verified 2026-05-11). osc_client.send_color
            # handles the encoding.
            self._osc.send_color(consumer.osc_path, hex_value)
        elif consumer.format == "rgba_floats":
            # Reserved for future use (e.g. ParamRange r/g/b separate inputs).
            LOGGER.warning(
                "%s: consumer %r format %r not supported by OscClient; skipping",
                self.name,
                consumer.name,
                consumer.format,
            )
            return
        else:
            LOGGER.warning(
                "%s: consumer %r has unknown format %r; skipping",
                self.name,
                consumer.name,
                consumer.format,
            )
            return
        self._consumer_write_count += 1

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
            "cc_event_count": self._cc_event_count,
            "palette_refresh_count": self._palette_refresh_count,
            "consumer_write_count": self._consumer_write_count,
            "input_channel": self._input_channel,
        }
