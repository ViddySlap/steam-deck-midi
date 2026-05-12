"""Shared helpers for engines that resolve Resolume params by name.

The v0.4.3 V-C-B-driven engines (`bumper_blast`,
`chaser_stack_dispatcher`, `global_color`, `stageflow_bridge`) walk
Resolume's REST composition tree to find
named effects + named params and resolve their numeric IDs for
subsequent PUT calls. This module centralises the slug + lookup logic.

Naming conventions:
- Effect names use UPPERCASE + spaces in Wire dashboards (e.g. "VIDDY-COLOR-BUMP").
- Resolume's slug rule: lowercase + drop non-alphanumerics.
- Param dict keys can be either the display name ("BUMPER BLAST MIN SPEED")
  or the slug ("bumperblastminspeed") depending on whether you read from
  the params dict directly or via OSC paths. We tolerate both via
  `_find_param_id` / `_find_param_value`.
"""

from __future__ import annotations

from typing import Any


def slug(name: str) -> str:
    """Resolume-style slug: lowercased + alphanumerics only."""
    return "".join(ch.lower() for ch in name if ch.isalnum())


def find_effect_params(comp: dict, effect_name: str) -> dict | None:
    """Search comp-level <video><effects> for a named effect; return its params dict."""
    target = slug(effect_name)
    for eff in comp.get("video", {}).get("effects", []) or ():
        if not isinstance(eff, dict):
            continue
        if _effect_slug(eff) == target:
            params = eff.get("params")
            if isinstance(params, dict):
                return params
    return None


def find_layer_effect_params(
    comp: dict, layer_index: int, effect_name: str
) -> dict | None:
    """Find params dict for a named effect on a specific 1-indexed layer.

    Layer video effects live at `layer.video.effects` in Resolume's REST tree.
    """
    layer = _get_layer(comp, layer_index)
    if layer is None:
        return None
    target = slug(effect_name)
    for eff in _layer_video_effects(layer):
        if not isinstance(eff, dict):
            continue
        if _effect_slug(eff) == target:
            params = eff.get("params")
            if isinstance(params, dict):
                return params
    return None


def find_param_id(params: dict, candidates: tuple[str, ...]) -> int | None:
    """Find a param's id by trying each candidate name (display or slug)."""
    for cand in candidates:
        node = params.get(cand)
        if isinstance(node, dict) and "id" in node:
            pid = _coerce_int(node["id"])
            if pid is not None:
                return pid
    target_slugs = {slug(c) for c in candidates}
    for key, node in params.items():
        if not isinstance(node, dict):
            continue
        if slug(str(key)) in target_slugs and "id" in node:
            pid = _coerce_int(node["id"])
            if pid is not None:
                return pid
    return None


def find_param_value(params: dict, candidates: tuple[str, ...]):
    """Find a param's current value by trying each candidate name (display or slug)."""
    for cand in candidates:
        node = params.get(cand)
        if isinstance(node, dict) and "value" in node:
            return node["value"]
    target_slugs = {slug(c) for c in candidates}
    for key, node in params.items():
        if not isinstance(node, dict):
            continue
        if slug(str(key)) in target_slugs and "value" in node:
            return node["value"]
    return None


def find_effect_node(comp: dict, effect_name: str) -> dict | None:
    """Return the comp-level effect node (so callers can read top-level fields)."""
    target = slug(effect_name)
    for eff in comp.get("video", {}).get("effects", []) or ():
        if isinstance(eff, dict) and _effect_slug(eff) == target:
            return eff
    return None


def find_layer_effect_node(
    comp: dict, layer_index: int, effect_name: str
) -> dict | None:
    layer = _get_layer(comp, layer_index)
    if layer is None:
        return None
    target = slug(effect_name)
    for eff in _layer_video_effects(layer):
        if isinstance(eff, dict) and _effect_slug(eff) == target:
            return eff
    return None


def _get_layer(comp: dict, layer_index: int) -> dict | None:
    layers = comp.get("layers") or []
    idx = layer_index - 1
    if idx < 0 or idx >= len(layers):
        return None
    layer = layers[idx]
    return layer if isinstance(layer, dict) else None


def _layer_video_effects(layer: dict) -> list:
    """Return `layer.video.effects` (the live REST shape) with a legacy fallback."""
    video = layer.get("video")
    if isinstance(video, dict):
        effects = video.get("effects")
        if isinstance(effects, list):
            return effects
    legacy = layer.get("effects")
    if isinstance(legacy, list):
        return legacy
    return []


def _effect_slug(eff: dict) -> str:
    """Match against the user's display_name first, falling back to the class name.

    Resolume's REST tree exposes both: `name` is the class identifier (e.g.
    "Color Bump", "Strobe") and `display_name` is what the user has renamed
    the instance to (e.g. "Color Bump WHITE", "OPACITY STROBE"). Two
    sibling effects can share the same `name` and only differ on
    `display_name`, so display name has to take precedence.
    """
    raw_name = _scalar_or_value(eff.get("display_name")) or _scalar_or_value(
        eff.get("name")
    )
    return slug(raw_name) if raw_name else ""


def _scalar_or_value(node) -> str | None:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        v = node.get("value")
        return v if isinstance(v, str) else None
    return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
