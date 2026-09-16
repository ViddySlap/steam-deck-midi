"""P0(f2)/F5: engine_ab.py must not require LOCALAPPDATA.

sdauto AG measured engine_ab.py exiting 1 on the laptop with
`KeyError: 'LOCALAPPDATA'`, which made the Windows engine A/B
UNVERIFIED-BY-EXECUTION. The lookup ran while the argument parser was being
BUILT - before argv was read - so no argument, including an explicit
--scratch, could avoid it. A non-interactive ssh session's environment has no
LOCALAPPDATA.

Reverting `--scratch` to a `default=os.environ["LOCALAPPDATA"]...` expression
turns test_parsing_works_on_windows_without_localappdata RED.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1] / "scripts" / "showready"


def _load_engine_ab():
    """Import scripts/showready/engine_ab.py fresh (it is not a package)."""
    # Never write bytecode into scripts/showready: SHA256SUMS pins the EXACT
    # file set there (tests/test_showready_rail.verify_pins rglobs the kit), so
    # a stray __pycache__ from this import would turn the pin check red - an
    # order-dependent failure that depends on which test ran first.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("engine_ab_under_test", KIT / "engine_ab.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class DefaultScratchDirTests(unittest.TestCase):
    def setUp(self):
        self.engine_ab = _load_engine_ab()
        self.addCleanup(sys.modules.pop, "engine_ab_under_test", None)

    def _no_localappdata(self):
        env = {k: v for k, v in os.environ.items() if k != "LOCALAPPDATA"}
        return patch.dict(os.environ, env, clear=True)

    def test_posix_default_is_unchanged(self):
        self.assertEqual(self.engine_ab.scratch_dir_for({}, "posix"),
                         "/tmp/sdauto-engine-ab")

    def test_default_scratch_dir_is_the_pure_function_on_this_machine(self):
        """Platform-independent: default_scratch_dir() is scratch_dir_for()
        applied to THIS machine, whichever machine is running the suite."""
        self.assertEqual(self.engine_ab.default_scratch_dir(),
                         Path(self.engine_ab.scratch_dir_for(os.environ, os.name)))

    def test_windows_uses_localappdata_when_it_is_there(self):
        # Built from parts: tests/test_resolume_home_defaults.py scans every
        # tracked file outside docs/ and scripts/ for a real Windows user home,
        # so this file must never contain that string literally.
        local = "C:\\Users\\" + "B" + "en" + "\\AppData\\Local"
        result = self.engine_ab.scratch_dir_for({"LOCALAPPDATA": local}, "nt")
        self.assertEqual(result, local + "/Temp/sdwin/engine-ab")

    def test_windows_without_localappdata_falls_back_and_never_raises(self):
        result = self.engine_ab.scratch_dir_for({"TEMP": r"C:\Windows\Temp"}, "nt")
        self.assertEqual(result, r"C:\Windows\Temp/sdwin/engine-ab")
        result = self.engine_ab.scratch_dir_for({"TMP": r"C:\Windows\Temp"}, "nt")
        self.assertEqual(result, r"C:\Windows\Temp/sdwin/engine-ab")

    def test_windows_with_no_environment_at_all_still_yields_a_path(self):
        result = self.engine_ab.scratch_dir_for({}, "nt")
        self.assertTrue(result.endswith("sdwin/engine-ab"), result)
        self.assertTrue(len(result) > len("sdwin/engine-ab"), result)

    def test_an_empty_localappdata_is_not_treated_as_a_directory(self):
        result = self.engine_ab.scratch_dir_for({"LOCALAPPDATA": "", "TEMP": r"C:\T"}, "nt")
        self.assertEqual(result, r"C:\T/sdwin/engine-ab")

    def test_parsing_works_on_windows_without_localappdata(self):
        """The F5 failure exactly: argv was never reached.

        The parser is built and argv parsed with LOCALAPPDATA absent. At BASE
        this raised KeyError during build_parser and exited 1.
        """
        with self._no_localappdata():
            with self.assertRaises(SystemExit) as caught:
                self.engine_ab.main(["--help"])
            self.assertEqual(caught.exception.code, 0)

    def test_an_explicit_scratch_is_honoured_without_localappdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._no_localappdata():
                # --candidate/--preset/--out missing => parser.error => exit 2,
                # but ONLY after --scratch parsed cleanly. A KeyError would be
                # an uncaught exception, not a SystemExit(2).
                with self.assertRaises(SystemExit) as caught:
                    self.engine_ab.main(["--scratch", tmp])
            self.assertEqual(caught.exception.code, 2)

    def test_no_eager_environ_subscript_anywhere_in_the_instrument(self):
        """The SHAPE of the F5 defect, not just the one instance of it.

        AST, not text: the module docstring quotes the old expression on
        purpose, and a grep would match the explanation as if it were the bug.
        """
        import ast

        tree = ast.parse((KIT / "engine_ab.py").read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            value = node.value
            if not (isinstance(value, ast.Attribute) and value.attr == "environ"):
                continue
            key = node.slice
            if isinstance(key, ast.Constant):
                offenders.append((node.lineno, key.value))
        self.assertEqual(
            offenders, [],
            "os.environ[...] raises KeyError when the variable is absent; use "
            f"os.environ.get(...) instead: {offenders}")


class AudioOpacityProtocolTests(unittest.TestCase):
    """P0(f2)/F6: the OSC surface is comparable, and has a sensitivity control."""

    def setUp(self):
        self.engine_ab = _load_engine_ab()
        self.addCleanup(sys.modules.pop, "engine_ab_under_test", None)

    def test_osc_is_the_default_protocol_for_a_run(self):
        """The installed laptop config has no `protocol` key, so the engine's
        own default (osc) is what actually ships, and that is what a bare
        invocation of engine_ab.py now compares."""
        self.assertEqual(self.engine_ab.required_surfaces("audio_opacity", "osc"), ("osc",))
        self.assertEqual(self.engine_ab.required_surfaces("audio_opacity", "midi"), ("midi",))
        # Every other engine is unaffected by the protocol.
        self.assertEqual(self.engine_ab.required_surfaces("autopilot", "osc"),
                         self.engine_ab.REQUIRED["autopilot"])

    def test_a_bare_invocation_compares_the_shipped_surface(self):
        """--audio-opacity-protocol defaults to osc."""
        import subprocess
        import sys as _sys
        out = subprocess.run([_sys.executable, "-B", str(KIT / "engine_ab.py"), "--help"],
                             capture_output=True, text=True).stdout
        self.assertIn("--audio-opacity-protocol", out)
        self.assertIn("Default osc", out)

    def test_the_engine_default_really_is_osc(self):
        """If the product default changed, engine_ab's default must follow."""
        import inspect

        from windows.engines import audio_opacity
        source = inspect.getsource(audio_opacity)
        self.assertIn('str(outputs.get("protocol", "osc")).lower()', source)

    def test_there_is_a_sensitivity_control_on_a_compared_osc_call(self):
        control = self.engine_ab.CONTROLS["sensitivity-audio_opacity-osc"]
        family, rel, old, new = control
        self.assertEqual(family, "audio_opacity")
        self.assertEqual(rel, "windows/engines/audio_opacity.py")
        self.assertIn("_osc.send", old)
        self.assertNotEqual(old, new)

    def test_the_control_anchor_exists_exactly_once_in_the_product(self):
        """A control that cannot be applied is a control that cannot go RED."""
        _, rel, old, new = self.engine_ab.CONTROLS["sensitivity-audio_opacity-osc"]
        source = (Path(__file__).resolve().parents[1] / rel).read_text(encoding="utf-8")
        self.assertEqual(source.count(old), 1, f"anchor not found exactly once in {rel}")
        self.assertEqual(source.count(new), 0, "the perturbed form is already present")

    def test_the_osc_control_edits_an_EMITTING_call_not_a_default(self):
        """PRESENCE IS NOT EFFECT.

        The first version of this control perturbed the default in
        `osc.get("logo_path", ...)`. The anchor existed exactly once, so an
        existence check passed - but config/engines.factory/audio_opacity.json
        SUPPLIES logo_path, so the default was never read and the control
        changed nothing: engine_ab reported identical_events True and the
        control did not fire. A control must edit a call that actually emits.
        """
        _, rel, old, new = self.engine_ab.CONTROLS["sensitivity-audio_opacity-osc"]
        self.assertIn("self._osc.send(", old,
                      "the control must perturb an emitting call, not a config default")
        self.assertNotIn(".get(", old,
                         "a .get() default is inert whenever the config supplies the key")

    def test_no_control_perturbs_a_default_the_factory_config_supplies(self):
        """The SHAPE of that defect, across every control."""
        import json
        import re

        repo = Path(__file__).resolve().parents[1]
        factory = repo / "config/engines.factory"
        for name, (family, rel, old, _new) in self.engine_ab.CONTROLS.items():
            match = re.search(r'\.get\(\s*["\'](\w+)["\']\s*,', old)
            if not match:
                continue
            key = match.group(1)
            path = factory / f"{family}.json"
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(control=name, key=key):
                self.assertNotIn(f'"{key}"', text,
                                 f"{name} perturbs the default for {key!r}, but "
                                 f"{path.name} supplies that key, so the edit is inert")

    def test_every_control_names_a_real_anchor(self):
        for name, (_, rel, old, _new) in self.engine_ab.CONTROLS.items():
            with self.subTest(control=name):
                source = (Path(__file__).resolve().parents[1] / rel).read_text(encoding="utf-8")
                self.assertEqual(source.count(old), 1, f"{name}: anchor not unique in {rel}")


if __name__ == "__main__":
    unittest.main()
