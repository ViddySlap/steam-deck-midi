"""Parse Resolume's OSC shortcut preset XML.

The preset (Shortcuts/OSC/<name>.xml) is the source of truth for which
Resolume parameters round-trip values to TouchOSC. The OSC sync engine
needs the subset of bindings where Resolume sends OSC OUT - i.e.
OutputPath.allowedTranslationTypes != "-1".

Parameter type is read from the Shortcut's paramNodeName attribute:

  ParamRange            -> float (wiggle by epsilon)
  RangedParam[bool]     -> bool  (flip-flop)
  ParamChoice[int]      -> int   (bump +/- 1)
  ParamChoice[float]    -> float
  Parameter[std::string]-> string (skipped - no safe wiggle)
  ParamEvent            -> trigger (skipped - no value to wiggle)
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


KIND_FLOAT = "float"
KIND_BOOL = "bool"
KIND_INT = "int"
KIND_STRING = "string"

_PARAM_NODE_TO_KIND = {
    "ParamRange": KIND_FLOAT,
    "RangedParam[bool]": KIND_BOOL,
    "ParamChoice[int]": KIND_INT,
    "ParamChoice[float]": KIND_FLOAT,
    "Parameter[std::string]": KIND_STRING,
}


@dataclass(frozen=True)
class SyncTarget:
    osc_path: str
    kind: str  # one of KIND_FLOAT/KIND_BOOL/KIND_INT/KIND_STRING
    param_node_name: str  # raw XML attribute, kept for debugging


def parse_osc_preset(xml_path: str | Path) -> list[SyncTarget]:
    """Parse an OSC shortcut preset XML and return wigglable targets.

    Includes only Shortcuts where OutputPath.allowedTranslationTypes != "-1"
    (i.e., Resolume actually sends OSC OUT for that binding) and where the
    paramNodeName maps to a wigglable kind. ParamEvent shortcuts are
    skipped (triggers, no value).
    """
    path = Path(xml_path)
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        LOGGER.error("failed to parse OSC preset %s: %s", path, exc)
        return []

    targets: list[SyncTarget] = []
    for shortcut in tree.iter("Shortcut"):
        param_node = shortcut.attrib.get("paramNodeName", "")
        kind = _PARAM_NODE_TO_KIND.get(param_node)
        if kind is None or kind == KIND_STRING:
            continue

        output_enabled = False
        osc_path: str | None = None
        for sp in shortcut.findall("ShortcutPath"):
            if sp.attrib.get("name") == "OutputPath":
                if sp.attrib.get("allowedTranslationTypes", "-1") != "-1":
                    output_enabled = True
                    osc_path = sp.attrib.get("path")
                break

        if not output_enabled or not osc_path:
            continue

        targets.append(SyncTarget(osc_path=osc_path, kind=kind, param_node_name=param_node))

    return targets
