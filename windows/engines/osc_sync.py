"""OSC sync engine.

Bens daily startup ritual: when Resolume + TouchOSC open cold, TouchOSC
controls show their default values, not Resolumes actual current state.
He has to wiggle every parameter to coax Resolume into broadcasting OSC
out so TouchOSC catches up.

This engine automates that ritual. Press a button -> the engine reads
the OSC shortcut preset XML to enumerate every binding Resolume sends
OSC OUT for, walks the composition once to capture each parameters
current value, and for every target writes a nudge then writes the
original back via OSC. Resolume re-broadcasts on each change, TouchOSC
catches up.

We use OSC for writes (Resolume natively resolves named paths like
/composition/video/effects/audioengine/effect/audiofft/behaviour/gain)
and REST GET only to read current values. That keeps the path-resolution
problem on Resolumes side where it already works.

Trigger path:
    TouchOSC button -> OSC -> comp-level "OSC Sync" wire patch SYNC bool
    -> wire MIDI Out CC 90 ch15 -> DECK_OUT -> on_midi_in(rising edge)
    -> worker thread runs the wiggle pass

The pass briefly drops /composition/master to 0 (so any tiny visible
artifact during bool flips is invisible) and restores it after, paces
messages ~2ms apart to avoid UDP packet loss, and serialises to the
worker so spammed presses dont stack.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.engines.osc_preset import (
    KIND_BOOL,
    KIND_FLOAT,
    KIND_INT,
    SyncTarget,
    parse_osc_preset,
)
from windows.engines.resolume_rest import ResolumeRestClient, ResolumeRestError
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)


COMP_MASTER_PATH = "/composition/master"


class OscSyncEngine(Engine):
    type_name = "osc_sync"

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
        self._input_channel = int(inputs.get("channel", 14))
        self._cc_sync = int(inputs.get("cc_sync", 90))

        self._osc_preset_path = str(
            config.get(
                "osc_preset_path",
                "C:/Users/Ben/OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml",
            )
        )
        self._epsilon_float = float(config.get("epsilon_float", 0.001))
        self._inter_message_delay_seconds = (
            float(config.get("inter_message_delay_ms", 50.0)) / 1000.0
        )
        self._mask_with_master = bool(config.get("mask_with_master", True))
        # Engine writes this OSC path with 1 at sync start and 0 at sync end.
        # When Ben adds an OSC OUT for the same path in Resolume's preset,
        # TouchOSC echoes the bool back to the trigger button, so the button
        # stays highlighted for the full duration of the wiggle pass.
        self._sync_indicator_path = str(
            config.get(
                "sync_indicator_path",
                "/composition/video/effects/oscsync/effect/sync/sync",
            )
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
        self._targets: list[SyncTarget] | None = None
        self._last_cc_value = 0
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stopped = False
        # While true, the engine ignores all incoming CC events on the sync
        # channel — protects against re-triggering when our own write of the
        # SYNC indicator (=1) feeds back through the wire patch as a fresh
        # CC rising edge.
        self._syncing = False

        self._last_pass_started_at: float | None = None
        self._last_pass_completed_at: float | None = None
        self._last_pass_target_count = 0
        self._last_pass_wiggle_count = 0
        self._last_pass_skipped_count = 0
        self._last_pass_error: str | None = None

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel or cc != self._cc_sync:
            return
        # Swallow CCs that our own writes to the SYNC indicator path
        # produce while a pass is running. Without this guard, writing
        # `sync_indicator=1` at the start of the pass would feed back
        # through the wire patch as a fresh rising edge.
        if self._syncing:
            self._last_cc_value = value
            return
        prev, self._last_cc_value = self._last_cc_value, value
        if value > 0 and prev == 0:
            self._spawn_pass()

    def resync_targets(self) -> int:
        """Re-read the OSC preset XML and rebuild the wigglable target list.

        Called lazily on first sync and explicitly by the mapping UI's
        "Resync OSC Wiggles" button so Ben can pick up new bindings he
        added manually in Resolume without restarting the bridge.

        Returns the new target count.
        """
        targets = parse_osc_preset(self._osc_preset_path)
        with self._lock:
            self._targets = targets
        LOGGER.info("osc_sync: parsed %d wigglable targets from %s", len(targets), self._osc_preset_path)
        return len(targets)

    def shutdown(self) -> None:
        self._stopped = True
        worker = self._worker
        if worker is not None:
            worker.join(timeout=5.0)
        try:
            self._osc.close()
        except Exception:
            pass

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "syncing": self._syncing,
            "target_count": len(self._targets) if self._targets is not None else None,
            "last_pass_started_at": self._last_pass_started_at,
            "last_pass_completed_at": self._last_pass_completed_at,
            "last_pass_wiggle_count": self._last_pass_wiggle_count,
            "last_pass_skipped_count": self._last_pass_skipped_count,
            "last_pass_error": self._last_pass_error,
        }

    def _spawn_pass(self) -> None:
        """Run the sync pass on a worker thread.

        A lock-free "is the previous worker still alive" check serialises
        rapid presses; the receive loop never blocks on REST or sleeps.
        """
        if self._stopped:
            return
        worker = self._worker
        if worker is not None and worker.is_alive():
            LOGGER.info("osc_sync: previous sync still running; skipping new trigger")
            return
        self._worker = threading.Thread(target=self._run_sync_pass, name="osc-sync", daemon=True)
        self._worker.start()

    def _run_sync_pass(self) -> None:
        self._syncing = True
        self._last_pass_started_at = self._clock()
        self._last_pass_error = None
        self._last_pass_wiggle_count = 0
        self._last_pass_skipped_count = 0

        # Hold the SYNC indicator true for the duration. TouchOSC's
        # OSC-OUT echo of this path will keep button613 highlighted until
        # we release at the end. Done before any other work so the visual
        # indicator goes up immediately.
        self._osc.send(self._sync_indicator_path, True)
        self._sleep(self._inter_message_delay_seconds)

        try:
            if self._targets is None:
                try:
                    self.resync_targets()
                except Exception as exc:  # noqa: BLE001 - never let the worker die silently
                    self._last_pass_error = f"target parse failed: {exc}"
                    LOGGER.exception("osc_sync: target parse failed")
                    return

            targets = [
                t
                for t in (self._targets or ())
                if t.osc_path != self._sync_indicator_path
            ]
            self._last_pass_target_count = len(targets)
            if not targets:
                LOGGER.warning("osc_sync: no targets; sync pass is a no-op")
                return

            try:
                path_index = self._build_path_index()
            except ResolumeRestError as exc:
                self._last_pass_error = f"composition fetch failed: {exc}"
                LOGGER.error("osc_sync: %s", self._last_pass_error)
                return

            master_meta = path_index.get(COMP_MASTER_PATH)
            prev_master = master_meta.get("value") if master_meta else None
            masked = False
            if self._mask_with_master and prev_master is not None:
                self._osc.send(COMP_MASTER_PATH, 0.0)
                self._sleep(self._inter_message_delay_seconds)
                masked = True

            try:
                for target in targets:
                    meta = path_index.get(target.osc_path)
                    if meta is None or "value" not in meta:
                        LOGGER.debug("osc_sync: no comp parameter for %s; skipping", target.osc_path)
                        self._last_pass_skipped_count += 1
                        continue
                    if self._wiggle(target, meta):
                        self._last_pass_wiggle_count += 1
                    else:
                        self._last_pass_skipped_count += 1
                    self._sleep(self._inter_message_delay_seconds)
            finally:
                if masked:
                    try:
                        self._osc.send(COMP_MASTER_PATH, float(prev_master))
                        self._sleep(self._inter_message_delay_seconds)
                    except (TypeError, ValueError):
                        LOGGER.warning("osc_sync: could not restore master to %r", prev_master)
        finally:
            # Release the SYNC indicator regardless of how the pass ended.
            # Operator's button visually un-highlights to signal "done."
            self._osc.send(self._sync_indicator_path, False)
            self._last_pass_completed_at = self._clock()
            self._syncing = False
            LOGGER.info(
                "osc_sync: sync pass complete in %.2fs; %d wiggled, %d skipped",
                (self._last_pass_completed_at or 0) - (self._last_pass_started_at or 0),
                self._last_pass_wiggle_count,
                self._last_pass_skipped_count,
            )

    def _build_path_index(self) -> dict[str, dict[str, Any]]:
        """Walk GET /api/v1/composition once and build {osc_path -> {value, min, max}}.

        Resolumes JSON tree mirrors the OSC namespace closely. Layers and
        groups are lists indexed positionally; effects are lists where
        each item carries a "name" we use as the path segment; dashboard
        links and parameter leaves are name-keyed dict entries with
        id+value fields.

        We are tolerant of structural surprises: bindings whose XML path
        we cannot resolve in the tree are simply skipped during the
        sync pass with a debug log.
        """
        comp = self._rest.get_composition()
        index: dict[str, dict[str, Any]] = {}
        _index_node(comp, "/composition", index)
        return index

    def _wiggle(self, target: SyncTarget, meta: dict[str, Any]) -> bool:
        current = meta.get("value")
        if current is None:
            return False
        try:
            if target.kind == KIND_FLOAT:
                pmin = _coerce_float(meta.get("min"), 0.0)
                pmax = _coerce_float(meta.get("max"), 1.0)
                cur_f = float(current)
                nudge = cur_f + self._epsilon_float
                if nudge > pmax:
                    nudge = cur_f - self._epsilon_float
                if nudge < pmin:
                    nudge = cur_f
                self._osc.send(target.osc_path, nudge)
                self._sleep(self._inter_message_delay_seconds)
                self._osc.send(target.osc_path, cur_f)
                return True
            if target.kind == KIND_BOOL:
                cur_b = bool(current)
                self._osc.send(target.osc_path, not cur_b)
                self._sleep(self._inter_message_delay_seconds)
                self._osc.send(target.osc_path, cur_b)
                return True
            if target.kind == KIND_INT:
                pmin = int(_coerce_float(meta.get("min"), 0))
                pmax = int(_coerce_float(meta.get("max"), 127))
                cur_i = int(current)
                nudge = cur_i + 1 if cur_i < pmax else cur_i - 1
                if nudge < pmin:
                    nudge = cur_i
                self._osc.send(target.osc_path, nudge)
                self._sleep(self._inter_message_delay_seconds)
                self._osc.send(target.osc_path, cur_i)
                return True
        except Exception:  # noqa: BLE001 - logged + skipped, never crash the pass
            LOGGER.debug("osc_sync: wiggle failed for %s", target.osc_path, exc_info=True)
            return False
        return False


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# Keys we never descend into (metadata that would create bogus paths).
_SKIP_KEYS = frozenset({"id", "value", "valuetype", "valuerange", "options"})

# Map Resolume JSON keys to their OSC namespace equivalent. Resolume's
# OSC paths use these aliases; the JSON tree uses the LHS form.
_KEY_ALIASES = {
    "layergroups": "groups",
}


def _is_param_leaf(node: dict[str, Any]) -> bool:
    return "id" in node and "value" in node


def _index_node(node: Any, path: str, index: dict[str, dict[str, Any]]) -> None:
    """Walk Resolume's composition JSON, building OSC-path -> param meta.

    Resolume's OSC namespace is regular but has a few mappings to know:
    - `layergroups` in JSON is `groups` in OSC.
    - Effects expose params under `effects[i].params`, but the OSC path
      for a Wire-patch dashboard param uses `effects/<slug>/effect/<param-slug>`
      with a synthetic `effect` segment between the effect slug and param.
    - Dashboard links use slugified keys like `link1`/`link6` (display
      name `Link 1` -> `link1`).

    We pessimistically register every parameter leaf at every plausible
    path so the wiggle pass can find what the XML preset references.
    """
    if isinstance(node, dict):
        if _is_param_leaf(node):
            meta: dict[str, Any] = {"value": node.get("value")}
            vr = node.get("valuerange")
            if isinstance(vr, dict):
                if "min" in vr:
                    meta["min"] = vr["min"]
                if "max" in vr:
                    meta["max"] = vr["max"]
            if "min" in node:
                meta["min"] = node["min"]
            if "max" in node:
                meta["max"] = node["max"]
            index[path] = meta

        for key, child in node.items():
            if key in _SKIP_KEYS:
                continue
            mapped_key = _KEY_ALIASES.get(key, key)
            if key == "params":
                # Effect params: emit BOTH the elided form (params drop into
                # the parent path) AND the OSC convention with the synthetic
                # `effect` segment. The elided form catches non-effect params
                # like layer transition; the `effect` form catches Wire patch
                # dashboard inputs.
                if isinstance(child, dict):
                    for pkey, pval in child.items():
                        slug = _slug(pkey)
                        if not isinstance(pval, (dict, list)):
                            continue
                        # elided
                        _index_at(pval, _join(path, slug), index)
                        # with synthetic 'effect' segment (Wire patch convention)
                        _index_at(pval, _join(_join(path, "effect"), slug), index)
                continue
            if key == "dashboard" and isinstance(child, dict):
                # Dashboard links: keys like "Link 1" -> slug "link1"
                for dkey, dval in child.items():
                    if not isinstance(dval, (dict, list)):
                        continue
                    _index_at(dval, _join(_join(path, "dashboard"), _slug(dkey)), index)
                continue
            sub_path = _join(path, mapped_key)
            if isinstance(child, dict):
                _index_node(child, sub_path, index)
            elif isinstance(child, list):
                _index_list(child, sub_path, key, index)
    elif isinstance(node, list):
        _index_list(node, path, "", index)


def _index_at(node: Any, path: str, index: dict[str, dict[str, Any]]) -> None:
    """Index a single subtree at a specific OSC path."""
    if isinstance(node, dict):
        if _is_param_leaf(node):
            meta: dict[str, Any] = {"value": node.get("value")}
            if "min" in node:
                meta["min"] = node["min"]
            if "max" in node:
                meta["max"] = node["max"]
            index[path] = meta
        # Don't recurse — params are leaves for our purposes
    # Lists rarely appear inside params/dashboard, but tolerate them
    elif isinstance(node, list):
        for i, item in enumerate(node, start=1):
            _index_at(item, _join(path, str(i)), index)


def _slug(name: str) -> str:
    """Match Resolume's OSC name slugging: lowercased + alphanumerics only."""
    return "".join(ch.lower() for ch in name if ch.isalnum())


def _index_list(items: list, parent_path: str, parent_key: str, index: dict[str, dict[str, Any]]) -> None:
    for i, item in enumerate(items, start=1):
        if isinstance(item, dict):
            named = _named_segment(item)
            # Index BOTH positional and named paths if the item has a name —
            # Resolume's OSC namespace uses positions for layers/groups/clips
            # and names for effects, but our XML preset paths sometimes use
            # whichever Resolume chose. Indexing both is cheap and tolerant.
            _index_node(item, _join(parent_path, str(i)), index)
            if named is not None:
                _index_node(item, _join(parent_path, named), index)
        else:
            _index_node(item, _join(parent_path, str(i)), index)


def _named_segment(item: dict[str, Any]) -> str | None:
    name_obj = item.get("name")
    raw_name: str | None = None
    if isinstance(name_obj, dict):
        raw_name = name_obj.get("value") if isinstance(name_obj.get("value"), str) else None
    elif isinstance(name_obj, str):
        raw_name = name_obj
    if not raw_name:
        return None
    # Resolume's OSC effect-name slugs are lowercased + alphanumerics only.
    # The "audioengine" path segment for the "Audio Engine" effect is the
    # canonical example.
    slug = "".join(ch.lower() for ch in raw_name if ch.isalnum())
    return slug or None


def _join(prefix: str, segment: str) -> str:
    if not segment:
        return prefix
    if segment.startswith("/"):
        return prefix.rstrip("/") + segment
    return prefix.rstrip("/") + "/" + segment
