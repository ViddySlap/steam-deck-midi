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

The pass drops /composition/master to 0 BEFORE any other write (so any
tiny visible artifact during bool flips is invisible) and restores it
in a try/finally so the screen always returns even if a wiggle step
raises. Paces messages ~2ms apart to avoid UDP packet loss, and
serialises to the worker so spammed presses dont stack.

Bool paths that disable the audio engine (engineenable / bypassed) are
excluded from the wiggle iteration by default — flipping them produces
a perceptible engine drop-out for the operator even though comp master
is masked, because the audio_opacity bridge engine reacts to the CC
echo and resets its state machine. See DEFAULT_ENGINE_ENABLE_EXCLUDES.
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

# Paths that, when wiggled as a bool flip, visibly toggle the audio engine
# on/off rather than just nudging a parameter back to its original value.
# These bool params are wired to either Resolume's effect bypass or to
# Wire-patch dashboard "engine enable" inputs whose downstream effect is a
# full-bypass disable. Flipping them mid-sync resets the audio_opacity
# bridge engine's state machine (it listens for the CC echo on cc_enable)
# and manifests as a perceptible engine drop-out at sync time even though
# comp master is masked. The sync pass leaves these alone — values are
# already correct (they were authored by the operator), and Resolume will
# re-broadcast their state at the next natural occasion.
DEFAULT_ENGINE_ENABLE_EXCLUDES: tuple[str, ...] = (
    "/composition/video/effects/audioengine/effect/engine/engineenable",
    "/composition/video/effects/audioengine/bypassed",
)


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
        # Bool wiggle on these paths flips the audio engine on/off, which is
        # not a "tiny parameter nudge" — see DEFAULT_ENGINE_ENABLE_EXCLUDES.
        # Operators can override (e.g. add an autopilot enable path) via
        # `engine_enable_excludes` in engines/osc_sync.json.
        raw_excludes = config.get("engine_enable_excludes", DEFAULT_ENGINE_ENABLE_EXCLUDES)
        self._engine_enable_excludes: frozenset[str] = frozenset(
            str(p) for p in raw_excludes if p
        )
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
        self._last_pass_skipped_paths: list[str] = []
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
            "last_pass_skipped_paths": list(self._last_pass_skipped_paths),
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
        self._last_pass_skipped_paths = []

        # Sequencing rule (Bug 1, 2026-05-12): comp master must be at 0
        # BEFORE any wiggle write goes out, and must be restored AFTER the
        # last wiggle write. Concretely:
        #   1. Parse targets (lazy first-pass parse from OSC preset XML)
        #   2. REST GET composition (reads current master + builds path_index)
        #   3. Drop comp master to 0 (mask) — done BEFORE the indicator dance
        #      and BEFORE any wiggle write so the operator's screen is black
        #      for the entire visible-side-effects window.
        #   4. Sync indicator force-transition dance (0 -> sleep 0.3s -> 1)
        #      runs DURING the mask so the 0.3s settle is hidden behind the
        #      black-out, not visible on screen.
        #   5. Wiggle all targets (master at 0 the whole time)
        #   6. Restore comp master to cached value  (try/finally)
        #   7. Release sync indicator (same try/finally)
        # The try/finally on master restore guarantees the screen comes
        # back even if a wiggle step raises mid-loop — the operator never
        # ends up stuck behind a 0-opacity master.

        masked = False
        prev_master: Any = None
        path_index: dict[str, dict[str, Any]] = {}
        targets: list[SyncTarget] = []
        try:
            if self._targets is None:
                try:
                    self.resync_targets()
                except Exception as exc:  # noqa: BLE001 - never let the worker die silently
                    self._last_pass_error = f"target parse failed: {exc}"
                    LOGGER.exception("osc_sync: target parse failed")
                    # Still run the indicator dance below so the operator's
                    # button visually responds to the press even on no-op.
                    self._do_indicator_dance()
                    return

            # Exclude paths the engine actively drives during the pass:
            # - sync indicator (engine holds true throughout, would otherwise
            #   wiggle off mid-pass)
            # - comp master (mask sets to 0; wiggling pulls back to cached value)
            # - engine on/off bypass paths (flipping them disables the audio
            #   engine briefly, which the audio_opacity bridge engine then
            #   reacts to — visible to the operator even with master masked).
            excluded = {self._sync_indicator_path, COMP_MASTER_PATH} | self._engine_enable_excludes
            targets = [t for t in (self._targets or ()) if t.osc_path not in excluded]
            self._last_pass_target_count = len(targets)
            if not targets:
                LOGGER.warning("osc_sync: no targets; sync pass is a no-op")
                # Still fire the indicator dance so the operator's button
                # visually responds to the press.
                self._do_indicator_dance()
                return

            # Single REST GET serves both purposes: cache prev_master for the
            # mask + restore, and build the path_index for wiggle resolution.
            # We do this BEFORE dropping master so the read returns the real
            # current value rather than the masked 0.
            try:
                path_index = self._build_path_index()
            except ResolumeRestError as exc:
                self._last_pass_error = f"composition fetch failed: {exc}"
                LOGGER.error("osc_sync: %s", self._last_pass_error)
                # No mask possible without prev_master, but still fire the
                # indicator dance so the button visually responds.
                self._do_indicator_dance()
                return

            # DROP MASTER FIRST (bug 1 fix). prev_master must be cached
            # before the OSC write so the finally clause can restore it.
            master_meta = path_index.get(COMP_MASTER_PATH)
            prev_master = master_meta.get("value") if master_meta else None
            if self._mask_with_master and prev_master is not None:
                self._osc.send(COMP_MASTER_PATH, 0.0)
                self._sleep(self._inter_message_delay_seconds)
                masked = True

            # Now that master is at 0, force the sync-indicator dance. The
            # 0.3s settle is hidden behind the black-out so nothing visible
            # leaks out during the wait for any pending button release.
            self._do_indicator_dance()

            for target in targets:
                meta = self._resolve_target(target.osc_path, path_index)
                if meta is None or "value" not in meta:
                    LOGGER.debug("osc_sync: no comp parameter for %s; skipping", target.osc_path)
                    self._last_pass_skipped_count += 1
                    self._last_pass_skipped_paths.append(target.osc_path)
                    continue
                if self._wiggle(target, meta):
                    self._last_pass_wiggle_count += 1
                else:
                    self._last_pass_skipped_count += 1
                    self._last_pass_skipped_paths.append(target.osc_path)
                self._sleep(self._inter_message_delay_seconds)
        finally:
            # Restore comp master FIRST (so the screen comes back even if
            # sync_indicator release errors), then release sync_indicator.
            # Both run regardless of how the pass exited.
            if masked:
                try:
                    self._osc.send(COMP_MASTER_PATH, float(prev_master))
                    self._sleep(self._inter_message_delay_seconds)
                except (TypeError, ValueError):
                    LOGGER.warning("osc_sync: could not restore master to %r", prev_master)
            # Release the SYNC indicator regardless of how the pass ended.
            # Operator's button visually un-highlights to signal "done."
            self._osc.send(self._sync_indicator_path, 0.0)
            self._last_pass_completed_at = self._clock()
            self._syncing = False
            LOGGER.info(
                "osc_sync: sync pass complete in %.2fs; %d wiggled, %d skipped",
                (self._last_pass_completed_at or 0) - (self._last_pass_started_at or 0),
                self._last_pass_wiggle_count,
                self._last_pass_skipped_count,
            )

    def _do_indicator_dance(self) -> None:
        """Force a 0 -> 1 transition on the SYNC indicator so Resolume
        broadcasts OSC OUT to TouchOSC, lighting the operator's button.

        The button-press already drove the wire bool to 1, then ~200ms
        later the button release drove it back to 0. We need the wire
        bool at 1 throughout the pass, but writing True now would be a
        no-op (already 1) and might not broadcast — and even if it did,
        the upcoming button release would override us. So: write False
        explicitly first, sleep long enough for any pending button
        release to land, then write True. The False+True pair guarantees
        a 0 -> 1 transition that Resolume broadcasts. We use float
        0.0/1.0 (not bool) to match what button613 itself sends and keep
        the wire patch's input typing consistent.
        """
        self._osc.send(self._sync_indicator_path, 0.0)
        self._sleep(0.3)
        self._osc.send(self._sync_indicator_path, 1.0)
        self._sleep(self._inter_message_delay_seconds)

    def _resolve_target(self, target_path: str, path_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        """Resolve an XML preset path to a JSON-tree parameter meta.

        Resolume's OSC paths for Wire patch dashboard params include the
        dashboard group as an extra segment (e.g. ".../audioengine/effect/engine/engineenable"
        where "engine" is the dashboard group). The JSON tree's `params`
        dict is flat — no group nesting. The path-walker emits
        `audioengine/effect/engineenable` (no group), which doesn't match.
        Fix: if the literal path misses, try collapsing the group segment.
        """
        meta = path_index.get(target_path)
        if meta is not None:
            return meta
        # Pattern: .../effect/<group>/<param-slug> -> .../effect/<param-slug>
        parts = target_path.split("/")
        if len(parts) >= 3 and parts[-3] == "effect":
            collapsed = "/".join(parts[:-2] + [parts[-1]])
            if collapsed in path_index:
                return path_index[collapsed]
        return None

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
                span = pmax - pmin
                if span <= 0:
                    return False
                # Resolume's OSC :7000 normalizes 0-1 over the param's actual
                # range for Wire-patch dashboard inputs and layer transition
                # paths (confirmed via probe 2026-05-08; same family as the
                # autopilot v0.4.2 layer-transition normalization). Sending
                # the raw REST value saturates anything with range != [0,1].
                # Convert raw -> normalized before send. For [0,1] params
                # this is a no-op.
                cur_norm = (cur_f - pmin) / span
                eps = self._epsilon_float  # epsilon lives in normalized 0..1 space
                if cur_norm + eps <= 1.0:
                    nudge_norm = cur_norm + eps
                elif cur_norm - eps >= 0.0:
                    nudge_norm = cur_norm - eps
                else:
                    return False
                self._osc.send(target.osc_path, nudge_norm)
                self._sleep(self._inter_message_delay_seconds)
                self._osc.send(target.osc_path, cur_norm)
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
