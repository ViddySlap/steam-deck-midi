"""Engine loading + registry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from windows.engines.audio_opacity import AudioOpacityEngine
from windows.engines.base import Engine
from windows.engines.osc_sync import OscSyncEngine
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

_ENGINE_TYPES: dict[str, type[Engine]] = {
    AudioOpacityEngine.type_name: AudioOpacityEngine,
    OscSyncEngine.type_name: OscSyncEngine,
}

_USER_DIR_NAME = "engines"
_FACTORY_DIR_NAME = "engines.factory"
_LEGACY_USER_FILE = "engines.json"
_LEGACY_FACTORY_FILE = "engines.factory.json"


class EngineRegistry:
    """Holds active engines, dispatches MIDI feedback + ticks."""

    def __init__(self, engines: Iterable[Engine] = ()) -> None:
        self._engines: list[Engine] = list(engines)

    @property
    def engines(self) -> list[Engine]:
        return list(self._engines)

    def add(self, engine: Engine) -> None:
        self._engines.append(engine)

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        for engine in self._engines:
            try:
                engine.on_midi_in(channel, cc, value, now)
            except Exception:
                LOGGER.exception("engine %s on_midi_in failed", engine.name)

    def tick(self, now: float) -> None:
        for engine in self._engines:
            try:
                engine.tick(now)
            except Exception:
                LOGGER.exception("engine %s tick failed", engine.name)

    def shortest_tick_interval(self) -> float | None:
        intervals = [
            engine.tick_interval_seconds()
            for engine in self._engines
            if engine.tick_interval_seconds() is not None
        ]
        return min(intervals) if intervals else None

    def shutdown(self) -> None:
        for engine in self._engines:
            try:
                engine.shutdown()
            except Exception:
                LOGGER.exception("engine %s shutdown failed", engine.name)

    def status(self) -> list[dict]:
        return [engine.status() for engine in self._engines]


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

    engines: list[Engine] = []
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
            engines.append(engine)
            LOGGER.info("loaded engine %s (type=%s)", name, engine_type)
        except Exception:
            LOGGER.exception("failed to instantiate engine %s", name)

    return EngineRegistry(engines)


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
