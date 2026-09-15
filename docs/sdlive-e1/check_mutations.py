"""Run E1 functional controls against owned scratch copies, restoring each fault."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
work = Path(tempfile.mkdtemp(prefix="mutations-", dir=sys.argv[1]))
for directory in ("windows", "protocol", "tests", "config"):
    shutil.copytree(root / directory, work / directory,
                    ignore=shutil.ignore_patterns("__pycache__", "*.local.json", "state", "presets"))
source = work / "windows/live_events.py"
pristine = source.read_text()
checks = []
for name, before, after, selector in [
    ("no-midi-observation", 'safe_publish(publisher, {"kind": "midi",', 'safe_publish(None, {"kind": "midi",',
     "tests.test_live_events.LiveMidiTests.test_all_methods_forward_exact_arguments_before_publish_including_panic"),
    ("no-axis-coalescing", 'axes[row["action"]] = row', 'rows.append(row)',
     "tests.test_live_events.LiveEventsTests.test_drop_count_resume_and_axis_latest_at_most_thirty_hz"),
    ("no-stream-timeout", 'self.connection.settimeout(0.5)', 'pass  # planted omission',
     "tests.test_live_events.LiveRouteTests.test_stalled_tcp_reader_cannot_hold_server_stop"),
    ("no-stream-stop", 'self.live_events.close()', 'pass  # planted omission',
     "tests.test_live_events.LiveRouteTests.test_post_shutdown_with_open_stream_stops_serve_and_http_within_three_seconds"),
]:
    target = work / "windows/ui_server.py" if name in ("no-stream-stop", "no-stream-timeout") else source
    original = target.read_text()
    assert original.count(before) == 1
    for arm in ("pristine", "red", "restored"):
        target.write_text(original.replace(before, after) if arm == "red" else original)
        command = [sys.executable, "-B", "-m", "unittest", "-v", selector]
        result = subprocess.run(command, cwd=work, env={**os.environ, "TMPDIR": str(work),
                                "PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true"},
                                capture_output=True, text=True, timeout=15)
        log = work / f"{name}-{arm}.log"
        log.write_text(result.stdout + result.stderr)
        expected = 1 if arm == "red" else 0
        checks.append({"name": name, "arm": arm, "command": command, "cwd": str(work),
                       "exit": result.returncode, "log": str(log)})
        assert result.returncode == expected, checks[-1]
        if arm == "red":
            assert "FAIL: " in result.stderr and "AssertionError" in result.stderr
    assert target.read_bytes() == original.encode()
output = {"checks": checks, "work": str(work), "status": "PASS"}
(work / "results.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps(output, indent=2))
