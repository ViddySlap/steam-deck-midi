"""StageFlow live-sync bridge engine.

Brings StageFlow look-name labels onto TouchOSC at runtime, without
requiring a .tosc rebuild + redeploy on every rename.

Architecture (from `wiki/design/stageflow-live-sync.md`):

1. Operator renames look in Resolume UI -> saves comp -> presses rescan.
2. This engine parses altNames out of the saved .avc XML.
3. For each (row, look_n), engine writes the altName to a String In
   dashboard input on the comp-level "STAGEFLOW BRIDGE" Wire patch via
   REST PUT /api/v1/parameter/by-id/<id>.
4. Wire patch broadcasts each String In's new value as OSC; TouchOSC
   subscribes and updates labels live.

Trigger inputs (all user-triggered or one-shot per the
"no REST after engine init unless user-triggered" rule):

- CC `cc_rescan` ch15 rising edge (default CC 91): operator-driven rescan.
- Initial-rescan one-shot: a `threading.Timer` fires `_initial_rescan_delay`
  seconds after `bind_registry`, so TouchOSC has labels even before the
  operator presses rescan. Single-shot only -- if the rescan misses
  (Wire patch not yet loaded into comp, etc.), the user must trigger
  another via CC 91, the webui, or the dev /api/engines/refresh endpoint.
- `refresh()`: dev endpoint hook -- re-runs a rescan on demand.

Failure modes are tolerated quietly: if the .avc isn't readable, if the
Wire patch hasn't been added to the comp yet, or if individual String
In param IDs can't be resolved, the engine logs and skips. Subsequent
user-triggered rescans pick up whatever has appeared in the meantime.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

from windows.engines._resolume_lookup import find_effect_node
from windows.engines.base import Engine
from windows.engines.resolume_rest import ResolumeRestClient, ResolumeRestError
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

DEFAULT_INPUT_CHANNEL = 14
DEFAULT_CC_RESCAN = 91
DEFAULT_WIRE_EFFECT_NAME = "STAGEFLOW BRIDGE"
DEFAULT_LOOK_COUNT = 6
DEFAULT_INITIAL_RESCAN_DELAY_SECONDS = 1.0

# Row keys map StageFlow instance container -> Wire dashboard row
# slug. The keys come from the .avc parser; values are the dashboard
# group slugs the Wire patch exposes.
DEFAULT_ROW_MAP: dict[tuple[str, int], str] = {
    ("group", 1): "groupvideo",
    ("layer", 1): "layer1",
    ("layer", 2): "layer2",
    ("layer", 3): "layer3",
    ("layer", 4): "layer4",
    ("layer", 6): "logo1",
    ("layer", 7): "logo2",
}


class StageFlowBridgeEngine(Engine):
    type_name = "stageflow_bridge"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        rest_client: ResolumeRestClient | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        inputs = config.get("inputs", {})
        self._input_channel = int(inputs.get("channel", DEFAULT_INPUT_CHANNEL))
        self._cc_rescan = int(inputs.get("cc_rescan", DEFAULT_CC_RESCAN))

        self._comp_path = Path(
            str(
                config.get(
                    "comp_path",
                    "C:/Users/Ben/OneDrive/Documents/Resolume Arena/Compositions/5-5-26 STEAMDECK V2.avc",
                )
            )
        )
        self._wire_effect_name = str(
            config.get("wire_effect_name", DEFAULT_WIRE_EFFECT_NAME)
        )
        self._look_count = int(config.get("look_count", DEFAULT_LOOK_COUNT))

        # Allow the row map to be overridden via config for shows that
        # use different layer numbers.
        row_map_raw = config.get("row_map")
        if row_map_raw:
            self._row_map = {
                (str(k[0]), int(k[1])): str(v)
                for k, v in (
                    (tuple(entry["key"]), entry["row"])
                    for entry in row_map_raw
                )
            }
        else:
            self._row_map = dict(DEFAULT_ROW_MAP)

        self._initial_rescan_delay = float(
            config.get(
                "initial_rescan_delay_seconds", DEFAULT_INITIAL_RESCAN_DELAY_SECONDS
            )
        )

        # Strip leading "<digit>-" prefix from altNames for compactness on
        # TouchOSC (so "1-FULL SCREEN" becomes "FULL SCREEN").
        self._strip_numeric_prefix = bool(
            config.get("strip_numeric_prefix", True)
        )

        rest_cfg = config.get("rest", {})
        self._rest = rest_client or ResolumeRestClient(
            base_url=str(rest_cfg.get("base_url", "http://127.0.0.1:8080")),
            timeout_seconds=float(rest_cfg.get("timeout_seconds", 1.5)),
        )

        # Edge detection on the rescan CC.
        self._last_cc_value = 0

        # Cached map of (row_slug, look_n) -> Wire String In param id.
        self._param_ids: dict[tuple[str, int], int] = {}

        # Initial-rescan one-shot timer (created in bind_registry).
        self._initial_rescan_timer: threading.Timer | None = None
        self._initial_rescan_done = False

        # Stats / status.
        self._last_rescan_at: float | None = None
        self._last_rescan_writes = 0
        self._last_rescan_skipped: list[str] = []
        self._last_rescan_error: str | None = None
        self._rescan_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

    def bind_registry(self, registry) -> None:
        # Schedule the one-shot initial rescan via threading.Timer so we
        # don't need a periodic tick. Per "no REST after engine init
        # unless user-triggered" -- this fires exactly once.
        delay = max(0.0, self._initial_rescan_delay)
        self._initial_rescan_timer = threading.Timer(
            delay, self._run_initial_rescan
        )
        self._initial_rescan_timer.daemon = True
        self._initial_rescan_timer.start()

    def _run_initial_rescan(self) -> None:
        if self._initial_rescan_done:
            return
        self._initial_rescan_done = True
        LOGGER.info(
            "%s: running initial rescan (%.1fs after engine init)",
            self.name,
            self._initial_rescan_delay,
        )
        self._do_rescan_safe()

    def refresh(self) -> None:
        """Re-rescan on demand. Called by /api/engines/refresh."""
        self._do_rescan_safe()

    def shutdown(self) -> None:
        timer = self._initial_rescan_timer
        if timer is not None:
            timer.cancel()

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel or cc != self._cc_rescan:
            return
        prev, self._last_cc_value = self._last_cc_value, value
        if value > 0 and prev == 0:
            LOGGER.info("%s: rescan triggered via CC %d", self.name, cc)
            self._do_rescan_safe()

    def trigger_rescan(self) -> bool:
        """Public entry point — used by the webui's mapping UI."""
        return self._do_rescan_safe()

    # ------------------------------------------------------------------
    # Rescan

    def _do_rescan_safe(self) -> bool:
        try:
            return self._do_rescan()
        except Exception as exc:  # noqa: BLE001 - never let rescan crash the engine
            self._last_rescan_error = f"unexpected error: {exc}"
            LOGGER.exception("%s: rescan failed", self.name)
            return False

    def _do_rescan(self) -> bool:
        self._last_rescan_at = self._clock()
        self._last_rescan_error = None
        self._last_rescan_writes = 0
        self._last_rescan_skipped = []
        self._rescan_count += 1

        # 1. Parse altNames out of the .avc.
        try:
            altnames = parse_stageflow_altnames(self._comp_path)
        except (OSError, IOError) as exc:
            self._last_rescan_error = f"comp file read failed: {exc}"
            LOGGER.warning("%s: %s", self.name, self._last_rescan_error)
            return False

        # 2. Discover Wire String In param IDs (cached after first call;
        #    re-discovered on next rescan if the cache is empty so the
        #    engine recovers if the patch is added after init).
        if not self._param_ids:
            self._discover_param_ids()
        if not self._param_ids:
            self._last_rescan_error = (
                f"could not find {self._wire_effect_name!r} effect in comp"
            )
            LOGGER.warning("%s: %s", self.name, self._last_rescan_error)
            return False

        # 3. PUT each altName to its corresponding String In.
        for key, looks in altnames.items():
            row_slug = self._row_map.get(key)
            if row_slug is None:
                continue
            for look_idx in range(1, self._look_count + 1):
                look_label = f"Look {look_idx}"
                altname = looks.get(look_label, "")
                display = self._format_label(altname, look_idx)
                pid = self._param_ids.get((row_slug, look_idx))
                if pid is None:
                    self._last_rescan_skipped.append(
                        f"{row_slug}/look{look_idx} (no param id)"
                    )
                    continue
                try:
                    self._rest.put_parameter(pid, display)
                    self._last_rescan_writes += 1
                except ResolumeRestError as exc:
                    self._last_rescan_skipped.append(
                        f"{row_slug}/look{look_idx} (PUT failed: {exc})"
                    )
        LOGGER.info(
            "%s: rescan wrote %d String Ins, skipped %d",
            self.name,
            self._last_rescan_writes,
            len(self._last_rescan_skipped),
        )
        return True

    def _format_label(self, altname: str, look_idx: int) -> str:
        if not altname:
            return f"LOOK {look_idx}"
        if self._strip_numeric_prefix:
            return re.sub(r"^\d+-", "", altname)
        return altname

    # ------------------------------------------------------------------
    # Param ID discovery

    def _discover_param_ids(self) -> None:
        """Walk Resolume's REST tree for the Wire patch's String In params.

        The Wire patch defines one dashboard group per row (groupvideo,
        layer1..layer4, logo1, logo2) with 6 String Ins each named like
        "<row_slug> LOOK <N> NAME" (or compact "look<N>name"). Resolume
        surfaces them under `effects[i].params` keyed by display name.
        We tolerate either form by matching against the slug.
        """
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            LOGGER.warning(
                "%s: comp fetch failed during param discovery: %s", self.name, exc
            )
            return
        eff = find_effect_node(comp, self._wire_effect_name)
        if not eff:
            return
        params = eff.get("params") or {}
        if not isinstance(params, dict):
            return
        # Match each param against the (row_slug, look_n) grid.
        # Param display name candidates:
        #   "<ROW> LOOK <N> NAME"      (legacy verbose)
        #   "look<N>name"              (compact slug form)
        # Slug form: the full key is just the row group + param. Resolume's
        # REST keeps the grouped names flat — we can't tell which group a
        # param lives in from its key alone unless the verbose prefix is
        # present. So we emit all 7×6 = 42 pattern keys and look for any
        # match.
        for row_slug in self._row_map.values():
            for look_idx in range(1, self._look_count + 1):
                pid = _find_string_in_param_id(params, row_slug, look_idx)
                if pid is not None:
                    self._param_ids[(row_slug, look_idx)] = pid
        LOGGER.info(
            "%s: discovered %d Wire String In param IDs (expected %d)",
            self.name,
            len(self._param_ids),
            len(self._row_map) * self._look_count,
        )

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "comp_path": str(self._comp_path),
            "wire_effect_name": self._wire_effect_name,
            "param_ids_known": len(self._param_ids),
            "last_rescan_at": self._last_rescan_at,
            "last_rescan_writes": self._last_rescan_writes,
            "last_rescan_skipped_count": len(self._last_rescan_skipped),
            "last_rescan_skipped": list(self._last_rescan_skipped[:5]),
            "last_rescan_error": self._last_rescan_error,
            "rescan_count": self._rescan_count,
            "initial_rescan_done": self._initial_rescan_done,
        }


# ---------------------------------------------------------------------------
# .avc parsing — exposed at module level so tests can drive it directly.

# Stageflow inner FFGLEffect block opener.
_SF_PATTERN = re.compile(
    r'<RenderPass[^>]*type="FFGLEffect"[^>]*uniqueTypeId="HV16"[^>]*>'
)
_LAYER_OPEN_PATTERN = re.compile(r"<Layer\b[^>]*>")
_LAYER_CLOSE_PATTERN = re.compile(r"</Layer>")
_GROUP_OPEN_PATTERN = re.compile(r"<Group\b[^>]*>")
_GROUP_CLOSE_PATTERN = re.compile(r"</Group>")
_LOOK_PARAM_PATTERN = re.compile(
    r'<ParamRange name="(Look \d+)"(?: altName="([^"]*)")?'
)
# Pattern for the FFGLEffect's outer FFGLPlugin marker. The inner
# RenderPass for a StageFlow always ends with `<FFGLPlugin .../>` (per
# the .avc structure documented in stageflow-altname-storage.md). We
# stop scanning once we see it — that bounds our chunk to one
# FFGLEffect block, ignoring sibling FFGLEffects further down.
_FFGL_PLUGIN_PATTERN = re.compile(r"<FFGLPlugin\b")
# Hard cap on how far past the StageFlow opener we'll scan for Look params.
# Each FFGLEffect's <Params> with all its nested Look ranges and their
# nested PhaseSourceTimeline params can run >5 KB in the live comp; this
# is defensive headroom.
_SF_BLOCK_BYTES = 32768


def parse_stageflow_altnames(
    comp_path: Path | str,
) -> dict[tuple[str, int], dict[str, str]]:
    """Parse altNames for every StageFlow instance in a comp .avc file.

    Returns a dict keyed by ('group', n) or ('layer', n) -> {look_label:
    altname}. Look labels missing from a particular instance are simply
    absent from the inner dict; callers should default to "LOOK <N>"
    when no altName is present.

    Raises OSError/IOError on unreadable files. Robust to partial XML
    (the comp .avc is sometimes truncated mid-write); unrecognised
    StageFlow blocks are simply skipped.
    """
    path = Path(comp_path)
    text = path.read_text(encoding="utf-8", errors="replace")

    layer_opens = list(_LAYER_OPEN_PATTERN.finditer(text))
    group_opens = list(_GROUP_OPEN_PATTERN.finditer(text))

    # Build a single sorted event stream so we can resolve container
    # context at any offset in O(N).
    events: list[tuple[int, str, int]] = []
    for i, m in enumerate(layer_opens):
        events.append((m.start(), "L_open", i))
    for m in _LAYER_CLOSE_PATTERN.finditer(text):
        events.append((m.start(), "L_close", -1))
    for i, m in enumerate(group_opens):
        events.append((m.start(), "G_open", i))
    for m in _GROUP_CLOSE_PATTERN.finditer(text):
        events.append((m.start(), "G_close", -1))
    events.sort()

    results: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)

    sf_matches = list(_SF_PATTERN.finditer(text))

    # For each StageFlow opener, find the immediate container by walking
    # the event stream up to its position.
    event_idx = 0
    layer_stack: list[int] = []  # 1-indexed layer numbers
    group_stack: list[int] = []
    for sf in sf_matches:
        # Advance event_idx to cover all events strictly before sf.start().
        while event_idx < len(events) and events[event_idx][0] < sf.start():
            ev_pos, kind, idx = events[event_idx]
            if kind == "L_open":
                layer_stack.append(idx + 1)
            elif kind == "L_close":
                if layer_stack:
                    layer_stack.pop()
            elif kind == "G_open":
                group_stack.append(idx + 1)
            elif kind == "G_close":
                if group_stack:
                    group_stack.pop()
            event_idx += 1

        # Immediate container = whichever opened latest (deepest).
        if layer_stack and group_stack:
            # Whichever container's open position is later wins.
            l_pos = layer_opens[layer_stack[-1] - 1].start()
            g_pos = group_opens[group_stack[-1] - 1].start()
            if l_pos > g_pos:
                key = ("layer", layer_stack[-1])
            else:
                key = ("group", group_stack[-1])
        elif layer_stack:
            key = ("layer", layer_stack[-1])
        elif group_stack:
            key = ("group", group_stack[-1])
        else:
            key = ("comp", 0)

        # Scan the next chunk for Look ParamRange entries. Cap the chunk
        # at the inner FFGLEffect's <FFGLPlugin/> sentinel so we don't
        # bleed into a sibling FFGLEffect's Look entries (which would
        # overwrite the current block's altNames with whatever comes next).
        # Looks are top-level ParamRange siblings of <FFGLPlugin/>, so this
        # bound encloses all of them.
        chunk_start = sf.start()
        hard_end = chunk_start + _SF_BLOCK_BYTES
        ffgl_match = _FFGL_PLUGIN_PATTERN.search(text, chunk_start, hard_end)
        chunk_end = ffgl_match.start() if ffgl_match else hard_end
        snippet = text[chunk_start:chunk_end]
        for look_label, altname in _LOOK_PARAM_PATTERN.findall(snippet):
            results[key][look_label] = altname or ""

    return dict(results)


def _find_string_in_param_id(
    params: dict, row_slug: str, look_idx: int
) -> int | None:
    """Find a Wire String In param id in the Wire patch's params dict.

    Match heuristics tolerate two naming styles:
      - "<ROW> LOOK <N> NAME" (verbose, e.g. "GROUP VIDEO LOOK 1 NAME")
      - "look<N>name" inside group "<row_slug>" (compact)

    Resolume's REST surfaces param keys flat so we can't see the group
    structure; instead we slug-match every key against either pattern.
    """
    target_verbose_slugs = {
        # Match the row_slug + "look" + N + "name" anywhere in the key
        # slug. The row_slug already lacks separators, so:
        #   "groupvideolook1name", "layer1look1name", etc.
        f"{row_slug}look{look_idx}name",
    }
    target_compact_slug = f"look{look_idx}name"

    for key, node in params.items():
        if not isinstance(node, dict) or "id" not in node:
            continue
        s = "".join(ch.lower() for ch in str(key) if ch.isalnum())
        if s in target_verbose_slugs:
            try:
                return int(node["id"])
            except (TypeError, ValueError):
                continue
        # Compact form: when the row_slug is part of the dashboard group
        # (not the param key), Resolume's flat representation drops it.
        # We can't confidently disambiguate compact look<N>name across
        # rows, so this branch is best-effort and only fires when there's
        # a single row's worth of compact entries (rare; when it happens
        # we accept the first match).
        if s == target_compact_slug:
            try:
                return int(node["id"])
            except (TypeError, ValueError):
                continue
    return None
