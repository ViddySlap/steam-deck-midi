"""Tests for StageFlowBridgeEngine."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from tests._engine_helpers import FakeRestClient, RecordingMidiOut
from windows.engines.registry import EngineRegistry
from windows.engines.stageflow_bridge import (
    StageFlowBridgeEngine,
    parse_stageflow_altnames,
)


# Minimal .avc XML covering the structure documented in
# wiki/research/stageflow-altname-storage.md. Two StageFlow instances:
# one in Group #1 (VIDEO) and one in Layer #1.
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
    <Layer name="Layer" uniqueId="l2">
      <Params><Param name="Name" T="STRING" value="LAYER 2"/></Params>
      <RenderPass name="StageFlow" type="DryWetEffect" uniqueTypeId="HV16">
        <Params><Param name="Bypassed" altName="Bypass" T="BOOL"/></Params>
        <RenderPass name="StageFlow" type="FFGLEffect" uniqueTypeId="HV16">
          <Params>
            <ParamRange name="Look 1" T="DOUBLE" value="0"/>
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
            # Group #1 should have Look 1 + Look 2 named.
            self.assertIn(("group", 1), results)
            self.assertEqual(
                results[("group", 1)]["Look 1"], "1-FULL SCREEN"
            )
            self.assertEqual(
                results[("group", 1)]["Look 2"], "2-EACH SECTION"
            )
            # Look 3 has no altName -> empty string.
            self.assertEqual(results[("group", 1)]["Look 3"], "")
            # Layer #1 has Look 2 named.
            self.assertIn(("layer", 1), results)
            self.assertEqual(
                results[("layer", 1)]["Look 2"], "2-EACH SECTION"
            )
            # Layer #2 has Look 1 with no altName.
            self.assertIn(("layer", 2), results)
            self.assertEqual(results[("layer", 2)]["Look 1"], "")
        finally:
            path.unlink()

    def test_parse_missing_file_raises(self) -> None:
        with self.assertRaises((OSError, FileNotFoundError)):
            parse_stageflow_altnames(Path("/nonexistent.avc"))

    def test_parse_truncated_xml_does_not_crash(self) -> None:
        path = _write_avc(SAMPLE_AVC[: len(SAMPLE_AVC) // 2])
        try:
            results = parse_stageflow_altnames(path)
            # We expect partial results — at least the first Group #1 block parses.
            self.assertIsInstance(results, dict)
        finally:
            path.unlink()


def _comp_with_stageflow_bridge(
    *,
    look_count: int = 6,
) -> dict:
    """Build a Resolume comp where the STAGEFLOW BRIDGE Wire patch's
    String Ins are exposed as params keyed by display name like
    'GROUP VIDEO LOOK 1 NAME'.
    """
    rows = ["GROUP VIDEO", "LAYER 1", "LAYER 2", "LAYER 3", "LAYER 4", "LOGO 1", "LOGO 2"]
    params = {}
    pid = 1
    for row in rows:
        for n in range(1, look_count + 1):
            params[f"{row} LOOK {n} NAME"] = {
                "id": pid,
                "value": f"LOOK {n}",
            }
            pid += 1
    return {
        "layers": [],
        "video": {
            "effects": [
                {"name": {"value": "STAGEFLOW BRIDGE"}, "params": params}
            ]
        },
    }


def _build_engine(
    *,
    comp: dict | None = None,
    avc_text: str = SAMPLE_AVC,
    overrides: dict | None = None,
) -> tuple[StageFlowBridgeEngine, FakeRestClient, Path]:
    avc_path = _write_avc(avc_text)
    cfg = {
        "name": "SF",
        "type": "stageflow_bridge",
        "inputs": {"channel": 14, "cc_rescan": 91},
        "comp_path": str(avc_path),
        "wire_effect_name": "STAGEFLOW BRIDGE",
        "look_count": 6,
        "initial_rescan_delay_seconds": 0.0,
        "strip_numeric_prefix": True,
    }
    if overrides:
        cfg.update(overrides)
    rest = FakeRestClient(composition=comp or _comp_with_stageflow_bridge())
    midi = RecordingMidiOut()
    engine = StageFlowBridgeEngine("SF", cfg, midi, rest_client=rest)
    return engine, rest, avc_path


class StageFlowBridgeRescanTests(unittest.TestCase):
    def test_rescan_writes_altnames_to_param_ids(self) -> None:
        engine, rest, avc_path = _build_engine()
        try:
            ok = engine.trigger_rescan()
            self.assertTrue(ok)
            # Group #1 row → groupvideo. Look 1 = "FULL SCREEN" (prefix stripped).
            # The matching pid for GROUP VIDEO LOOK 1 NAME is 1 (first param built).
            self.assertIn((1, "FULL SCREEN"), rest.put_calls)
            # Look 2 = "EACH SECTION".
            self.assertIn((2, "EACH SECTION"), rest.put_calls)
            # Look 3 has no altName -> default LOOK 3.
            self.assertIn((3, "LOOK 3"), rest.put_calls)
        finally:
            avc_path.unlink()

    def test_rescan_uses_default_label_when_altname_missing(self) -> None:
        engine, rest, avc_path = _build_engine()
        try:
            engine.trigger_rescan()
            # Look 4-6 in Group #1 not present in altname dict — should default.
            self.assertIn((4, "LOOK 4"), rest.put_calls)
            self.assertIn((5, "LOOK 5"), rest.put_calls)
            self.assertIn((6, "LOOK 6"), rest.put_calls)
        finally:
            avc_path.unlink()

    def test_rescan_records_writes_count(self) -> None:
        engine, _, avc_path = _build_engine()
        try:
            engine.trigger_rescan()
            # 7 rows × 6 looks = 42 — but only the rows present in altnames
            # contribute: group/1 (6), layer/1 (6), layer/2 (6) = 18.
            # The bridge writes for every (row_slug, look_n) pair where the
            # row exists in altnames AND the param id is known. So:
            # group/1 row: 6 looks (3 named + 3 default), layer/1: 6, layer/2: 6.
            self.assertEqual(engine._last_rescan_writes, 18)
        finally:
            avc_path.unlink()

    def test_strip_numeric_prefix_optional(self) -> None:
        engine, rest, avc_path = _build_engine(
            overrides={"strip_numeric_prefix": False}
        )
        try:
            engine.trigger_rescan()
            self.assertIn((1, "1-FULL SCREEN"), rest.put_calls)
        finally:
            avc_path.unlink()


class StageFlowBridgeMidiTests(unittest.TestCase):
    def test_rising_cc_triggers_rescan(self) -> None:
        engine, rest, avc_path = _build_engine()
        try:
            engine.on_midi_in(14, 91, 0, now=0.0)
            engine.on_midi_in(14, 91, 127, now=0.05)
            self.assertGreater(len(rest.put_calls), 0)
            self.assertEqual(engine._rescan_count, 1)
        finally:
            avc_path.unlink()

    def test_held_cc_does_not_re_rescan(self) -> None:
        engine, _, avc_path = _build_engine()
        try:
            engine.on_midi_in(14, 91, 127, now=0.0)
            engine.on_midi_in(14, 91, 127, now=0.05)
            self.assertEqual(engine._rescan_count, 1)
        finally:
            avc_path.unlink()

    def test_wrong_channel_or_cc_ignored(self) -> None:
        engine, _, avc_path = _build_engine()
        try:
            engine.on_midi_in(0, 91, 127, now=0.0)
            engine.on_midi_in(14, 99, 127, now=0.0)
            self.assertEqual(engine._rescan_count, 0)
        finally:
            avc_path.unlink()


class StageFlowBridgeFailureModeTests(unittest.TestCase):
    def test_missing_avc_logs_error_and_returns_false(self) -> None:
        cfg = {
            "name": "SF",
            "type": "stageflow_bridge",
            "comp_path": "/nonexistent.avc",
        }
        rest = FakeRestClient(composition=_comp_with_stageflow_bridge())
        midi = RecordingMidiOut()
        engine = StageFlowBridgeEngine("SF", cfg, midi, rest_client=rest)
        ok = engine.trigger_rescan()
        self.assertFalse(ok)
        self.assertIsNotNone(engine._last_rescan_error)

    def test_missing_wire_patch_returns_false(self) -> None:
        # Comp tree without the STAGEFLOW BRIDGE effect.
        comp = {"layers": [], "video": {"effects": []}}
        engine, _, avc_path = _build_engine(comp=comp)
        try:
            ok = engine.trigger_rescan()
            self.assertFalse(ok)
            self.assertIsNotNone(engine._last_rescan_error)
        finally:
            avc_path.unlink()

    def test_rest_failure_during_param_discovery_does_not_crash(self) -> None:
        engine, rest, avc_path = _build_engine()
        try:
            rest._fail_get = True  # noqa: SLF001 - test fixture
            ok = engine.trigger_rescan()
            self.assertFalse(ok)
        finally:
            avc_path.unlink()


class StageFlowBridgeInitialRescanTests(unittest.TestCase):
    """Initial rescan is now a one-shot threading.Timer scheduled in
    `bind_registry`, not a periodic tick. Per the 2026-05-11 EVENING
    "no REST after engine init unless user-triggered" rule.
    """

    def test_engine_does_not_request_periodic_tick(self) -> None:
        engine, _, avc_path = _build_engine()
        try:
            # Periodic tick polling was the pre-rewrite mechanism; gone.
            self.assertIsNone(engine.tick_interval_seconds())
        finally:
            avc_path.unlink()

    def test_bind_registry_schedules_one_shot_initial_rescan(self) -> None:
        engine, rest, avc_path = _build_engine()
        try:
            registry = EngineRegistry([engine])
            engine.bind_registry(registry)
            # 0.0s delay -> Timer fires near-immediately. Wait for the
            # rescan to actually complete (rescan_count is incremented
            # at the start of _do_rescan, so wait for it to be set).
            for _ in range(100):
                if engine._rescan_count >= 1 and rest.put_calls:
                    break
                time.sleep(0.02)
            engine.shutdown()  # cancel any leftover timer
            self.assertTrue(engine._initial_rescan_done)
            self.assertEqual(engine._rescan_count, 1)
            self.assertGreater(len(rest.put_calls), 0)
        finally:
            avc_path.unlink()

    def test_initial_rescan_runs_only_once(self) -> None:
        engine, _, avc_path = _build_engine()
        try:
            # Direct call to the inner method twice — second call is a no-op.
            engine._run_initial_rescan()
            count_after_first = engine._rescan_count
            engine._run_initial_rescan()
            self.assertEqual(engine._rescan_count, count_after_first)
        finally:
            avc_path.unlink()

    def test_shutdown_cancels_pending_timer(self) -> None:
        engine, _, avc_path = _build_engine(
            overrides={"initial_rescan_delay_seconds": 60.0}
        )
        try:
            registry = EngineRegistry([engine])
            engine.bind_registry(registry)
            self.assertIsNotNone(engine._initial_rescan_timer)
            engine.shutdown()
            # Give the cancel a moment to take effect.
            time.sleep(0.05)
            # Most importantly: the rescan never fired.
            self.assertFalse(engine._initial_rescan_done)
            self.assertEqual(engine._rescan_count, 0)
        finally:
            avc_path.unlink()


class StageFlowBridgeRefreshTests(unittest.TestCase):
    """`refresh()` re-runs a rescan on demand (POST /api/engines/refresh)."""

    def test_refresh_triggers_rescan(self) -> None:
        engine, rest, avc_path = _build_engine()
        try:
            count_before = engine._rescan_count
            engine.refresh()
            self.assertEqual(engine._rescan_count, count_before + 1)
            self.assertGreater(len(rest.put_calls), 0)
        finally:
            avc_path.unlink()


class StageFlowBridgeStatusTests(unittest.TestCase):
    def test_status_reports_state(self) -> None:
        engine, _, avc_path = _build_engine()
        try:
            engine.trigger_rescan()
            status = engine.status()
            self.assertEqual(status["param_ids_known"], 42)
            self.assertEqual(status["rescan_count"], 1)
            self.assertEqual(status["last_rescan_writes"], 18)
        finally:
            avc_path.unlink()


if __name__ == "__main__":
    unittest.main()
