"""Bridge-side automation engines (v0.3.0+).

An engine listens to one or more input signals (MIDI CCs from Resolume via the
feedback port, REST API polls, etc.) and drives output side effects (MIDI CCs
back to Resolume, REST API writes, etc.). Engines run inside the receiver event
loop alongside the existing mapping dispatcher.
"""

from windows.engines.base import Engine
from windows.engines.registry import EngineRegistry, load_engines

__all__ = ["Engine", "EngineRegistry", "load_engines"]
