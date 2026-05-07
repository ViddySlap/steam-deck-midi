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

    Missing config file → empty registry (engines are opt-in).

    **Factory-default merge (added v0.3.3):** if a sibling `engines.factory.json`
    exists, it ships the as-installed defaults for THIS bridge version. For
    each engine TYPE present in the factory file but absent from the user's
    `engines.json`, the factory stanza is merged in (in-memory only — the
    user's file on disk is never modified). This auto-picks up new engine
    types on installer upgrade without clobbering user customizations to
    engines they've already configured.
    """
    path = Path(config_path)
    if not path.exists():
        LOGGER.info("no engines config at %s; engine registry is empty", path)
        return EngineRegistry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.error("failed to read engines config %s: %s", path, exc)
        return EngineRegistry()

    user_specs = list(raw.get("engines", []))
    user_types = {
        spec.get("type")
        for spec in user_specs
        if isinstance(spec, dict) and spec.get("type")
    }

    factory_path = path.parent / "engines.factory.json"
    if factory_path.exists():
        try:
            factory_raw = json.loads(factory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("failed to read factory engines config %s: %s", factory_path, exc)
        else:
            for fspec in factory_raw.get("engines", []):
                if not isinstance(fspec, dict):
                    continue
                ftype = fspec.get("type")
                if not ftype or ftype in user_types:
                    continue
                LOGGER.info(
                    "auto-merging factory default for engine type %r (not in %s)",
                    ftype,
                    path.name,
                )
                user_specs.append(fspec)

    engines: list[Engine] = []
    for spec in user_specs:
        if not isinstance(spec, dict):
            continue
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
