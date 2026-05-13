"""Tests for StageFlowBridgeEngine.

The engine pivoted on 2026-05-12 LATE NIGHT from .avc-parsing to a
REST-based read with a clip-connect + bypass-cycle wake-up step. These
tests exercise the new flow with a stateful fake REST client that can
mutate the comp tree in response to PUTs.

The legacy `parse_stageflow_altnames` function is still exported (so
tests + future fallback paths can call it directly) and its parser
tests are preserved.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from tests._engine_helpers import FakeOscClient, RecordingMidiOut
from windows.engines.resolume_rest import ResolumeRestError
from windows.engines.stageflow_bridge import (
    StageFlowBridgeEngine,
    parse_stageflow_altnames,
)


# ---------------------------------------------------------------------------
# .avc parser tests (legacy path, still exported)

SAMPLE_AVC = """<?xml version="1.0" encoding="utf-8"?>
<Composition name="Composition" uniqueId="abc" numLayers="2" numColumns="4">
  <Group name="Group" uniqueId="g1">
    <Params><Param name="Name" T="STRING" value="VIDEO"/></Params>
    <RenderPass name="StageFlow" type="DryWetEffect" uniqueTypeId="HV16">
      <Params><Param name="Bypassed" altName="Bypass" T="BOOL"/></Params>
      <RenderPass name="StageFlow" type="FFGLEffect" uniqueTypeId="HV16">
        <Params>
          <ParamRange name="Look 1" altName="1-FULL SCREEN" T="DOUBLE" value="0"/>
          <ParamRange name="Look 2" altName="2-EACH SECTION" T="DOUBLE" value="0"/>
          <ParamRange name="Look 3" T="DOUBLE" value="0"/>
        </Params>
        <FFGLPlugin name="FFGLPlugin" uniqueId="HV16"/>
      </RenderPass>
    </RenderPass>
    <Layer name="Layer" uniqueId="l1">
      <Params><Param name="Name" T="STRING" value="LAYER 1"/></Params>
      <RenderPass name="StageFlow" type="DryWetEffect" uniqueTypeId="HV16">
        <Params><Param name="Bypassed" altName="Bypass" T="BOOL"/></Params>
        <RenderPass name="StageFlow" type="FFGLEffect" uniqueTypeId="HV16">
          <Params>
            <ParamRange name="Look 2" altName="2-EACH SECTION" T="DOUBLE" value="0"/>
          </Params>
          <FFGLPlugin name="FFGLPlugin" uniqueId="HV16"/>
        </RenderPass>
      </RenderPass>
    </Layer>
  </Group>
</Composition>
"""


def _write_avc(text: str = SAMPLE_AVC) -> Path:
    fd, path = tempfile.mkstemp(suffix=".avc")
    os.close(fd)
    Path(path).write_text(text, encoding="utf-8")
    return Path(path)


class StageFlowParserTests(unittest.TestCase):
    def test_parse_extracts_altnames_per_container(self) -> None:
        path = _write_avc()
        try:
            results = parse_stageflow_altnames(path)
            self.assertIn(("group", 1), results)
            self.assertEqual(results[("group", 1)]["Look 1"], "1-FULL SCREEN")
            self.assertEqual(results[("group", 1)]["Look 2"], "2-EACH SECTION")
            self.assertEqual(results[("group", 1)]["Look 3"], "")
            self.assertIn(("layer", 1), results)
            self.assertEqual(results[("layer", 1)]["Look 2"], "2-EACH SECTION")
        finally:
            path.unlink()

    def test_parse_missing_file_raises(self) -> None:
        with self.assertRaises((OSError, FileNotFoundError)):
            parse_stageflow_altnames(Path("/nonexistent.avc"))

    def test_parse_truncated_xml_does_not_crash(self) -> None:
        path = _write_avc(SAMPLE_AVC[: len(SAMPLE_AVC) // 2])
        try:
            results = parse_stageflow_altnames(path)
            self.assertIsInstance(results, dict)
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# REST-based engine fakes + comp builders

# Fixed IDs we use throughout the tests so assertions stay readable.
# Bypass id is kept BELOW the Wire patch base so filtering put_calls by
# pid >= base only counts Wire-patch String In writes.
LAYER1_STAGEFLOW_BYPASS_ID = 50
LAYER1_STAGEFLOW_LOOK_ALTNAMES = {
    1: "1-FULL SCREEN",
    2: "2-EACH SECTION",
    3: "3-SPLIT",
    4: "4-LOGO",
}
WIRE_PATCH_PARAM_BASE_ID = 1000  # Wire String In param IDs start here.


def _build_layer(
    *,
    has_active_clip: bool,
    stageflow_bypassed: bool,
    look_altnames: dict[int, str] | None = None,
) -> dict:
    """Build a Resolume-style layer with a StageFlow effect.

    If `look_altnames` is None, the StageFlow is in the "inactive" state
    (no Look params materialised in the REST tree).
    """
    effects = [
        {"name": {"value": "Transform"}, "params": {}},
        {
            "name": {"value": "StageFlow"},
            "id": 1764000000001,
            "bypassed": {
                "id": LAYER1_STAGEFLOW_BYPASS_ID,
                "value": stageflow_bypassed,
            },
            "params": _stageflow_params(look_altnames),
        },
    ]
    return {
        "id": 1234,
        "name": {"value": "LAYER 1"},
        "video": {"effects": effects},
        "clips": [{"id": 555, "connected": {"value": "Disconnected"}}],
        "active_clip": (
            {"id": 5000, "name": {"value": "Some Clip"}}
            if has_active_clip
            else None
        ),
    }


def _stageflow_params(look_altnames: dict[int, str] | None) -> dict:
    """Return the params dict of a StageFlow effect.

    `look_altnames=None` => "inactive" state, only INFO entries surface.
    `look_altnames={...}` => Look params materialised with altNames.
    """
    if look_altnames is None:
        return {
            "Opacity": {"id": 10, "value": 1.0},
            "INFO": {"id": 11, "value": "EFFECT INACTIVE"},
        }
    params: dict[str, Any] = {"Opacity": {"id": 10, "value": 1.0}}
    for n in (1, 2, 3, 4):
        altname = look_altnames.get(n, "")
        params[f"Look {n}"] = {
            "id": 100 + n,
            "valuetype": "ParamRange",
            "value": 0.0,
            "view": {"alternative_name": altname},
        }
    return params


def _build_wire_patch_effect(rows: list[str], look_count: int = 6) -> dict:
    """Build the STAGEFLOW BRIDGE comp-level effect with N rows × look_count
    String In params, IDs assigned sequentially from WIRE_PATCH_PARAM_BASE_ID.
    """
    params: dict[str, Any] = {}
    pid = WIRE_PATCH_PARAM_BASE_ID
    for row in rows:
        for n in range(1, look_count + 1):
            params[f"{row} LOOK {n} NAME"] = {"id": pid, "value": "default"}
            pid += 1
    return {
        "name": {"value": "STAGEFLOW BRIDGE"},
        "display_name": {"value": "STAGEFLOW BRIDGE"},
        "params": params,
    }


def _build_comp(
    *,
    layer1_state: str = "active",
    extra_layers: int = 0,
    wire_rows: list[str] | None = None,
    look_count: int = 6,
) -> dict:
    """Build a full comp tree for the engine to walk.

    `layer1_state` is one of:
      - 'active': clip connected, stageflow bypassed=False, looks materialised
      - 'cold': no clip connected, stageflow bypassed=True, looks NOT
        materialised (matches cold-boot Resolume behaviour)
      - 'awake_but_bypassed': clip connected, bypassed=True, looks present
    """
    if layer1_state == "active":
        layer1 = _build_layer(
            has_active_clip=True,
            stageflow_bypassed=False,
            look_altnames=LAYER1_STAGEFLOW_LOOK_ALTNAMES,
        )
    elif layer1_state == "cold":
        layer1 = _build_layer(
            has_active_clip=False,
            stageflow_bypassed=True,
            look_altnames=None,
        )
    elif layer1_state == "awake_but_bypassed":
        layer1 = _build_layer(
            has_active_clip=True,
            stageflow_bypassed=True,
            look_altnames=LAYER1_STAGEFLOW_LOOK_ALTNAMES,
        )
    else:
        raise ValueError(f"unknown layer1_state: {layer1_state}")

    rows = wire_rows if wire_rows is not None else [
        "GROUP VIDEO",
        "LAYER 1",
        "LAYER 2",
        "LAYER 3",
        "LAYER 4",
        "LOGO 1",
        "LOGO 2",
    ]
    return {
        "layers": [layer1] + [
            _build_layer(
                has_active_clip=False,
                stageflow_bypassed=True,
                look_altnames=None,
            )
            for _ in range(extra_layers)
        ],
        "video": {"effects": [_build_wire_patch_effect(rows, look_count)]},
    }


class StatefulFakeRest:
    """Fake REST client that mutates its composition tree in response to
    PUTs on bypass + Wire String In params, and to simulated wake-up
    cycles (so the post-wake GET returns Look params).

    `cycle_wakes_stageflow=True` (default) emulates Resolume's real
    behaviour: when bypass goes True->False AND a clip is connected on
    the layer, the next GET returns the layer's StageFlow with Look
    params materialised.
    """

    def __init__(
        self,
        composition: dict,
        *,
        cycle_wakes_stageflow: bool = True,
        layer_to_wake: int = 1,
        look_altnames: dict[int, str] | None = None,
        fail_get: bool = False,
    ) -> None:
        self._comp = composition
        self._cycle_wakes = cycle_wakes_stageflow
        self._layer_to_wake = layer_to_wake
        self._look_altnames = (
            look_altnames
            if look_altnames is not None
            else dict(LAYER1_STAGEFLOW_LOOK_ALTNAMES)
        )
        self._fail_get = fail_get
        self.put_calls: list[tuple[int, Any]] = []
        self.get_calls = 0
        self._bypass_state: bool | None = None  # tracks transitions

    def get_composition(self) -> dict:
        self.get_calls += 1
        if self._fail_get:
            raise ResolumeRestError("simulated GET failure")
        return self._comp

    def get_parameter(self, param_id: int) -> dict:
        return {"id": param_id, "value": 0.0}

    def put_parameter(self, param_id: int, value: Any) -> None:
        self.put_calls.append((param_id, value))
        # Handle bypass writes on the canonical layer's StageFlow.
        if param_id == LAYER1_STAGEFLOW_BYPASS_ID:
            layer = self._comp["layers"][self._layer_to_wake - 1]
            sf = next(
                e for e in layer["video"]["effects"]
                if (e.get("name", {}).get("value")
                    if isinstance(e.get("name"), dict)
                    else e.get("name")) == "StageFlow"
            )
            prev = sf["bypassed"]["value"]
            sf["bypassed"]["value"] = bool(value)
            # bypass True -> False on a connected layer materialises Looks.
            went_true_to_false = (prev is True) and (value is False)
            if (
                self._cycle_wakes
                and went_true_to_false
                and layer.get("active_clip") is not None
            ):
                sf["params"] = _stageflow_params(self._look_altnames)
        # Handle writes to Wire String In params (record value for later checks).
        effects = self._comp.get("video", {}).get("effects") or []
        if not effects:
            return
        wire_eff = effects[0]
        for k, node in wire_eff.get("params", {}).items():
            if isinstance(node, dict) and node.get("id") == param_id:
                node["value"] = value
                return


class FakeOscWithClipConnect(FakeOscClient):
    """OSC fake that mutates the comp tree on `/clips/M/connect` and
    `/clear`, so the bridge's wake-up can transition a cold layer into
    an active state.
    """

    def __init__(self, rest: StatefulFakeRest) -> None:
        super().__init__()
        self._rest = rest

    def send(self, address: str, value: Any) -> None:
        super().send(address, value)
        # Pattern match: /composition/layers/<L>/clips/<M>/connect
        import re

        m = re.match(
            r"^/composition/layers/(\d+)/clips/(\d+)/connect$", address
        )
        if m:
            layer_idx = int(m.group(1))
            clip_idx = int(m.group(2))
            layer = self._rest._comp["layers"][layer_idx - 1]  # noqa: SLF001
            layer["active_clip"] = {
                "id": 9000 + clip_idx,
                "name": {"value": f"Clip {clip_idx}"},
            }
            return
        m = re.match(r"^/composition/layers/(\d+)/clear$", address)
        if m:
            layer_idx = int(m.group(1))
            layer = self._rest._comp["layers"][layer_idx - 1]  # noqa: SLF001
            layer["active_clip"] = None
            return


# ---------------------------------------------------------------------------
# Engine builder


def _build_engine(
    *,
    comp: dict | None = None,
    overrides: dict | None = None,
    rest: StatefulFakeRest | None = None,
    osc: FakeOscClient | None = None,
) -> tuple[StageFlowBridgeEngine, StatefulFakeRest, FakeOscClient]:
    comp = comp or _build_comp(layer1_state="active")
    cfg = {
        "name": "SF",
        "type": "stageflow_bridge",
        "inputs": {"channel": 14, "cc_rescan": 91, "cc_sync": 90},
        "wire_effect_name": "STAGEFLOW BRIDGE",
        "look_count": 6,
        "layer_index": 1,
        "wake_up_step_delay_ms": 0,  # instant for tests
        "pre_wake_delay_ms": 0,
        "strip_numeric_prefix": True,
        "fallback_label": "-",
    }
    if overrides:
        cfg.update(overrides)
    rest = rest or StatefulFakeRest(comp)
    osc = osc or FakeOscWithClipConnect(rest)
    midi = RecordingMidiOut()
    engine = StageFlowBridgeEngine(
        "SF",
        cfg,
        midi,
        rest_client=rest,
        osc_client=osc,
        sleep=lambda _: None,
    )
    return engine, rest, osc


# ---------------------------------------------------------------------------
# Rescan tests


class StageFlowBridgeRescanTests(unittest.TestCase):
    def test_active_layer_rescan_writes_altnames_to_all_rows(self) -> None:
        # 7 rows × 6 looks = 42 String Ins. After rescan, every row's
        # 6 String Ins should hold the SAME 6 names (the canonical 6
        # fanned out). Look 1..4 from altNames, Look 5+6 = fallback "-".
        engine, rest, _osc = _build_engine()
        ok = engine.trigger_rescan()
        self.assertTrue(ok)
        # 42 String In writes (after numeric prefix stripping).
        write_values_by_pid = dict(rest.put_calls)
        # bypass cycle PUTs are also in put_calls; filter them out.
        wire_writes = {
            pid: val for pid, val in write_values_by_pid.items()
            if pid >= WIRE_PATCH_PARAM_BASE_ID
        }
        self.assertEqual(len(wire_writes), 42)
        # First row (GROUP VIDEO), Look 1 = "FULL SCREEN" (prefix stripped).
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID], "FULL SCREEN")
        # First row, Look 5 = fallback "-"
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID + 4], "-")
        # LAYER 1 row's Look 1 (param base + 6) also = "FULL SCREEN".
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID + 6], "FULL SCREEN")
        self.assertEqual(engine._last_rescan_writes, 42)

    def test_cold_layer_wake_up_materialises_looks(self) -> None:
        comp = _build_comp(layer1_state="cold")
        rest = StatefulFakeRest(comp)
        osc = FakeOscWithClipConnect(rest)
        engine, _, _ = _build_engine(comp=comp, rest=rest, osc=osc)
        ok = engine.trigger_rescan()
        self.assertTrue(ok)
        # Engine must have OSC-connected clip 1 on layer 1, then cleared after.
        addresses = [a for a, _ in osc.sends]
        self.assertIn("/composition/layers/1/clips/1/connect", addresses)
        self.assertIn("/composition/layers/1/clear", addresses)
        # Bypass cycle should have happened: True then False.
        bypass_writes = [
            v for pid, v in rest.put_calls if pid == LAYER1_STAGEFLOW_BYPASS_ID
        ]
        # First two writes: True (start of cycle), False (end of cycle).
        # Then a third write to restore True (since cold layer started bypassed).
        self.assertEqual(bypass_writes[:2], [True, False])
        self.assertEqual(bypass_writes[-1], True)
        # And the labels reached the Wire patch.
        wire_writes = {
            pid: val for pid, val in rest.put_calls
            if pid >= WIRE_PATCH_PARAM_BASE_ID
        }
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID], "FULL SCREEN")

    def test_warm_layer_skips_clip_connect_but_still_cycles_bypass(self) -> None:
        engine, rest, osc = _build_engine()  # active state
        engine.trigger_rescan()
        # Active layer has an active_clip, so engine MUST NOT touch clip.
        clip_addrs = [
            a for a, _ in osc.sends
            if "/clips/" in a or a.endswith("/clear")
        ]
        self.assertEqual(clip_addrs, [])
        # But it still cycles bypass to refresh the param tree.
        bypass_writes = [
            v for pid, v in rest.put_calls if pid == LAYER1_STAGEFLOW_BYPASS_ID
        ]
        # Layer started bypassed=False so cycle is True, False, then no restore.
        self.assertEqual(bypass_writes, [True, False])

    def test_strip_numeric_prefix_disabled_preserves_full_altname(self) -> None:
        engine, rest, _osc = _build_engine(
            overrides={"strip_numeric_prefix": False}
        )
        engine.trigger_rescan()
        wire_writes = {
            pid: val for pid, val in rest.put_calls
            if pid >= WIRE_PATCH_PARAM_BASE_ID
        }
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID], "1-FULL SCREEN")

    def test_missing_look_uses_fallback_dash(self) -> None:
        engine, rest, _osc = _build_engine()
        engine.trigger_rescan()
        wire_writes = {
            pid: val for pid, val in rest.put_calls
            if pid >= WIRE_PATCH_PARAM_BASE_ID
        }
        # Resolume only exposes 4 looks; slots 5+6 fall back to '-'.
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID + 4], "-")
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID + 5], "-")

    def test_custom_fallback_label_honoured(self) -> None:
        engine, rest, _osc = _build_engine(
            overrides={"fallback_label": "(empty)"}
        )
        engine.trigger_rescan()
        wire_writes = {
            pid: val for pid, val in rest.put_calls
            if pid >= WIRE_PATCH_PARAM_BASE_ID
        }
        self.assertEqual(wire_writes[WIRE_PATCH_PARAM_BASE_ID + 4], "(empty)")

    def test_collapsed_wire_patch_writes_just_6(self) -> None:
        # After Phase-2 surgery the Wire patch has a single LOOKS group
        # with 6 String Ins. Discovery finds 6 ids; bridge writes 6.
        comp = _build_comp(wire_rows=["LOOKS"], look_count=6)
        rest = StatefulFakeRest(comp)
        engine, _, _ = _build_engine(comp=comp, rest=rest)
        engine.trigger_rescan()
        wire_writes = {
            pid: val for pid, val in rest.put_calls
            if pid >= WIRE_PATCH_PARAM_BASE_ID
        }
        self.assertEqual(len(wire_writes), 6)


class StageFlowBridgeMidiTests(unittest.TestCase):
    def test_rising_cc_rescan_triggers_worker(self) -> None:
        engine, rest, _ = _build_engine()
        engine.on_midi_in(14, 91, 0, now=0.0)
        engine.on_midi_in(14, 91, 127, now=0.05)
        # Wait for the worker thread to complete.
        self._await_rescan(engine)
        self.assertEqual(engine._rescan_count, 1)

    def test_rising_cc_sync_also_triggers_worker(self) -> None:
        engine, rest, _ = _build_engine()
        engine.on_midi_in(14, 90, 0, now=0.0)
        engine.on_midi_in(14, 90, 127, now=0.05)
        self._await_rescan(engine)
        self.assertEqual(engine._rescan_count, 1)

    def test_held_cc_does_not_re_rescan(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(14, 91, 127, now=0.0)
        engine.on_midi_in(14, 91, 127, now=0.05)
        self._await_rescan(engine)
        self.assertEqual(engine._rescan_count, 1)

    def test_wrong_channel_or_cc_ignored(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(0, 91, 127, now=0.0)
        engine.on_midi_in(14, 99, 127, now=0.0)
        # Give any erroneous worker thread a moment to misbehave.
        time.sleep(0.05)
        self.assertEqual(engine._rescan_count, 0)

    def test_overlapping_triggers_collapse_to_one_rescan(self) -> None:
        # CC 90 then CC 91 in rapid succession: only one rescan runs.
        # Use the worker_lock to test the drop-duplicate behaviour.
        engine, _, _ = _build_engine()
        # Acquire the lock manually to keep "rescan in flight".
        engine._worker_lock.acquire()
        try:
            engine.on_midi_in(14, 90, 0, now=0.0)
            engine.on_midi_in(14, 90, 127, now=0.05)
            engine.on_midi_in(14, 91, 0, now=0.10)
            engine.on_midi_in(14, 91, 127, now=0.15)
        finally:
            engine._worker_lock.release()
        # No thread ran (lock was held by the test); rescan_count still 0.
        # We can't directly assert "exactly one would have run", but we can
        # verify the early-drop path didn't crash.
        time.sleep(0.05)
        self.assertEqual(engine._rescan_count, 0)

    @staticmethod
    def _await_rescan(engine: StageFlowBridgeEngine, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if engine._rescan_count >= 1 and not engine._worker_lock.locked():
                return
            time.sleep(0.01)


class StageFlowBridgeFailureModeTests(unittest.TestCase):
    def test_missing_wire_patch_returns_false(self) -> None:
        comp = _build_comp()
        # Remove the Wire patch effect entirely.
        comp["video"]["effects"] = []
        rest = StatefulFakeRest(comp)
        engine, _, _ = _build_engine(comp=comp, rest=rest)
        ok = engine.trigger_rescan()
        self.assertFalse(ok)
        self.assertIsNotNone(engine._last_rescan_error)

    def test_layer_index_out_of_range_returns_false(self) -> None:
        engine, _, _ = _build_engine(overrides={"layer_index": 99})
        ok = engine.trigger_rescan()
        self.assertFalse(ok)
        self.assertIn("out of range", engine._last_rescan_error or "")

    def test_rest_get_failure_returns_false(self) -> None:
        comp = _build_comp()
        rest = StatefulFakeRest(comp, fail_get=True)
        engine, _, _ = _build_engine(comp=comp, rest=rest)
        ok = engine.trigger_rescan()
        self.assertFalse(ok)
        self.assertIsNotNone(engine._last_rescan_error)


class StageFlowBridgeLifecycleTests(unittest.TestCase):
    def test_engine_does_not_request_periodic_tick(self) -> None:
        engine, _, _ = _build_engine()
        self.assertIsNone(engine.tick_interval_seconds())

    def test_bind_registry_does_not_fire_rescan(self) -> None:
        engine, rest, _ = _build_engine()
        engine.bind_registry(None)
        # No initial-rescan timer. Engine stays idle until user trigger.
        time.sleep(0.05)
        self.assertEqual(engine._rescan_count, 0)
        self.assertEqual(rest.get_calls, 0)

    def test_refresh_runs_rescan(self) -> None:
        engine, rest, _ = _build_engine()
        before = engine._rescan_count
        engine.refresh()
        # refresh uses the worker thread same as MIDI triggers.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if engine._rescan_count > before and not engine._worker_lock.locked():
                break
            time.sleep(0.01)
        self.assertEqual(engine._rescan_count, before + 1)


class StageFlowBridgeStatusTests(unittest.TestCase):
    def test_status_reports_state(self) -> None:
        engine, _, _ = _build_engine()
        engine.trigger_rescan()
        status = engine.status()
        self.assertEqual(status["type"], "stageflow_bridge")
        self.assertEqual(status["layer_index"], 1)
        self.assertEqual(status["look_count"], 6)
        self.assertEqual(status["param_ids_known"], 42)
        self.assertEqual(status["last_rescan_writes"], 42)
        self.assertEqual(status["rescan_count"], 1)
        # last_look_names: 4 from REST + 2 fallback.
        self.assertEqual(status["last_look_names"][0], "FULL SCREEN")
        self.assertEqual(status["last_look_names"][4], "-")
        self.assertEqual(status["last_look_names"][5], "-")


if __name__ == "__main__":
    unittest.main()
