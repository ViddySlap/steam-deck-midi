"""Engine loading + registry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from windows.engines.audio_opacity import AudioOpacityEngine
from windows.engines.base import Engine
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

_ENGINE_TYPES: dict[str, type[Engine]] = {
    AudioOpacityEngine.type_name: AudioOpacityEngine,
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

    engines: list[Engine] = []
    for spec in raw.get("engines", []):
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
