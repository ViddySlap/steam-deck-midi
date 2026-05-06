"""Auto-bypass engine.

Polls Resolume layer/group video opacity (or master) values via REST and toggles
the corresponding `bypassed` parameter when opacity stays below a threshold for
a debounce window. Restores when opacity rises back above the threshold for the
same window. Saves real GPU work on layers like FEEDBACK and COMP LEVEL FX when
they are temporarily masked off.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from windows.engines.base import Engine
from windows.engines.resolume_rest import ResolumeRestClient, ResolumeRestError
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)


class AutoBypassEngine(Engine):
    type_name = "auto_bypass"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        rest_client: ResolumeRestClient | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)
        rest_cfg = config.get("rest", {})
        self._rest = rest_client or ResolumeRestClient(
            base_url=rest_cfg.get("base_url", "http://127.0.0.1:8080"),
            timeout=float(rest_cfg.get("timeout_seconds", 1.5)),
        )
        self._poll_hz = float(config.get("poll_hz", 5.0))
        self._threshold = float(config.get("threshold", 0.01))
        self._debounce_ms = int(config.get("debounce_ms", 500))
        self._read_param = config.get("read_param", "master")
        # targets is a list of {kind: layer|group, index: N, label: str}
        self._targets: list[dict] = list(config.get("targets", []))

        self._last_poll = -float("inf")
        # per-target state
        self._state: dict[str, dict] = {
            self._target_key(t): {
                "bypassed": False,
                "below_since": None,
                "above_since": None,
            }
            for t in self._targets
        }

    @staticmethod
    def _target_key(target: dict) -> str:
        return f"{target['kind']}:{target['index']}"

    def tick_interval_seconds(self) -> float:
        return 1.0 / self._poll_hz

    def tick(self, now: float) -> None:
        if (now - self._last_poll) < (1.0 / self._poll_hz):
            return
        self._last_poll = now
        for target in self._targets:
            key = self._target_key(target)
            try:
                value = self._read_value(target)
            except ResolumeRestError as exc:
                LOGGER.debug("auto_bypass read failed for %s: %s", key, exc)
                continue
            self._evaluate(target, value, now)

    def _read_value(self, target: dict) -> float:
        kind = target["kind"]
        index = int(target["index"])
        if kind == "layer":
            data = self._rest.get_layer(index)
        elif kind == "group":
            data = self._rest.get_group(index)
        else:
            raise ResolumeRestError(f"unsupported kind: {kind}")
        param = data.get(self._read_param)
        if isinstance(param, dict) and "value" in param:
            return float(param["value"])
        return 0.0

    def _evaluate(self, target: dict, value: float, now: float) -> None:
        key = self._target_key(target)
        state = self._state[key]
        debounce_seconds = self._debounce_ms / 1000.0
        if value <= self._threshold:
            state["above_since"] = None
            if state["below_since"] is None:
                state["below_since"] = now
            if not state["bypassed"] and (now - state["below_since"]) >= debounce_seconds:
                self._set_bypass(target, True)
                state["bypassed"] = True
        else:
            state["below_since"] = None
            if state["above_since"] is None:
                state["above_since"] = now
            if state["bypassed"] and (now - state["above_since"]) >= debounce_seconds:
                self._set_bypass(target, False)
                state["bypassed"] = False

    def _set_bypass(self, target: dict, bypassed: bool) -> None:
        try:
            if target["kind"] == "layer":
                self._rest.set_layer_bypassed(int(target["index"]), bypassed)
            else:
                self._rest.set_group_bypassed(int(target["index"]), bypassed)
            LOGGER.info(
                "auto_bypass %s %s = %s",
                target.get("label", self._target_key(target)),
                "bypass" if bypassed else "unbypass",
                bypassed,
            )
        except ResolumeRestError as exc:
            LOGGER.warning("auto_bypass set_bypass failed for %s: %s", self._target_key(target), exc)

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "threshold": self._threshold,
            "debounce_ms": self._debounce_ms,
            "targets": [
                {
                    "label": t.get("label", self._target_key(t)),
                    "kind": t["kind"],
                    "index": t["index"],
                    "bypassed": self._state[self._target_key(t)]["bypassed"],
                }
                for t in self._targets
            ],
        }
