"""engine_ab.py detectors: a difference goes RED, zero observations go RED, clean goes GREEN.

The end-to-end arms (git archive of v0.4.9 and a candidate) are run by the
commands in scripts/showready/README.md; these tests pin the pure judgement
functions those runs rely on.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "scripts/showready"


def _load():
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("engine_ab_under_test", KIT / "engine_ab.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


engine_ab = _load()

SECTION = {
    "macro_settings": {"macro_delay_ms": 80, "modifier_hold_ms": 2000},
    "mappings": {
        "LEFT_STICK_CLICK_L3": {"type": "note", "channel": 0, "note": 72, "velocity": 127},
        "L_PAD_LEFT": {"type": "note", "channel": 0, "note": 82, "velocity": 127},
        "L_PAD_RIGHT": {"type": "note", "channel": 0, "note": 83, "velocity": 127},
        "L_PAD_LEFT_LONG_PRESS": {"type": "staged_note_macro", "modifier_channel": 0, "trigger_channel": 1,
                                  "note": 86, "velocity": 127},
        "L_PAD_RIGHT_LONG_PRESS": {"type": "staged_note_macro", "modifier_channel": 0, "trigger_channel": 1,
                                   "note": 87, "velocity": 127},
        "L4": {"type": "cc", "channel": 2, "cc": 74, "on_value": 127, "off_value": 0},
    },
}
AUTOPILOT = {"inputs": {"channel": 14, **{
    key: {"cc_enable": base, "cc_beats": base + 1, "cc_transition": base + 2, "cc_mode": base + 3,
          "layer_ccs": {str(n): base + 4 + i for i, n in enumerate(layers)}}
    for key, base, layers in (("video", 60, (1, 2, 3, 4)), ("fx", 70, (5,)), ("logo", 80, (6, 7)))
}}}


def _capture(steps_for_script):
    kinds = {s["i"]: s["kind"] for s in steps_for_script}
    clock_step = next(i for i, k in kinds.items() if k == "clock")
    events = [
        {"step": clock_step, "src": "autopilot", "osc": "/composition/layers/1/master", "value": "1.0"},
        {"step": clock_step, "src": "autopilot", "midi": "90567f"},
        {"step": "load", "src": "global_color", "midi": "be637f"},
        {"step": clock_step, "src": "global_color", "osc": "/x", "value": "'#ff0000ff'"},
        {"step": clock_step, "src": "l_stick_layer", "midi": "bf7640"},
        {"step": clock_step, "src": "gyro_feedback", "midi": "bf7a40"},
        {"step": clock_step, "src": "audio_opacity", "midi": "b06e7f"},
        {"step": clock_step, "src": "receiver", "midi": "90527f"},
    ]
    decisions = [{"step": clock_step, "allowed": False}, {"step": clock_step, "allowed": False},
                 {"step": clock_step, "allowed": True}]
    return {"events": events, "decisions": decisions}


class EngineAbDetectorTests(unittest.TestCase):
    def setUp(self):
        self.script = engine_ab.build_script(SECTION, {"autopilot": True}, AUTOPILOT)
        self.clean = _capture(self.script["steps"])

    def test_script_is_deterministic_and_uses_the_preset_notes(self):
        again = engine_ab.build_script(copy.deepcopy(SECTION), {"autopilot": True}, AUTOPILOT)
        self.assertEqual(engine_ab.canonical(again), engine_ab.canonical(self.script))
        notes = {(s["channel"], s["note"]) for s in self.script["steps"] if s["kind"] == "deck_note_on"}
        self.assertTrue({(0, 82), (0, 83), (0, 86), (1, 86), (0, 87), (0, 72)} <= notes)
        kinds = {s["kind"] for s in self.script["steps"]}
        self.assertEqual(kinds, {"tick", "clock", "feedback_cc", "deck_cc", "deck_note_on", "deck_note_off",
                                 "axis", "refresh"})

    def test_missing_preset_mapping_is_refused(self):
        broken = copy.deepcopy(SECTION)
        del broken["mappings"]["L_PAD_RIGHT_LONG_PRESS"]
        with self.assertRaisesRegex(ValueError, "L_PAD_RIGHT_LONG_PRESS"):
            engine_ab.build_script(broken, {}, AUTOPILOT)

    def test_identical_captures_are_green(self):
        result = engine_ab.compare(self.clean, copy.deepcopy(self.clean))
        self.assertTrue(result["identical_events"])
        self.assertTrue(result["identical_filter_decisions"])
        self.assertEqual(result["different_sources"], [])
        table = engine_ab.coverage_table(self.script, {"A": self.clean, "B": self.clean}, ("A", "B"))
        self.assertEqual([r["engine"] for r in table if not r["covered"]], [])

    def test_one_byte_difference_is_red_and_attributed(self):
        planted = copy.deepcopy(self.clean)
        planted["events"][4]["midi"] = "bf7740"
        result = engine_ab.compare(self.clean, planted)
        self.assertFalse(result["identical_events"])
        self.assertEqual(result["different_sources"], ["l_stick_layer"])
        self.assertEqual(result["first_difference"]["index"], 4)

    def test_missing_trailing_event_is_red(self):
        planted = copy.deepcopy(self.clean)
        planted["events"].pop()
        result = engine_ab.compare(self.clean, planted)
        self.assertFalse(result["identical_events"])
        self.assertEqual(result["first_difference"]["index"], len(planted["events"]))

    def test_filter_decision_difference_is_red(self):
        planted = copy.deepcopy(self.clean)
        planted["decisions"][0]["allowed"] = True
        self.assertFalse(engine_ab.compare(self.clean, planted)["identical_filter_decisions"])

    def test_zero_observations_on_either_arm_is_red(self):
        for engine in engine_ab.ENGINE_TYPES:
            with self.subTest(engine=engine):
                empty = copy.deepcopy(self.clean)
                empty["events"] = [e for e in empty["events"] if e["src"] != engine]
                table = engine_ab.coverage_table(self.script, {"A": self.clean, "B": empty}, ("A", "B"))
                self.assertEqual([r["engine"] for r in table if not r["covered"]], [engine])

    def test_inactive_engine_must_stay_silent_except_load_and_refresh(self):
        script = engine_ab.build_script(SECTION, {"l_stick_layer": False, "global_color": False}, AUTOPILOT)
        silent = copy.deepcopy(self.clean)
        silent["events"] = [e for e in silent["events"] if e["src"] not in ("l_stick_layer",)]
        silent["events"] = [e for e in silent["events"] if not (e["src"] == "global_color" and e["step"] != "load")]
        table = engine_ab.coverage_table(script, {"A": silent}, ("A",))
        self.assertEqual([r["engine"] for r in table if not r["covered"]], [])
        table = engine_ab.coverage_table(script, {"A": self.clean}, ("A",))
        self.assertEqual(sorted(r["engine"] for r in table if not r["covered"]), ["global_color", "l_stick_layer"])

    def test_autopilot_needs_both_a_reemit_and_a_drop(self):
        no_drop = copy.deepcopy(self.clean)
        no_drop["decisions"] = [d for d in no_drop["decisions"] if d["allowed"]] + [{"step": 0, "allowed": False}]
        table = engine_ab.coverage_table(self.script, {"A": no_drop}, ("A",))
        self.assertFalse(next(r for r in table if r["engine"] == "autopilot")["covered"])


if __name__ == "__main__":
    unittest.main()
