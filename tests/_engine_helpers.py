"""Shared fakes and fixtures for the v0.4.3 bridge engine tests.

The 6 V-C-B engines all want a fake REST client (so they can resolve
param IDs against a stubbed comp tree) and a fake OSC client (for
engines that emit OSC writes). This module centralises those fakes
plus a comp-tree builder helper that mirrors Resolume's REST shape.
"""

from __future__ import annotations

from typing import Any

from windows.engines.resolume_rest import ResolumeRestError
from windows.midi import DryRunMidiOut


class RecordingMidiOut(DryRunMidiOut):
    def __init__(self) -> None:
        super().__init__(selected_port_name="recording")
        self.events: list[tuple[str, int, int, int]] = []

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.events.append(("cc", channel, control, value))

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.events.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.events.append(("note_off", channel, note, velocity))


class FakeRestClient:
    def __init__(
        self,
        composition: dict | None = None,
        *,
        fail_get: bool = False,
    ) -> None:
        self._composition = composition or {}
        self._fail_get = fail_get
        self.put_calls: list[tuple[int, Any]] = []
        self.get_calls = 0

    def set_composition(self, composition: dict) -> None:
        self._composition = composition

    def get_composition(self) -> dict:
        self.get_calls += 1
        if self._fail_get:
            raise ResolumeRestError("simulated GET failure")
        return self._composition

    def get_parameter(self, param_id: int) -> dict:
        return {"id": param_id, "value": 0.0}

    def put_parameter(self, param_id: int, value: Any) -> None:
        self.put_calls.append((param_id, value))


class FakeOscClient:
    def __init__(self) -> None:
        self.sends: list[tuple[str, Any]] = []
        self.closed = False

    def send(self, address: str, value: Any) -> None:
        self.sends.append((address, value))

    def send_color(self, address: str, hex_value: str) -> None:
        # Record as a regular send with the hex string value so tests can
        # assert on color writes the same way they assert on other sends.
        self.sends.append((address, hex_value))

    def close(self) -> None:
        self.closed = True


def build_param_node(param_id: int, value: Any = 0.0) -> dict:
    """Build a Resolume-style param leaf node."""
    return {"id": param_id, "value": value, "valuerange": {"min": 0, "max": 1}}


def build_layer_with_effect(
    *,
    effect_name: str,
    params: dict[str, dict],
) -> dict:
    """Build a Resolume-style layer dict with a single named effect."""
    return {
        "effects": [
            {
                "name": {"value": effect_name},
                "params": params,
            }
        ]
    }


def build_video_with_effect(
    *,
    effect_name: str,
    params: dict[str, dict],
) -> dict:
    return {
        "effects": [
            {
                "name": {"value": effect_name},
                "params": params,
            }
        ]
    }


def build_comp(
    *,
    layers: list[dict] | None = None,
    video_effects: list[dict] | None = None,
) -> dict:
    """Build a composition tree shaped like Resolume's REST output."""
    return {
        "layers": layers or [],
        "video": {"effects": video_effects or []},
    }
