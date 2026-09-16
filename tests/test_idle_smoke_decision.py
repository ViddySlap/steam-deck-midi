"""P0(f): idle_smoke.py's pass/fail/INVALID decision, with fixed inputs.

idle_smoke.py itself is NOT in `unittest discover`: it boots a real bridge and
idles 30 s per arm. Its DECISION is pure, so it is unit-tested here, and its
load-rule classifiers are tested against fixed process tables so a detector
change cannot quietly void or validate arms.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1] / "scripts" / "showready"


def _load():
    spec = importlib.util.spec_from_file_location("idle_smoke_under_test", KIT / "idle_smoke.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.smoke = _load()
        self.addCleanup(sys.modules.pop, "idle_smoke_under_test", None)

    def test_declared_thresholds_are_the_ones_the_master_named(self):
        self.assertEqual(self.smoke.MAX_CPU_PERCENT_OF_ONE_CORE, 5.0)
        self.assertEqual(self.smoke.MAX_EXIT_SECONDS, 5.0)
        self.assertEqual(self.smoke.IDLE_SECONDS, 30.0)

    def test_a_quiet_clean_arm_passes(self):
        self.assertEqual(
            self.smoke.verdict_for(0.3, 0.1, [], True, []), "PASS")

    def test_cpu_over_the_bar_fails(self):
        self.assertEqual(self.smoke.verdict_for(94.3, 0.1, [], True, []), "FAIL")
        self.assertEqual(self.smoke.verdict_for(5.01, 0.1, [], True, []), "FAIL")

    def test_exactly_at_the_bar_passes(self):
        self.assertEqual(self.smoke.verdict_for(5.0, 5.0, [], True, []), "PASS")

    def test_a_slow_exit_fails(self):
        self.assertEqual(self.smoke.verdict_for(0.3, 15.005, [], True, []), "FAIL")

    def test_a_new_crash_report_fails(self):
        self.assertEqual(
            self.smoke.verdict_for(0.3, 0.1, ["python-2026-09-15.ips"], True, []), "FAIL")

    def test_a_failed_preflight_is_invalid_not_a_fail(self):
        """A bad measuring environment is never evidence about the product."""
        self.assertEqual(self.smoke.verdict_for(94.3, 0.1, [], False, []), "INVALID")
        self.assertEqual(self.smoke.verdict_for(0.3, 0.1, [], False, []), "INVALID")

    def test_a_sampler_breach_is_invalid_not_a_fail(self):
        self.assertEqual(
            self.smoke.verdict_for(0.3, 0.1, [], True, [{"load1": 7.2}]), "INVALID")
        self.assertEqual(
            self.smoke.verdict_for(94.3, 0.1, [], True, [{"load1": 7.2}]), "INVALID")

    def test_an_unmeasured_arm_is_invalid(self):
        self.assertEqual(self.smoke.verdict_for(None, 0.1, [], True, []), "INVALID")
        self.assertEqual(self.smoke.verdict_for(0.3, None, [], True, []), "INVALID")


class ForeignLineClassifierTests(unittest.TestCase):
    """MASTER 13 19:42: consumption not presence; executable + first script arg."""

    def setUp(self):
        self.smoke = _load()
        self.addCleanup(sys.modules.pop, "idle_smoke_under_test", None)

    def _classify(self, rows):
        with patch.object(self.smoke, "_ps_rows", return_value=rows):
            return self.smoke.foreign_lines(set())

    def row(self, pid, pcpu, command):
        return {"pid": pid, "pcpu": pcpu, "command": command}

    def test_an_idle_local_llm_process_is_recorded_not_counted(self):
        foreign, infra, recorded = self._classify([self.row(
            1, 0.0,
            "node /Users/viddyslap/Documents/project-workspaces/local-LLM-deepseek/"
            "qwen-bench/../sandbox/model-proxy.mjs x")])
        self.assertEqual(foreign, [])
        self.assertEqual(len(recorded), 1)

    def test_a_busy_local_llm_process_is_counted(self):
        foreign, _, _ = self._classify([self.row(
            1, 42.0,
            "node /Users/viddyslap/Documents/project-workspaces/local-LLM-deepseek/"
            "qwen-bench/../sandbox/model-proxy.mjs x")])
        self.assertEqual(len(foreign), 1)

    def test_a_bench_driver_is_counted_even_at_zero_cpu(self):
        for script in ("drive-iteration.mjs", "run2.sh", "run-watcher.mjs"):
            with self.subTest(script=script):
                foreign, _, _ = self._classify([self.row(
                    1, 0.0,
                    "node /Users/viddyslap/Documents/project-workspaces/local-LLM-deepseek/"
                    f"qwen-bench/{script} x")])
                self.assertEqual(len(foreign), 1, script)

    def test_the_presence_clause_still_counts_at_zero_cpu(self):
        foreign, _, _ = self._classify([self.row(
            1, 0.0,
            "zsh /Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/"
            "tests/something.sh")])
        self.assertEqual(len(foreign), 1)
        self.assertIn("presence", foreign[0]["counted_because"])

    def test_run_all_sh_counts_at_zero_cpu(self):
        foreign, _, _ = self._classify([self.row(1, 0.0, "zsh /somewhere/run-all.sh")])
        self.assertEqual(len(foreign), 1)

    def test_a_claude_session_with_a_local_llm_add_dir_is_not_foreign(self):
        """The detector bug this rule was corrected for: matching the WHOLE
        command line classed an agent session as foreign load."""
        foreign, _, recorded = self._classify([self.row(
            1, 1.5,
            "/Users/viddyslap/.local/bin/claude --model claude-opus-5 --add-dir "
            "/Users/viddyslap/Documents/project-workspaces/local-LLM-engine")])
        self.assertEqual(foreign, [])
        self.assertEqual(recorded, [])

    def test_the_lane_engine_is_infrastructure_never_foreign(self):
        for pcpu in (0.1, 7.7, 36.6, 90.0):
            with self.subTest(pcpu=pcpu):
                foreign, infra, _ = self._classify([self.row(
                    1, pcpu,
                    "/opt/homebrew/bin/node /Users/viddyslap/Documents/project-workspaces/"
                    "local-LLM-engine/engine/server.mjs --port 8899")])
                self.assertEqual(foreign, [])
                self.assertEqual(len(infra), 1)

    def test_a_harness_advancer_is_infrastructure_too(self):
        foreign, infra, _ = self._classify([self.row(
            1, 40.0,
            "/opt/homebrew/bin/node /Users/viddyslap/Documents/project-workspaces/"
            "local-LLM-engine/engine/advance.mjs")])
        self.assertEqual(foreign, [])
        self.assertEqual(len(infra), 1)

    def test_codex_exec_is_excluded(self):
        foreign, _, recorded = self._classify([self.row(
            1, 80.0,
            "codex exec /Users/viddyslap/Documents/project-workspaces/local-LLM-deepseek/x.mjs")])
        self.assertEqual(foreign, [])
        self.assertEqual(recorded, [])

    def test_an_ordinary_process_is_never_flagged(self):
        foreign, infra, recorded = self._classify([
            self.row(1, 99.0, "/usr/libexec/WindowServer"),
            self.row(2, 50.0, "/Applications/Firefox.app/Contents/MacOS/firefox"),
        ])
        self.assertEqual((foreign, infra, recorded), ([], [], []))


class LoopbackScanTests(unittest.TestCase):
    """The ENGINES-ON RULE: no packet may reach Ben's Resolume network."""

    def setUp(self):
        self.smoke = _load()
        self.addCleanup(sys.modules.pop, "idle_smoke_under_test", None)

    def test_factory_configs_are_rewritten_to_loopback_and_scan_clean(self):
        import tempfile

        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "engines"
            info = self.smoke.build_engine_scratch(repo / "config/engines.factory", dest)
            self.assertGreater(info["files"], 0)
            # The factory configs really do carry Ben's camera addresses.
            self.assertGreater(info["addresses_rewritten"], 0)
            self.assertEqual(self.smoke.scan_for_non_loopback(dest), [])

    def test_the_scanner_fires_on_a_planted_non_loopback_target(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "planted.json").write_text(
                json.dumps({"cameras": {"1": "192.168.0.203"}}), encoding="utf-8")
            hits = self.smoke.scan_for_non_loopback(dest)
            self.assertEqual(len(hits), 1)
            self.assertIn("192.168.0.203", hits[0])

    def test_the_factory_source_is_what_makes_the_control_meaningful(self):
        repo = Path(__file__).resolve().parents[1]
        text = (repo / "config/engines.factory/ptz_visca.json").read_text(encoding="utf-8")
        self.assertIn("192.168.0.", text,
                      "if the factory config no longer points off-loopback, the "
                      "rewrite+scan control is testing nothing")


class PortSafetyTests(unittest.TestCase):
    def setUp(self):
        self.smoke = _load()
        self.addCleanup(sys.modules.pop, "idle_smoke_under_test", None)

    def test_the_installed_tray_ports_are_refused(self):
        self.assertEqual(self.smoke.FORBIDDEN_PORTS, {45123, 7723})

    def test_free_port_never_returns_a_forbidden_port(self):
        for _ in range(25):
            self.assertNotIn(self.smoke.free_port(), self.smoke.FORBIDDEN_PORTS)

    def test_the_instrument_never_names_tray_mode(self):
        source = (KIT / "idle_smoke.py").read_text(encoding="utf-8")
        self.assertNotIn('"--tray"', source.replace('assert "--tray" not in argv', ""))


if __name__ == "__main__":
    unittest.main()
