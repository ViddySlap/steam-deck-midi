"""Engine loading + registry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Iterable

from windows.engines.audio_opacity import AudioOpacityEngine
from windows.engines.autopilot import AutopilotEngine
from windows.engines.autopilot_ptz import AutopilotPtzEngine
from windows.engines.base import Engine
from windows.engines.bumper_blast import BumperBlastEngine
from windows.engines.chaser_stack_dispatcher import ChaserStackDispatcherEngine
from windows.engines.flash_blast import FlashBlastEngine
from windows.engines.global_color import GlobalColorEngine
from windows.engines.gyro_feedback import GyroFeedbackEngine
from windows.engines.l_stick_layer import LStickLayerEngine
from windows.engines.nestdrop_engine import NestdropEngine
from windows.engines.osc_sync import OscSyncEngine
from windows.engines.ptz_visca import PtzViscaEngine
from windows.engines.stageflow_bridge import StageFlowBridgeEngine
from windows.engines.steam_input_layer_tracker import SteamInputLayerTrackerEngine
from windows.midi import MidiOut

NoteEmitFilter = Callable[[int, int, int, float], bool]
"""Filter signature: (channel, note, velocity, now) -> True to allow emit, False to defer."""

LOGGER = logging.getLogger(__name__)

_ENGINE_TYPES: dict[str, type[Engine]] = {
    AudioOpacityEngine.type_name: AudioOpacityEngine,
    OscSyncEngine.type_name: OscSyncEngine,
    AutopilotEngine.type_name: AutopilotEngine,
    AutopilotPtzEngine.type_name: AutopilotPtzEngine,
    SteamInputLayerTrackerEngine.type_name: SteamInputLayerTrackerEngine,
    BumperBlastEngine.type_name: BumperBlastEngine,
    ChaserStackDispatcherEngine.type_name: ChaserStackDispatcherEngine,
    FlashBlastEngine.type_name: FlashBlastEngine,
    GlobalColorEngine.type_name: GlobalColorEngine,
    GyroFeedbackEngine.type_name: GyroFeedbackEngine,
    LStickLayerEngine.type_name: LStickLayerEngine,
    NestdropEngine.type_name: NestdropEngine,
    PtzViscaEngine.type_name: PtzViscaEngine,
    StageFlowBridgeEngine.type_name: StageFlowBridgeEngine,
}

_USER_DIR_NAME = "engines"
_FACTORY_DIR_NAME = "engines.factory"
_LEGACY_USER_FILE = "engines.json"
_LEGACY_FACTORY_FILE = "engines.factory.json"


class EngineRegistry:
    """Holds active engines, dispatches MIDI feedback + ticks.

    Also brokers two engine→receiver hooks:

    - **MIDI clock dispatch.** `on_midi_clock(message_type, now)` fans out to
      every engine; tempo-driven engines (e.g. autopilot) derive BPM from the
      tick stream.
    - **Note-emit filters.** Engines can register a callback via
      `add_note_emit_filter`; the receiver consults `should_emit_note` before
      every outbound `midi_out.note_on(...)` call. If any filter returns
      False the receiver skips the emit, allowing the engine to defer or
      drop the note (e.g. autopilot quantizing column triggers to the next
      beat boundary).
    """

    def __init__(self, engines: Iterable[Engine] = ()) -> None:
        self._engines: list[Engine] = list(engines)
        self._note_emit_filters: list[NoteEmitFilter] = []

    @property
    def engines(self) -> list[Engine]:
        return list(self._engines)

    def add(self, engine: Engine) -> None:
        self._engines.append(engine)

    def add_note_emit_filter(self, callback: NoteEmitFilter) -> None:
        """Register a pre-emit filter for outbound note_on messages."""
        self._note_emit_filters.append(callback)

    def should_emit_note(
        self, channel: int, note: int, velocity: int, now: float
    ) -> bool:
        """Return True if the receiver should proceed with `midi_out.note_on(...)`.

        Returns False as soon as any filter returns False — that filter has
        taken responsibility for the note (it will re-emit later or drop it).
        Filter exceptions are caught and treated as "allow" so a buggy engine
        doesn't black-hole show-critical input.
        """
        for callback in self._note_emit_filters:
            owner = getattr(callback, "__self__", None)
            if isinstance(owner, Engine) and not owner.active:
                # Owning engine is disabled — don't let its filter defer/drop
                # notes (e.g. an inactive autopilot must not black-hole input).
                continue
            try:
                if callback(channel, note, velocity, now) is False:
                    return False
            except Exception:
                LOGGER.exception("note-emit filter raised; treating as allow")
        return True

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        for engine in self._engines:
            if not engine.active:
                continue
            try:
                engine.on_midi_in(channel, cc, value, now)
            except Exception:
                LOGGER.exception("engine %s on_midi_in failed", engine.name)

    def on_note_in(self, channel: int, note: int, velocity: int, now: float) -> None:
        """Fan note_on/note_off (velocity=0) events to every active engine."""
        for engine in self._engines:
            if not engine.active:
                continue
            try:
                engine.on_note_in(channel, note, velocity, now)
            except Exception:
                LOGGER.exception("engine %s on_note_in failed", engine.name)

    def on_axis_event(self, action: str, value: int, now: float) -> None:
        """Fan analog axis events to every active engine."""
        for engine in self._engines:
            if not engine.active:
                continue
            try:
                engine.on_axis_event(action, value, now)
            except Exception:
                LOGGER.exception("engine %s on_axis_event failed", engine.name)

    def get_by_type(self, type_name: str) -> Engine | None:
        """Look up the (single) loaded engine for a given type, or None."""
        for engine in self._engines:
            if engine.type_name == type_name:
                return engine
        return None

    def on_midi_clock(self, message_type: str, now: float) -> None:
        for engine in self._engines:
            if not engine.active:
                continue
            try:
                engine.on_midi_clock(message_type, now)
            except Exception:
                LOGGER.exception("engine %s on_midi_clock failed", engine.name)

    def tick(self, now: float) -> None:
        for engine in self._engines:
            if not engine.active:
                continue
            try:
                engine.tick(now)
            except Exception:
                LOGGER.exception("engine %s tick failed", engine.name)

    def shortest_tick_interval(self) -> float | None:
        intervals = [
            engine.tick_interval_seconds()
            for engine in self._engines
            if engine.active and engine.tick_interval_seconds() is not None
        ]
        return min(intervals) if intervals else None

    def set_active_by_type(self, type_name: str, active: bool) -> bool:
        """Set one engine's runtime active flag by type. Returns True if found."""
        engine = self.get_by_type(type_name)
        if engine is None:
            return False
        engine.set_active(active)
        LOGGER.info("engine %s (%s) active=%s", engine.name, type_name, active)
        return True

    def apply_engine_states(self, states: dict[str, bool]) -> None:
        """Apply a preset's {engine_type: active} map to the loaded engines.

        Only engines present in the map are touched; engines absent from the
        map keep their current active flag (so a preset that omits an engine
        leaves it as-is rather than forcing it on). Unknown types are ignored.
        Runs on the receiver thread via the hot-reload path.
        """
        if not states:
            return
        for engine in self._engines:
            if engine.type_name in states:
                engine.set_active(states[engine.type_name])

    def current_states(self) -> dict[str, bool]:
        """Snapshot the loaded engines' active flags as {engine_type: active}."""
        return {engine.type_name: engine.active for engine in self._engines}

    def refresh(self) -> dict[str, str]:
        """Trigger every engine's `refresh()` hook. Used by the dev endpoint.

        Returns a {engine_name: "ok" | error_message} map so the caller can
        report partial failures. One engine raising never blocks the others.
        """
        results: dict[str, str] = {}
        for engine in self._engines:
            try:
                engine.refresh()
                results[engine.name] = "ok"
            except Exception as exc:  # noqa: BLE001 - surface to UI
                LOGGER.exception("engine %s refresh failed", engine.name)
                results[engine.name] = f"error: {exc}"
        return results

    def shutdown(self) -> None:
        for engine in self._engines:
            try:
                engine.shutdown()
            except Exception:
                LOGGER.exception("engine %s shutdown failed", engine.name)

    def status(self) -> list[dict]:
        # Overlay the runtime `active` flag here so it's present regardless of
        # whether a given engine's status() override calls super(). The web UI
        # reads `active` to render its on/off checkbox.
        return [
            {**engine.status(), "active": engine.active}
            for engine in self._engines
        ]


def load_engines(config_path: str | Path, midi_out: MidiOut) -> EngineRegistry:
    """Load engine config from disk and instantiate the registry.

    `config_path` may point at:

    - A directory (preferred, v0.4.0+): each `*.json` file inside is one engine
      stanza. The loader enforces one engine per `type`; on collision the
      alphabetically-first file wins and the rest are skipped with a warning.
    - A file ending in `.json` (legacy v0.3.x): the array-of-stanzas format.
      The loader auto-migrates this on first call by splitting each entry into
      a sibling `engines/<type>.json` file and renaming the original to
      `engines.json.migrated`.
    - A non-existent directory whose sibling holds a legacy `engines.json`
      file: the legacy file is auto-migrated into the (newly-created)
      directory before loading. Covers the case where a v0.3.x install is
      first launched against the v0.4.0 default CLI path.

    **Factory-default merge:** alongside the user dir, the loader looks for an
    `engines.factory/` directory (or legacy `engines.factory.json` file, also
    auto-migrated). For each engine `type` present in the factory but absent
    from the user dir, the factory stanza is merged in-memory (the user dir on
    disk is never modified). This auto-picks up new engine types on installer
    upgrade without clobbering user customizations to engines they've already
    configured.

    Missing config (no dir, no legacy file) → empty registry; engines are
    opt-in.
    """
    path = Path(config_path)

    user_dir = _resolve_user_dir(path)
    if user_dir is None:
        LOGGER.info("no engines config at %s; engine registry is empty", path)
        return EngineRegistry()

    user_specs = _load_user_dir(user_dir)
    user_types = {spec.get("type") for spec in user_specs if spec.get("type")}

    factory_specs = _load_factory(user_dir.parent)
    for fspec in factory_specs:
        ftype = fspec.get("type")
        if not ftype or ftype in user_types:
            continue
        LOGGER.info(
            "auto-merging factory default for engine type %r (not in %s/)",
            ftype,
            user_dir.name,
        )
        user_specs.append(fspec)

    registry = EngineRegistry()

    # Pass 1: instantiate + register every engine. Inter-engine references
    # (e.g. bumper_blast looking up the SteamInput layer tracker) must NOT
    # happen here — config-driven load order is not deterministic, so a
    # dependent engine may load before its dependency.
    for spec in user_specs:
        if not spec.get("enabled", True):
            LOGGER.info("engine %s is disabled in config; skipping", spec.get("name"))
            continue
        engine_type = spec.get("type")
        cls = _ENGINE_TYPES.get(engine_type)
        if cls is None:
            LOGGER.warning("unknown engine type %r; skipping", engine_type)
            continue
        name = spec.get("name", engine_type)
        try:
            engine = cls(name=name, config=spec, midi_out=midi_out)
            registry.add(engine)
            LOGGER.info("loaded engine %s (type=%s)", name, engine_type)
        except Exception:
            LOGGER.exception("failed to instantiate engine %s", name)

    # Pass 2: bind every engine to the now-complete registry so cross-engine
    # lookups resolve correctly regardless of load order.
    for engine in registry.engines:
        try:
            engine.bind_registry(registry)
        except Exception:
            LOGGER.exception("engine %s bind_registry failed", engine.name)

    return registry


def _resolve_user_dir(path: Path) -> Path | None:
    """Resolve the configured path to a user-config directory.

    Returns the directory to scan for `*.json` engine stanzas, or None if no
    config is reachable. Migrates legacy single-file configs as a side effect.

    User-dir + legacy-file coexistence rule: when both are present we keep any
    files already in the user dir (recent customizations win) and only migrate
    legacy stanzas whose `type` isn't already represented. Then the legacy
    file is archived as `engines.json.migrated` so we never re-migrate.
    """
    if path.is_dir():
        _migrate_legacies_alongside(path)
        return path

    if path.is_file() and path.suffix == ".json":
        target_dir = path.parent / _USER_DIR_NAME
        target_dir.mkdir(parents=True, exist_ok=True)
        _migrate_legacies_alongside(target_dir)
        return target_dir

    if not path.exists():
        legacy = path.parent / _LEGACY_USER_FILE
        legacy_factory = path.parent / _LEGACY_FACTORY_FILE
        if path.name == _USER_DIR_NAME and (legacy.is_file() or legacy_factory.is_file()):
            path.mkdir(parents=True, exist_ok=True)
            _migrate_legacies_alongside(path)
            return path
        return None

    return None


def _migrate_legacies_alongside(user_dir: Path) -> None:
    """Migrate legacy `engines.json` and `engines.factory.json` files into per-file dirs.

    Idempotent: once each legacy file is renamed `<name>.migrated`, future
    invocations are no-ops.
    """
    parent = user_dir.parent

    legacy_user = parent / _LEGACY_USER_FILE
    if legacy_user.is_file():
        existing_types = _existing_user_types(user_dir)
        _migrate_legacy_user_file(legacy_user, user_dir, skip_types=existing_types)

    factory_dir = parent / _FACTORY_DIR_NAME
    legacy_factory = parent / _LEGACY_FACTORY_FILE
    if legacy_factory.is_file() and not factory_dir.exists():
        _migrate_legacy_factory_file(legacy_factory, factory_dir)


def _existing_user_types(user_dir: Path) -> set[str]:
    """Return the set of `type` fields already present in user_dir's *.json files."""
    types: set[str] = set()
    for json_path in user_dir.glob("*.json"):
        try:
            spec = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(spec, dict) and spec.get("type"):
            types.add(spec["type"])
    return types


def _migrate_legacy_user_file(
    legacy: Path, target_dir: Path, *, skip_types: set[str]
) -> None:
    """Split a legacy `engines.json` array into per-file stanzas.

    Skips any stanza whose `type` is already represented in `target_dir` so
    user customizations made post-upgrade are not clobbered.
    """
    try:
        raw = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.error("failed to read legacy engines file %s: %s", legacy, exc)
        return
    specs = raw.get("engines", [])
    if not isinstance(specs, list):
        LOGGER.error("legacy %s has no 'engines' array; skipping migration", legacy)
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    migrated = skipped = 0
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        engine_type = spec.get("type") or "engine"
        if engine_type in skip_types:
            LOGGER.info(
                "legacy stanza for type %r already in %s/; skipping migration",
                engine_type,
                target_dir.name,
            )
            skipped += 1
            continue
        filename = _unique_filename(target_dir, engine_type, written)
        out_path = target_dir / filename
        out_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        written.add(filename)
        LOGGER.info("migrated legacy engine stanza %r -> %s", engine_type, out_path)
        migrated += 1

    archived = legacy.with_suffix(legacy.suffix + ".migrated")
    try:
        legacy.rename(archived)
        LOGGER.info(
            "archived %s -> %s (migrated=%d, skipped=%d)",
            legacy.name,
            archived.name,
            migrated,
            skipped,
        )
    except OSError as exc:
        LOGGER.warning("could not archive legacy %s: %s", legacy, exc)


def _migrate_legacy_factory_file(legacy: Path, target_dir: Path) -> None:
    """Same migration shape, but for `engines.factory.json`."""
    try:
        raw = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("failed to read legacy factory file %s: %s", legacy, exc)
        return
    specs = raw.get("engines", [])
    if not isinstance(specs, list):
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        engine_type = spec.get("type") or "engine"
        filename = _unique_filename(target_dir, engine_type, written)
        (target_dir / filename).write_text(
            json.dumps(spec, indent=2) + "\n", encoding="utf-8"
        )
        written.add(filename)

    archived = legacy.with_suffix(legacy.suffix + ".migrated")
    try:
        legacy.rename(archived)
    except OSError as exc:
        LOGGER.warning("could not archive legacy factory %s: %s", legacy, exc)


def _unique_filename(target_dir: Path, base: str, written: set[str]) -> str:
    """Pick `<base>.json` if free, else `<base>-<n>.json`."""
    primary = f"{base}.json"
    if primary not in written and not (target_dir / primary).exists():
        return primary
    n = 2
    while True:
        candidate = f"{base}-{n}.json"
        if candidate not in written and not (target_dir / candidate).exists():
            return candidate
        n += 1


def _load_user_dir(user_dir: Path) -> list[dict]:
    """Load and validate user engine stanzas, enforcing one-per-type."""
    by_type: dict[str, tuple[str, dict]] = {}  # type -> (filename, spec)
    for json_path in sorted(user_dir.glob("*.json")):
        try:
            spec = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.error("failed to read engine config %s: %s", json_path, exc)
            continue
        if not isinstance(spec, dict):
            LOGGER.warning("engine config %s is not an object; skipping", json_path)
            continue
        engine_type = spec.get("type")
        if not engine_type:
            LOGGER.warning("engine config %s has no 'type' field; skipping", json_path)
            continue
        if engine_type in by_type:
            existing = by_type[engine_type][0]
            LOGGER.warning(
                "duplicate engine type %r in %s and %s; keeping %s",
                engine_type,
                existing,
                json_path.name,
                existing,
            )
            continue
        by_type[engine_type] = (json_path.name, spec)
    return [spec for _, spec in by_type.values()]


def _load_factory(parent: Path) -> list[dict]:
    """Read factory engine stanzas. Returns [] if neither dir nor legacy file exists."""
    factory_dir = parent / _FACTORY_DIR_NAME
    if factory_dir.is_dir():
        specs: list[dict] = []
        for json_path in sorted(factory_dir.glob("*.json")):
            try:
                spec = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                LOGGER.warning("failed to read factory %s: %s", json_path, exc)
                continue
            if isinstance(spec, dict):
                specs.append(spec)
        return specs

    # Legacy factory file (already migrated by the time we get here in normal
    # flow; this branch only hits if the user manually pointed at a non-default
    # parent dir). Read it directly without migrating.
    legacy = parent / _LEGACY_FACTORY_FILE
    if legacy.is_file():
        try:
            raw = json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("failed to read legacy factory %s: %s", legacy, exc)
            return []
        specs = raw.get("engines", [])
        return [s for s in specs if isinstance(s, dict)]

    return []
