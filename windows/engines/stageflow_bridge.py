"""StageFlow live-sync bridge engine.

Brings StageFlow look-name labels onto TouchOSC at runtime, without
requiring a .tosc rebuild + redeploy on every rename.

Architecture (as of 2026-05-12 LATE NIGHT pivot):

1. Operator renames a look in Resolume UI.
2. Operator presses the TouchOSC "sync engine button" (CC 90 ch15) OR the
   STAGEFLOW BRIDGE Wire patch's RESCAN button (CC 91 ch15).
3. Engine wakes Resolume's StageFlow on a canonical layer (default Layer 1):
   connects clip 1 if no clip is connected, then cycles bypass true -> false.
   This forces Resolume to materialise the Look-N params in the REST tree
   (cold-boot StageFlow instances show "EFFECT INACTIVE / TRIGGER CLIP TO
   ENABLE" and expose zero Look params via REST until they've been activated).
4. Engine reads the canonical layer's StageFlow `Look N` params and pulls
   `view.alternative_name` for each.
5. Engine fans the same 6 names out to every String In dashboard input it
   discovered on the comp-level STAGEFLOW BRIDGE Wire patch (REST PUT). The
   Wire patch broadcasts each String In's new value as OSC; TouchOSC labels
   update live.
6. Engine restores the bypass + clip state it perturbed during wake-up.

REST discipline: this engine ONLY touches REST when CC 90/91 fires
(user-triggered). No periodic polling. No initial-rescan timer.

Resolume Arena 7.26.0 caps StageFlow plugin REST exposure at Look 1-4
even when the plugin slot count is higher. Slots 5 and 6 in the 6-slot
Wire patch surface get the fallback string "-".
"""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Callable

from windows.engines._resolume_lookup import (
    find_effect_node,
    find_layer_effect_node,
)
from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.engines.resolume_rest import ResolumeRestClient, ResolumeRestError
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

DEFAULT_INPUT_CHANNEL = 14
DEFAULT_CC_RESCAN = 91
DEFAULT_CC_SYNC = 90
DEFAULT_WIRE_EFFECT_NAME = "STAGEFLOW BRIDGE"
DEFAULT_LOOK_COUNT = 6
DEFAULT_LAYER_INDEX = 1
DEFAULT_STEP_DELAY_MS = 120
DEFAULT_PRE_WAKE_DELAY_MS = 50
DEFAULT_FALLBACK_LABEL = "-"


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
        osc_client: OscClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        inputs = config.get("inputs", {})
        self._input_channel = int(inputs.get("channel", DEFAULT_INPUT_CHANNEL))
        self._cc_rescan = int(inputs.get("cc_rescan", DEFAULT_CC_RESCAN))
        self._cc_sync = int(inputs.get("cc_sync", DEFAULT_CC_SYNC))

        self._wire_effect_name = str(
            config.get("wire_effect_name", DEFAULT_WIRE_EFFECT_NAME)
        )
        self._look_count = int(config.get("look_count", DEFAULT_LOOK_COUNT))
        self._layer_index = int(config.get("layer_index", DEFAULT_LAYER_INDEX))

        # Tunables for wake-up timing.
        self._step_delay = (
            float(config.get("wake_up_step_delay_ms", DEFAULT_STEP_DELAY_MS)) / 1000.0
        )
        # Small pause before the wake-up cycle so osc_sync's master-drop
        # has time to mask any flicker. osc_sync also fires on CC 90.
        self._pre_wake_delay = (
            float(config.get("pre_wake_delay_ms", DEFAULT_PRE_WAKE_DELAY_MS)) / 1000.0
        )

        # Strip leading "<digit>-" prefix for label compactness.
        self._strip_numeric_prefix = bool(
            config.get("strip_numeric_prefix", True)
        )

        # Fallback when a look slot has no altName (or is past the
        # plugin's REST-exposed slot count).
        self._fallback_label = str(
            config.get("fallback_label", DEFAULT_FALLBACK_LABEL)
        )

        rest_cfg = config.get("rest", {})
        self._rest = rest_client or ResolumeRestClient(
            base_url=str(rest_cfg.get("base_url", "http://127.0.0.1:8080")),
            timeout_seconds=float(rest_cfg.get("timeout_seconds", 1.5)),
        )

        osc_cfg = config.get("osc", {})
        self._osc = osc_client or OscClient(
            host=str(osc_cfg.get("host", "127.0.0.1")),
            port=int(osc_cfg.get("port", 7000)),
        )

        self._sleep = sleep

        # Edge detection for both rescan inputs.
        self._last_cc_value: dict[int, int] = {self._cc_rescan: 0, self._cc_sync: 0}

        # Cached map of (row_slug, look_n) -> Wire String In param id.
        # row_slug is whatever Wire dashboard group the String In lives
        # under. After the Phase-2 Wire-patch collapse it will be a single
        # row (e.g. "looks"); pre-collapse it's still 7 rows.
        self._param_ids: dict[tuple[str, int], int] = {}

        # Serialise rescan work onto a single worker thread. Multiple
        # rapid CC presses collapse to at most one in-flight rescan.
        self._worker_lock = threading.Lock()
        self._rescan_thread: threading.Thread | None = None

        # Legacy field, retained for the deprecated .avc path. The .avc
        # parser is still exported as `parse_stageflow_altnames` for
        # tests that exercise the standalone function, but the engine
        # itself no longer reads .avc on rescan.
        self._comp_path = Path(
            str(
                config.get(
                    "comp_path",
                    "C:/Users/Ben/OneDrive/Documents/Resolume Arena/"
                    "Compositions/5-5-26 STEAMDECK V2.avc",
                )
            )
        )

        # Stats / status.
        self._last_rescan_at: float | None = None
        self._last_rescan_writes = 0
        self._last_rescan_skipped: list[str] = []
        self._last_rescan_error: str | None = None
        self._last_look_names: list[str] = []
        self._rescan_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

    def bind_registry(self, registry) -> None:
        # No initial-rescan timer. The engine stays idle until the
        # operator fires CC 90 (sync engine button) or CC 91 (Wire
        # RESCAN button). Per the "no REST after engine init unless
        # user-triggered" rule.
        pass

    def refresh(self) -> None:
        """Re-rescan on demand. Called by POST /api/engines/refresh."""
        self._spawn_rescan(trigger="refresh")

    def shutdown(self) -> None:
        # Best-effort: let any in-flight rescan finish naturally. We
        # don't have a cancellation signal, but rescans complete in
        # well under a second.
        pass

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel:
            return
        if cc not in (self._cc_rescan, self._cc_sync):
            return
        prev = self._last_cc_value.get(cc, 0)
        self._last_cc_value[cc] = value
        if value > 0 and prev == 0:
            trigger = "cc_rescan" if cc == self._cc_rescan else "cc_sync"
            LOGGER.info("%s: rescan triggered (%s, CC %d)", self.name, trigger, cc)
            self._spawn_rescan(trigger=trigger)

    def trigger_rescan(self) -> bool:
        """Public entry point — used by the webui mapping UI and tests.

        Runs synchronously so callers can assert on the result. For
        MIDI-driven triggers we spawn a worker thread to avoid blocking
        the receive loop on REST round-trips + sleeps.
        """
        return self._do_rescan_safe()

    # ------------------------------------------------------------------
    # Threading

    def _spawn_rescan(self, *, trigger: str) -> None:
        # If a rescan is already running, drop this trigger. The user
        # can press again after the current pass finishes.
        if self._worker_lock.locked():
            LOGGER.info(
                "%s: rescan already in flight (trigger=%s ignored)",
                self.name,
                trigger,
            )
            return
        t = threading.Thread(
            target=self._worker_rescan,
            name=f"{self.name}-rescan",
            daemon=True,
        )
        self._rescan_thread = t
        t.start()

    def _worker_rescan(self) -> None:
        with self._worker_lock:
            self._do_rescan_safe()

    # ------------------------------------------------------------------
    # Rescan

    def _do_rescan_safe(self) -> bool:
        try:
            return self._do_rescan()
        except Exception as exc:  # noqa: BLE001
            self._last_rescan_error = f"unexpected error: {exc}"
            LOGGER.exception("%s: rescan failed", self.name)
            return False

    def _do_rescan(self) -> bool:
        self._last_rescan_at = self._clock()
        self._last_rescan_error = None
        self._last_rescan_writes = 0
        self._last_rescan_skipped = []
        self._rescan_count += 1

        # Pause briefly so any concurrent osc_sync master-drop lands first.
        if self._pre_wake_delay > 0:
            self._sleep(self._pre_wake_delay)

        # 1. Wake-up + read.
        look_names = self._wake_and_read()
        if look_names is None:
            return False
        # Pad / truncate to look_count slots so writes always cover the
        # full Wire patch surface deterministically.
        padded = list(look_names) + [self._fallback_label] * self._look_count
        padded = padded[: self._look_count]
        self._last_look_names = padded

        # 2. Discover String In param IDs. Re-walk every rescan so the
        #    cache can't go stale across Resolume comp reloads, which
        #    regenerate every param ID. One extra REST GET is cheap
        #    compared to a silently broken sync.
        self._param_ids.clear()
        self._discover_param_ids()
        if not self._param_ids:
            self._last_rescan_error = (
                f"could not find {self._wire_effect_name!r} effect in comp"
            )
            LOGGER.warning("%s: %s", self.name, self._last_rescan_error)
            return False

        # 3. Fan the 6 canonical names out to every (row, look_n) param id
        #    we discovered. Transition behaviour: with the legacy 7-row Wire
        #    patch, all 42 String Ins get the same 6 names. After surgery
        #    to a single LOOKS group with 6 String Ins, only 6 writes occur.
        for (row_slug, look_idx), pid in self._param_ids.items():
            if look_idx < 1 or look_idx > self._look_count:
                continue
            display = padded[look_idx - 1]
            try:
                self._rest.put_parameter(pid, display)
                self._last_rescan_writes += 1
            except ResolumeRestError as exc:
                self._last_rescan_skipped.append(
                    f"{row_slug}/look{look_idx} (PUT failed: {exc})"
                )

        LOGGER.info(
            "%s: rescan wrote %d String Ins, skipped %d, names=%s",
            self.name,
            self._last_rescan_writes,
            len(self._last_rescan_skipped),
            padded,
        )
        return True

    # ------------------------------------------------------------------
    # Wake-up + REST read

    def _wake_and_read(self) -> list[str] | None:
        """Force the canonical layer's StageFlow into the REST-active
        state, read its look altNames, and restore prior clip + bypass
        state.

        Returns the look names list (1..N as they came back from REST,
        with fallbacks for missing slots), or None on hard failure.
        """
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            self._last_rescan_error = f"comp GET failed: {exc}"
            LOGGER.warning("%s: %s", self.name, self._last_rescan_error)
            return None

        layers = comp.get("layers") or []
        idx0 = self._layer_index - 1
        if idx0 < 0 or idx0 >= len(layers):
            self._last_rescan_error = (
                f"canonical layer {self._layer_index} out of range "
                f"({len(layers)} layers in comp)"
            )
            LOGGER.warning("%s: %s", self.name, self._last_rescan_error)
            return None
        layer_node = layers[idx0]
        sf_eff = find_layer_effect_node(comp, self._layer_index, "StageFlow")
        if sf_eff is None:
            self._last_rescan_error = (
                f"no StageFlow effect on layer {self._layer_index}"
            )
            LOGGER.warning("%s: %s", self.name, self._last_rescan_error)
            return None

        bypass_node = sf_eff.get("bypassed") or {}
        bypass_id = bypass_node.get("id")
        orig_bypassed = bool(bypass_node.get("value", False))

        # If any clip is connected, we leave it alone; the bypass cycle
        # alone wakes the effect. If nothing is connected, we temp-connect
        # clip 1 (the well-known "first clip") and clear after.
        had_active_clip = layer_node.get("active_clip") is not None
        connected_clip_for_wake = had_active_clip

        # --- Step 1: ensure a clip is connected.
        if not connected_clip_for_wake:
            connect_addr = (
                f"/composition/layers/{self._layer_index}/clips/1/connect"
            )
            # Press + release pair. Resolume needs to see the trigger
            # transition false->true->false; a sole "press" message can
            # leave the button latched as held.
            self._osc.send(connect_addr, 1.0)
            self._sleep(0.05)
            self._osc.send(connect_addr, 0.0)
            self._sleep(self._step_delay)

        # --- Step 2: bypass cycle.
        if bypass_id is not None:
            try:
                self._rest.put_parameter(int(bypass_id), True)
                self._sleep(self._step_delay)
                self._rest.put_parameter(int(bypass_id), False)
                self._sleep(self._step_delay)
            except ResolumeRestError as exc:
                LOGGER.warning(
                    "%s: bypass cycle PUT failed: %s", self.name, exc
                )

        # --- Step 3: read the now-materialised Look altNames.
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            self._last_rescan_error = f"comp GET (post-wake) failed: {exc}"
            LOGGER.warning("%s: %s", self.name, self._last_rescan_error)
            return None
        sf_eff = find_layer_effect_node(comp, self._layer_index, "StageFlow")
        look_names = self._extract_look_names(sf_eff)

        # --- Step 4: restore.
        if bypass_id is not None and orig_bypassed:
            try:
                self._rest.put_parameter(int(bypass_id), True)
            except ResolumeRestError as exc:
                LOGGER.warning(
                    "%s: bypass restore PUT failed: %s", self.name, exc
                )
        if not had_active_clip:
            # Disconnect via the layer-level /clear OSC path. The /connect
            # path with value 0.0 does NOT disconnect — verified live
            # 2026-05-12. /clear expects a press + release pair (float 1.0
            # then 0.0); sending bool True leaves it latched as held.
            clear_addr = f"/composition/layers/{self._layer_index}/clear"
            self._osc.send(clear_addr, 1.0)
            self._sleep(0.05)
            self._osc.send(clear_addr, 0.0)

        return look_names

    def _extract_look_names(self, sf_eff: dict | None) -> list[str]:
        """Pull altNames out of a StageFlow effect's REST params dict.

        Returns a list of length `_look_count`, indexed 0..N-1 for Look 1..N.
        Missing or empty altNames become `_fallback_label`.
        """
        out = [self._fallback_label] * self._look_count
        if not sf_eff:
            return out
        params = sf_eff.get("params")
        if not isinstance(params, dict):
            return out
        for n in range(1, self._look_count + 1):
            key = f"Look {n}"
            node = params.get(key)
            if not isinstance(node, dict):
                continue
            view = node.get("view")
            altname = ""
            if isinstance(view, dict):
                altname = view.get("alternative_name") or ""
            if not altname:
                continue
            out[n - 1] = self._format_label(altname)
        return out

    def _format_label(self, altname: str) -> str:
        if not altname:
            return self._fallback_label
        if self._strip_numeric_prefix:
            return re.sub(r"^\d+-", "", altname)
        return altname

    # ------------------------------------------------------------------
    # Wire String In param ID discovery

    def _discover_param_ids(self) -> None:
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            LOGGER.warning(
                "%s: comp fetch failed during param discovery: %s",
                self.name,
                exc,
            )
            return
        eff = find_effect_node(comp, self._wire_effect_name)
        if not eff:
            return
        params = eff.get("params") or {}
        if not isinstance(params, dict):
            return

        # The Wire patch's String Ins are flattened into the effect's
        # params dict, keyed by display name like "GROUP VIDEO LOOK 1 NAME"
        # (pre-collapse) or "LOOK 1 NAME" (post-collapse, single LOOKS group).
        # Walk every key, strip to alphanumeric slug, and pattern-match
        # `<row_slug>look<N>name` or `look<N>name`.
        for key, node in params.items():
            if not isinstance(node, dict) or "id" not in node:
                continue
            slug = "".join(ch.lower() for ch in str(key) if ch.isalnum())
            m = re.match(r"^(.*)look(\d+)name$", slug)
            if not m:
                continue
            row_slug = m.group(1) or "looks"
            try:
                look_idx = int(m.group(2))
            except (TypeError, ValueError):
                continue
            try:
                self._param_ids[(row_slug, look_idx)] = int(node["id"])
            except (TypeError, ValueError):
                continue
        LOGGER.info(
            "%s: discovered %d Wire String In param IDs",
            self.name,
            len(self._param_ids),
        )

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "wire_effect_name": self._wire_effect_name,
            "layer_index": self._layer_index,
            "look_count": self._look_count,
            "param_ids_known": len(self._param_ids),
            "last_rescan_at": self._last_rescan_at,
            "last_rescan_writes": self._last_rescan_writes,
            "last_rescan_skipped_count": len(self._last_rescan_skipped),
            "last_rescan_skipped": list(self._last_rescan_skipped[:5]),
            "last_rescan_error": self._last_rescan_error,
            "last_look_names": list(self._last_look_names),
            "rescan_count": self._rescan_count,
        }


# ---------------------------------------------------------------------------
# Legacy .avc parser. Kept exported so any tests that exercise the standalone
# function still run, and so future cold-boot fallback paths can read the
# saved comp file. The engine itself no longer calls this on rescan.

from collections import defaultdict


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
_FFGL_PLUGIN_PATTERN = re.compile(r"<FFGLPlugin\b")
_SF_BLOCK_BYTES = 32768


def parse_stageflow_altnames(
    comp_path: Path | str,
) -> dict[tuple[str, int], dict[str, str]]:
    """Parse altNames for every StageFlow instance in a comp .avc file.

    Returns a dict keyed by ('group', n) or ('layer', n) -> {look_label:
    altname}. Look labels missing from a particular instance are simply
    absent from the inner dict.

    Raises OSError/IOError on unreadable files.
    """
    path = Path(comp_path)
    text = path.read_text(encoding="utf-8", errors="replace")

    layer_opens = list(_LAYER_OPEN_PATTERN.finditer(text))
    group_opens = list(_GROUP_OPEN_PATTERN.finditer(text))

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

    event_idx = 0
    layer_stack: list[int] = []
    group_stack: list[int] = []
    for sf in sf_matches:
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

        if layer_stack and group_stack:
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

        chunk_start = sf.start()
        hard_end = chunk_start + _SF_BLOCK_BYTES
        ffgl_match = _FFGL_PLUGIN_PATTERN.search(text, chunk_start, hard_end)
        chunk_end = ffgl_match.start() if ffgl_match else hard_end
        snippet = text[chunk_start:chunk_end]
        for look_label, altname in _LOOK_PARAM_PATTERN.findall(snippet):
            results[key][look_label] = altname or ""

    return dict(results)
