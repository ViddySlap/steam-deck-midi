#!/usr/bin/env python3
"""Idle CPU and clean-shutdown instrument for the non-tray bridge (P0, lap sdpolish).

WHY THIS EXISTS. The tray CPU spin (sdcore3 T1, then sdauto A3: 94.3% of one
core on the Mac, down to 0.3%) lingered because every automated run set
PYSTRAY_BACKEND=dummy, which removes the real tray and so removes the defect,
and because A3's CPU number came from a one-off script rather than a rerunnable
check. This instrument is the rerunnable one. On the Mac it deliberately runs
WITHOUT PYSTRAY_BACKEND=dummy so the real tray path executes (MASTER 13, 14:28);
BROWSER stays set to a no-op and --no-browser is always passed.

WHAT IT MEASURES, per arm:
  - process CPU as a CPU-TIME DELTA over a fixed idle window (ps on the Mac,
    GetProcessTimes on Windows), as a percentage of ONE core;
  - seconds to exit under a named stop arm (SIGINT, or POST /api/shutdown);
  - new crash reports in ~/Library/Logs/DiagnosticReports (Mac).

DECLARED BEFORE DATA:
  CPU <= 5.0% of one core, exit within 5.0 s, zero new crash reports.

VALIDITY. The load preflight runs INSIDE this script, before and after every
arm. An arm whose preflight fails is INVALID - never PASS and never FAIL. The
rules it enforces are the lane's, not this script's: LOAD RULES (MASTER 16:5x,
01:11), the EXTENDED LOAD VALIDITY (MASTER 13, 15:21(3)), the extended foreign
definition (MASTER 13, 17:18(2)), the PER-ARM QUIET GATE (MASTER 13, 17:39),
SCRATCH INDEXING (MASTER 13, 17:09) and the vault-sync and free-memory rules
(MASTER 13, 19:29).

NEVER --tray. NEVER the installed tray's ports. See scripts/showready/README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]

# Declared before data.
MAX_CPU_PERCENT_OF_ONE_CORE = 5.0
MAX_EXIT_SECONDS = 5.0
IDLE_SECONDS = 30.0

# Lane load rules.
QUIET_GATE_LOAD1 = 4.0            # PER-ARM QUIET GATE: wait for load1 below this
MAX_IN_ARM_LOAD1 = 5.0            # EXTENDED VALIDITY: any in-arm sample above => INVALID
MAX_FOREIGN_CORE_FRACTION = 0.50  # non-lane process above this...
MAX_FOREIGN_CORE_SECONDS = 10.0   # ...for longer than this => INVALID
SAMPLE_INTERVAL_SECONDS = 5.0     # whole-machine sampler cadence
VAULT_SYNC_HOLD_PERCENT = 80.0    # MASTER 13 19:29: near 90% => hold, do not measure
MIN_FREE_MEMORY_PERCENT = 25.0    # MASTER 13 19:29: below => do not add a 3rd tree

# The installed tray owns these. Every arm must use others.
FORBIDDEN_PORTS = {45123, 7723}

# MASTER 13, 19:29(1): the vault sync is a NAMED non-lane load.
VAULT_SYNC_PATTERN = "obsidian-headless"
# MASTER 13, 17:18(2) + LOAD RULES: foreign script roots.
FOREIGN_PATH_PATTERNS = (
    "/Users/viddyslap/Documents/project-workspaces/local-LLM-",
    "/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/",
)
FOREIGN_SCRIPT_NAMES = ("run-all.sh",)
FOREIGN_SHELLS = ("zsh", "bash", "sh", "node")
# MASTER 13, 19:42(1): the local-LLM-* clause bites on CONSUMPTION, not
# presence. A matching process counts only if it is a bench DRIVER, or if a
# sample shows it above BENCH_BUSY_PERCENT of one core. Otherwise it is
# RECORDED beside the arm and not counted. The ORIGINAL sdbar3 definition
# (the h14 engine-tests path and run-all.sh) is UNCHANGED and counts on
# PRESENCE.
BENCH_DRIVER_NAMES = ("run2.sh", "drive-iteration.mjs")
BENCH_DRIVER_PREFIXES = ("run-watcher",)
BENCH_BUSY_PERCENT = 5.0
# MASTER 13, 19:42(2): lane infrastructure above this is a NEEDS-MASTER line,
# never a self-voided arm.
INFRASTRUCTURE_NOTIFY_PERCENT = 25.0
# The clause that still counts on presence (the original sdbar3 wording).
PRESENCE_FOREIGN_PATTERNS = (
    "/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/",
)
# The harness engine this chain reports to (brief: ENGINE http://127.0.0.1:8899).
# It lives under local-LLM-engine/, so the extended foreign glob `local-LLM-*`
# matches it literally - but it is LANE INFRASTRUCTURE, not foreign load, and
# the brief forbids restarting it. Recorded with every arm, never counted.
# The master's rule was declared against qwen-bench driving load1 to 9.38.
# MASTER 13, 19:42(2) names server.mjs. The harness ALSO runs short-lived node
# processes out of the same tree - the advancer fires every 30 s - and each one
# is briefly above the 5% consumption threshold, so matching only server.mjs
# voided a BASE arm on a harness tick (pid 64852, gone before it could be
# named). The whole engine tree is the lane's own infrastructure: RECORDED
# beside every arm with its sampled CPU, never counted. Reported to the master
# as a third detector correction.
LANE_INFRASTRUCTURE = (
    "/Users/viddyslap/Documents/project-workspaces/local-LLM-engine/",
)

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
LOOPBACK_OK = {"127.0.0.1", "localhost", "0.0.0.0"}


# ---------------------------------------------------------------------------
# machine sampling


def _run(cmd: list[str], timeout: float = 20.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def load1() -> float | None:
    """1-minute load average. NAMES ITS COMMAND: sysctl -n vm.loadavg."""
    if platform.system() == "Darwin":
        text = _run(["sysctl", "-n", "vm.loadavg"])
        try:
            return float(text.strip().strip("{}").split()[0])
        except Exception:
            return None
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return None


def free_memory_percent() -> float | None:
    """MASTER 13, 19:29(2). NAMES ITS COMMAND: memory_pressure."""
    if platform.system() != "Darwin":
        return None
    text = _run(["memory_pressure"])
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", text)
    return float(match.group(1)) if match else None


def _ps_rows() -> list[dict]:
    """Every process: pid, %cpu, command line. Command: ps -Ao pid=,pcpu=,command=."""
    rows = []
    for line in _run(["ps", "-Ao", "pid=,pcpu=,command="]).splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            rows.append({"pid": int(parts[0]), "pcpu": float(parts[1]), "command": parts[2]})
        except ValueError:
            continue
    return rows


def vault_sync_sample() -> list[dict]:
    """MASTER 13, 19:29(1): sample every obsidian-headless pid's CPU.

    The sync was measured at 90.3-90.7% of one core at 19:28 and at 0.0% at
    19:30, so it is BURSTY: this is sampled per arm, never assumed.
    """
    return [{"pid": r["pid"], "pcpu": r["pcpu"]}
            for r in _ps_rows() if VAULT_SYNC_PATTERN in r["command"]]


def spinner_pids() -> list[int]:
    """LOAD RULES: `pgrep -f "while True: pass"` must be EMPTY."""
    text = _run(["pgrep", "-f", "while True: pass"])
    return [int(p) for p in text.split() if p.strip().isdigit()]


def foreign_lines(own_pids: set[int]) -> tuple[list[dict], list[dict], list[dict]]:
    """LOAD RULES, MASTER 13 17:18(2) and 19:42.

    Returns (counted_foreign, lane_infrastructure, recorded_not_counted).

    The match is on the EXECUTABLE and the FIRST SCRIPT ARGUMENT only, never on
    the whole command line: a `claude` session with a local-LLM path somewhere
    in its `--add-dir` arguments is an agent session, not a foreign script, and
    matching the full command line classed one as foreign on the first run of
    this instrument.
    """
    foreign, infrastructure, recorded = [], [], []
    for row in _ps_rows():
        if row["pid"] in own_pids:
            continue
        command = row["command"]
        if "codex exec" in command:
            continue
        parts = command.split()
        if not parts:
            continue
        executable, script = parts[0], (parts[1] if len(parts) > 1 else "")
        if any(marker in executable or marker in script for marker in LANE_INFRASTRUCTURE):
            infrastructure.append(row)
            continue
        base = Path(executable).name
        candidates = [executable]
        if base in FOREIGN_SHELLS and script:
            candidates.append(script)

        # (a) The presence clause: unchanged from sdbar3.
        presence = any(pattern in candidate
                       for candidate in candidates for pattern in PRESENCE_FOREIGN_PATTERNS)
        if not presence and script and Path(script).name in FOREIGN_SCRIPT_NAMES:
            presence = True
        if presence:
            row["counted_because"] = "presence clause (sdbar3, unchanged)"
            foreign.append(row)
            continue

        # (b) The local-LLM-* clause: consumption, not presence (19:42(1)).
        matches = any(pattern in candidate
                      for candidate in candidates for pattern in FOREIGN_PATH_PATTERNS)
        if not matches:
            continue
        script_name = Path(script).name if script else ""
        is_driver = (script_name in BENCH_DRIVER_NAMES
                     or base in BENCH_DRIVER_NAMES
                     or any(script_name.startswith(prefix) or base.startswith(prefix)
                            for prefix in BENCH_DRIVER_PREFIXES))
        if is_driver:
            row["counted_because"] = f"bench driver ({script_name or base})"
            foreign.append(row)
        elif row["pcpu"] > BENCH_BUSY_PERCENT:
            row["counted_because"] = f"above {BENCH_BUSY_PERCENT}% of one core ({row['pcpu']})"
            foreign.append(row)
        else:
            row["counted_because"] = None
            recorded.append(row)
    return foreign, infrastructure, recorded


def preflight(own_pids: set[int]) -> dict:
    """Every load rule, measured. `valid` False => the arm is INVALID."""
    spinners = spinner_pids()
    foreign, infrastructure, recorded = foreign_lines(own_pids)
    sync = vault_sync_sample()
    load = load1()
    free = free_memory_percent()
    sync_busy = [s for s in sync if s["pcpu"] >= VAULT_SYNC_HOLD_PERCENT]
    reasons = []
    if spinners:
        reasons.append(f"spinner pids present: {spinners}")
    if foreign:
        reasons.append(f"foreign_lines={len(foreign)}: "
                       + "; ".join(f"{f['pid']} {f['command'][:80]}" for f in foreign))
    if load is not None and load > MAX_IN_ARM_LOAD1:
        reasons.append(f"load1 {load} > {MAX_IN_ARM_LOAD1}")
    if sync_busy:
        reasons.append(f"vault sync busy: {sync_busy}")
    hot_infrastructure = [i for i in infrastructure if i["pcpu"] > INFRASTRUCTURE_NOTIFY_PERCENT]
    return {
        "load1": load,
        "free_memory_percent": free,
        "spinner_pids": spinners,
        "foreign_lines": len(foreign),
        "foreign_detail": [{"pid": f["pid"], "pcpu": f["pcpu"], "command": f["command"][:160]}
                           for f in foreign],
        "lane_infrastructure": [{"pid": i["pid"], "pcpu": i["pcpu"],
                                 "command": i["command"][:120]} for i in infrastructure],
        "local_llm_recorded_not_counted": [
            {"pid": r["pid"], "pcpu": r["pcpu"], "command": r["command"][:160]}
            for r in recorded],
        "vault_sync": sync,
        "vault_sync_hold": bool(sync_busy),
        "infrastructure_needs_master": [
            f"sdpolish lane engine at {i['pcpu']:.1f}% of one core during an arm (pid {i['pid']})"
            for i in hot_infrastructure],
        "valid": not reasons,
        "reasons": reasons,
    }


def wait_for_quiet(timeout: float = 1800.0) -> dict:
    """PER-ARM QUIET GATE: wait for load1 < 4.0 AND a quiet vault sync.

    MASTER 13, 17:39 gates on load1. MASTER 13, 19:29(1) makes the vault sync a
    named non-lane load, and 19:42 stresses it is BURSTY (90.3% at 19:28, 0.0%
    at 19:31, 87.6% at 19:41), so only a per-arm sample is the machine's state.
    A gate before the arm beats voiding it after, which is the whole point of
    17:39 - and the sync is provoked by writes into the vault, including this
    lane's own lane-log appends, so waiting out a burst is the normal case.
    """
    started = time.monotonic()
    bursts = []
    while True:
        load = load1()
        sync = vault_sync_sample()
        hottest = max((s["pcpu"] for s in sync), default=0.0)
        # Windows has no load average and no vault sync: those two lane rules
        # are the MAC's. Treating an unavailable measurement as "not yet quiet"
        # made this gate wait out its whole timeout on the laptop and the arm
        # never started. An unavailable signal is NOT a failing signal - but it
        # is recorded as unavailable, never reported as a measured quiet.
        load_ok = load is None or load < QUIET_GATE_LOAD1
        sync_ok = hottest < VAULT_SYNC_HOLD_PERCENT
        waited = time.monotonic() - started
        if load_ok and sync_ok:
            return {"waited_seconds": round(waited, 1), "load1_at_start": load,
                    "load1_available": load is not None,
                    "vault_sync_at_start": sync, "vault_sync_bursts_waited_out": bursts,
                    "gate": "passed" if load is not None else "passed (no load average on this platform)"}
        if not sync_ok:
            bursts.append({"t": round(waited, 1), "pcpu": hottest})
        if waited > timeout:
            return {"waited_seconds": round(waited, 1), "load1_at_start": load,
                    "vault_sync_at_start": sync, "vault_sync_bursts_waited_out": bursts,
                    "gate": "timeout",
                    "needs_master": (f"sdpolish vault sync at {hottest:.1f} of one core, "
                                     "timing arm held") if not sync_ok else
                                    f"sdpolish Mac timing blocked by machine load load1={load}"}
        time.sleep(5.0)


# ---------------------------------------------------------------------------
# process CPU time


def process_cpu_seconds(pid: int) -> float | None:
    """Cumulative CPU seconds for `pid`, all threads.

    Mac/posix: `ps -o cputime= -p <pid>` ([DD-]HH:MM:SS.ss or MM:SS.ss). The
               bridge is a single process there (the venv python is the real
               interpreter, not a launcher), so no tree walk is needed.
    Windows:   GetProcessTimes summed over the process AND ITS DESCENDANTS,
               because the venv's Scripts\\python.exe re-execs the real
               interpreter. py-spy is NOT installed and must not be installed.

    PROVEN IN BOTH DIRECTIONS on each machine by the --cpu-self-test arm: a
    child spinning a whole core must read near 100%, and a sleeping child near 0.
    """
    if os.name == "nt":
        return _windows_cpu_seconds(pid)
    text = _run(["ps", "-o", "cputime=", "-p", str(pid)]).strip()
    if not text:
        return None
    days = 0
    if "-" in text:
        day_text, text = text.split("-", 1)
        days = int(day_text)
    parts = text.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60.0 + part
    return seconds + days * 86400.0


def _windows_process_tree(pid: int) -> list[int]:
    """`pid` and every descendant, via a Toolhelp32 snapshot.

    The venv's `Scripts\\python.exe` is a launcher that re-execs the real
    interpreter, so the pid we start is NOT the pid that burns CPU. Measuring
    only the parent reported 0.0% for a process spinning a whole core - a
    detector that could only ever pass.
    """
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return [pid]
    children: dict[int, list[int]] = {}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return [pid]
        while True:
            children.setdefault(entry.th32ParentProcessID, []).append(entry.th32ProcessID)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    tree, queue = [], [pid]
    while queue:
        current = queue.pop()
        if current in tree:
            continue
        tree.append(current)
        queue.extend(children.get(current, []))
    return tree


def _windows_cpu_seconds(pid: int) -> float | None:
    """Kernel + user CPU seconds for `pid` AND its descendants."""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # HANDLE is pointer-sized. Left as the default c_int, a 64-bit handle is
    # TRUNCATED and every call downstream is against the wrong object.
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME)]

    def to_seconds(ft):
        return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7

    total, seen_any = 0.0, False
    for target in _windows_process_tree(pid):
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, target)
        if not handle:
            continue
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                        ctypes.byref(kernel), ctypes.byref(user)):
                total += to_seconds(kernel) + to_seconds(user)
                seen_any = True
        finally:
            kernel32.CloseHandle(handle)
    return total if seen_any else None


def free_port() -> int:
    """A port the OS says is free, and never one the installed tray owns."""
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in FORBIDDEN_PORTS:
            return port


# ---------------------------------------------------------------------------
# crash reports


def crash_reports() -> set[str]:
    directory = Path.home() / "Library/Logs/DiagnosticReports"
    if not directory.is_dir():
        return set()
    try:
        return {p.name for p in directory.iterdir()}
    except OSError:
        return set()


# ---------------------------------------------------------------------------
# engine config scratch


def build_engine_scratch(source: Path, dest: Path, update_hz_override: float | None = None,
                         override_type: str = "autopilot") -> dict:
    """Copy factory engine configs to scratch and rewrite every target to loopback.

    ENGINES-ON RULE: the factory configs point at Ben's Resolume network and at
    real PTZ cameras (192.168.0.203-205). No process in this lane may send a
    packet there. The caller MUST run scan_for_non_loopback() on the result and
    refuse the boot on any hit.
    """
    dest.mkdir(parents=True, exist_ok=True)
    rewritten = 0
    for path in sorted(source.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))

        def to_loopback(node):
            nonlocal rewritten
            if isinstance(node, dict):
                return {k: to_loopback(v) for k, v in node.items()}
            if isinstance(node, list):
                return [to_loopback(v) for v in node]
            if isinstance(node, str):
                if IP_RE.fullmatch(node) and node not in LOOPBACK_OK:
                    rewritten += 1
                    return "127.0.0.1"
                if "://" in node and IP_RE.search(node):
                    replaced = IP_RE.sub("127.0.0.1", node)
                    if replaced != node:
                        rewritten += 1
                    return replaced
            return node

        spec = to_loopback(spec)
        if update_hz_override is not None and spec.get("type") == override_type:
            spec["update_hz"] = update_hz_override
        (dest / path.name).write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return {"files": len(list(dest.glob("*.json"))), "addresses_rewritten": rewritten}


def scan_for_non_loopback(directory: Path) -> list[str]:
    """Every IP or host in the scratch configs that is not loopback. 0 required."""
    hits = []
    for path in sorted(directory.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for ip in IP_RE.findall(text):
            if ip not in LOOPBACK_OK:
                hits.append(f"{path.name}: {ip}")
    return hits


# ---------------------------------------------------------------------------
# one arm


def verdict_for(cpu_percent, exit_seconds, new_crashes, preflight_ok,
                sampler_breaches) -> str:
    """The pass/fail/INVALID decision, as a pure function (unit-tested)."""
    if not preflight_ok or sampler_breaches:
        return "INVALID"
    if cpu_percent is None or exit_seconds is None:
        return "INVALID"
    if cpu_percent > MAX_CPU_PERCENT_OF_ONE_CORE:
        return "FAIL"
    if exit_seconds > MAX_EXIT_SECONDS:
        return "FAIL"
    if new_crashes:
        return "FAIL"
    return "PASS"


def run_arm(name: str, tree: Path, python: str, scratch: Path, stop: str,
            engines_dir: Path | None, idle_seconds: float, no_ui: bool,
            expect_no_sidecar: bool) -> dict:
    """Boot the non-tray bridge, idle, measure CPU, stop it, prove it gone."""
    record: dict = {"arm": name, "tree": str(tree), "stop": stop,
                    "engines": str(engines_dir) if engines_dir else None}

    record["quiet_gate"] = wait_for_quiet()
    if record["quiet_gate"]["gate"].startswith("timeout"):
        record["verdict"] = "INVALID"
        record["needs_master"] = record["quiet_gate"]["needs_master"]
        return record
    pre = preflight(set())
    record["preflight_before"] = pre
    if pre["vault_sync_hold"]:
        record["verdict"] = "INVALID"
        record["needs_master"] = (
            "sdpolish vault sync at "
            f"{max(s['pcpu'] for s in pre['vault_sync']):.1f} of one core, timing arm held")
        return record
    if not pre["valid"]:
        record["verdict"] = "INVALID"
        return record

    udp_port, ui_port = free_port(), free_port()
    record["udp_port"], record["ui_port"] = udp_port, ui_port
    assert udp_port not in FORBIDDEN_PORTS and ui_port not in FORBIDDEN_PORTS

    work = scratch / name
    work.mkdir(parents=True, exist_ok=True)
    map_path = work / "map.json"
    map_path.write_text('{"mappings": {}}', encoding="utf-8")

    # BROWSER CLASS RULE: --no-browser WHERE THE ENTRY POINT SUPPORTS IT. It was
    # added by sdauto A3 (38de0a4), so a BASE arm older than that rejects it
    # with "unrecognized arguments" and never boots. BROWSER stays a no-op that
    # really exits 0 on every arm either way.
    supports_no_browser = "--no-browser" in (tree / "windows/win_recv.py").read_text(
        encoding="utf-8", errors="replace")
    record["supports_no_browser"] = supports_no_browser
    argv = [python, "-B", "-m", "windows.win_recv",
            "--map", str(map_path),
            "--listen", f"127.0.0.1:{udp_port}",
            "--ui-port", str(ui_port),
            "--dry-run", "--no-pulse", "--no-osc-relay"]
    if supports_no_browser:
        argv.append("--no-browser")
    if no_ui:
        argv.append("--no-ui")
    if engines_dir is None:
        argv.append("--no-engines")
    else:
        argv.extend(["--engines", str(engines_dir)])
    record["argv"] = argv
    assert "--tray" not in argv, "idle_smoke NEVER launches --tray"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(tree)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # BROWSER stays a no-op; --no-browser is passed above as well.
    env["BROWSER"] = "/usr/bin/true" if os.name != "nt" else env.get("BROWSER", "")
    # DELIBERATE (MASTER 13, 14:28): on the Mac the real tray path must run, so
    # PYSTRAY_BACKEND=dummy is REMOVED here, for this instrument only.
    env.pop("PYSTRAY_BACKEND", None)
    record["pystray_backend_set"] = "PYSTRAY_BACKEND" in env

    crashes_before = crash_reports()
    log_path = work / "bridge.log"
    # WINDOWS: the child MUST be its own process group. Without
    # CREATE_NEW_PROCESS_GROUP, the CTRL_BREAK_EVENT the stop arm sends goes to
    # the whole group - it killed the PowerShell host and the ssh rail running
    # this instrument and left the console in the PS debugger
    # (IDLE_EXIT=-1073741510, STATUS_CONTROL_C_EXIT). A stop arm must reach the
    # bridge and nothing else.
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(argv, cwd=str(tree), stdout=log, stderr=subprocess.STDOUT,
                                env=env, creationflags=creation_flags)
    record["pid"] = proc.pid
    own = {proc.pid}

    try:
        ready = False
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            # Readiness is the UDP socket bind, from the bridge's own log. It
            # is the ONE marker every tree in this lap emits: GET /api/version
            # was added by sdauto A4 (a8fec2a), so probing it made a BASE arm
            # older than A4 look like a bridge that never booted when the log
            # said "listening on udp://".
            if "listening on udp://" in log_path.read_text(errors="replace"):
                ready = True
                break
            time.sleep(0.25)
        record["ready"] = ready
        if not ready:
            # A bridge that EXITED is a RESULT, not bad measuring conditions:
            # that is the receive loop dying, which is the whole defect class
            # this instrument exists for. Only a bridge that is still alive but
            # never bound is INVALID.
            record["exit_code_during_startup"] = proc.poll()
            record["log_tail"] = log_path.read_text(errors="replace")[-3000:]
            if proc.poll() is not None:
                record["verdict"] = "FAIL"
                record["reason"] = (
                    f"bridge exited during startup with code {proc.returncode} "
                    "before binding its UDP socket")
                record["died_during_startup"] = True
                record["exit_seconds"] = 0.0
            else:
                record["verdict"] = "INVALID"
                record["reason"] = "bridge never bound its UDP socket and is still running"
            return record

        # ---- idle window, with the whole-machine sampler -------------------
        cpu0 = process_cpu_seconds(proc.pid)
        wall0 = time.monotonic()
        samples = []
        breaches = []
        busy_since: dict[int, float] = {}
        while time.monotonic() - wall0 < idle_seconds:
            time.sleep(min(SAMPLE_INTERVAL_SECONDS, idle_seconds))
            now = time.monotonic()
            sample = {"t": round(now - wall0, 1), "load1": load1(),
                      "vault_sync": vault_sync_sample(),
                      "free_memory_percent": free_memory_percent(), "hot": []}
            for row in _ps_rows():
                if row["pid"] in own or row["pcpu"] < 20.0:
                    continue
                name_only = Path(row["command"].split()[0]).name if row["command"] else ""
                if name_only in ("WindowServer", "kernel_task"):
                    sample["hot"].append({"pid": row["pid"], "pcpu": row["pcpu"],
                                          "name": name_only, "counted": False})
                    continue
                sample["hot"].append({"pid": row["pid"], "pcpu": row["pcpu"],
                                      "name": name_only, "counted": True})
                if row["pcpu"] >= MAX_FOREIGN_CORE_FRACTION * 100:
                    started = busy_since.setdefault(row["pid"], now)
                    if now - started > MAX_FOREIGN_CORE_SECONDS:
                        breaches.append({"pid": row["pid"], "name": name_only,
                                         "pcpu": row["pcpu"],
                                         "seconds": round(now - started, 1)})
                else:
                    busy_since.pop(row["pid"], None)
            if sample["load1"] is not None and sample["load1"] > MAX_IN_ARM_LOAD1:  # noqa: E501 - unavailable is not a breach
                breaches.append({"load1": sample["load1"], "t": sample["t"]})
            samples.append(sample)
            if proc.poll() is not None:
                break
        cpu1 = process_cpu_seconds(proc.pid)
        wall = time.monotonic() - wall0
        record["samples"] = samples
        record["sampler_breaches"] = breaches
        record["idle_wall_seconds"] = round(wall, 2)
        record["cpu_seconds"] = None if (cpu0 is None or cpu1 is None) else round(cpu1 - cpu0, 4)
        record["cpu_percent_of_one_core"] = (
            None if record["cpu_seconds"] is None else round(100.0 * record["cpu_seconds"] / wall, 3))

        if proc.poll() is not None:
            record["died_during_idle"] = True
            record["exit_code_during_idle"] = proc.returncode
            record["log_tail"] = log_path.read_text(errors="replace")[-3000:]
            record["verdict"] = "FAIL"
            record["exit_seconds"] = 0.0
            return record

        # ---- stop arm ------------------------------------------------------
        stop_started = time.monotonic()
        if stop == "sigint":
            if os.name == "nt":
                # CTRL_BREAK_EVENT, into the child's OWN group. Windows has no
                # SIGINT delivery to another process that is both reliable and
                # safe for the sender, so this arm measures an ABRUPT stop on
                # Windows and a graceful KeyboardInterrupt on the Mac. The
                # record says which, so a reader cannot mistake the two.
                record["stop_mechanism"] = "CTRL_BREAK_EVENT to a new process group"
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                record["stop_mechanism"] = "SIGINT"
                proc.send_signal(signal.SIGINT)
        elif stop == "shutdown":
            if no_ui:
                # There is no HTTP server to POST to. Saying so beats recording
                # a 17 s "exit" that is really this instrument's own kill.
                record["verdict"] = "NOT_APPLICABLE"
                record["reason"] = "--no-ui has no HTTP surface; POST /api/shutdown cannot apply"
                record["stop_mechanism"] = "none (--no-ui)"
                proc.kill()
                proc.wait(timeout=10)
                record["exit_seconds"] = None
                return record
            record["stop_mechanism"] = "POST /api/shutdown"
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{ui_port}/api/shutdown", method="POST", data=b"")
                with urllib.request.urlopen(request, timeout=5) as response:
                    record["shutdown_status"] = response.status
            except urllib.error.HTTPError as exc:
                record["shutdown_status"] = exc.code
            except (urllib.error.URLError, OSError) as exc:
                record["shutdown_status"] = f"error: {exc}"
        else:
            raise ValueError(f"unknown stop arm: {stop}")
        try:
            proc.wait(timeout=MAX_EXIT_SECONDS + 10.0)
        except subprocess.TimeoutExpired:
            pass
        record["exit_seconds"] = round(time.monotonic() - stop_started, 3)
        record["exit_code"] = proc.returncode
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
            record["had_to_kill"] = True
    record["process_gone"] = proc.poll() is not None

    log_text = log_path.read_text(errors="replace")
    record["log_tail"] = log_text[-3000:]
    if expect_no_sidecar:
        # The A3 fix, asserted against the REAL tray path (no PYSTRAY_BACKEND).
        # A tree older than A3 has no such line BY CONSTRUCTION - that tree is
        # the one that spins - so absence is only a FAILURE where A3 landed.
        line = "system tray not started on darwin"
        record["no_sidecar_line"] = line in log_text
        record["tree_has_a3_fix"] = "_should_start_receiver_tray" in (
            tree / "windows/win_recv.py").read_text(encoding="utf-8", errors="replace")
    record["new_crash_reports"] = sorted(crash_reports() - crashes_before)

    post = preflight(own)
    record["preflight_after"] = post
    record["verdict"] = verdict_for(
        record.get("cpu_percent_of_one_core"), record.get("exit_seconds"),
        record["new_crash_reports"], pre["valid"] and post["valid"],
        record["sampler_breaches"])
    if (expect_no_sidecar and record.get("tree_has_a3_fix")
            and not record.get("no_sidecar_line")):
        record["verdict"] = "FAIL"
        record["reason"] = "darwin no-sidecar log line absent"
    return record


def cpu_self_test(python: str) -> dict:
    """Prove the CPU reader fires and does not fire, ON THIS MACHINE.

    A CPU instrument that reads the wrong process reports 0.0% for everything
    and can only ever PASS. That is exactly what happened on the laptop: the
    venv launcher re-execs the real interpreter, so measuring the pid we
    started gave 0.0% for a child burning a whole core. Every gate runs this
    before believing any CPU number.

    Declared: busy >= 50% of one core, idle <= 5%.
    """
    result = {"machine": platform.system(), "python": python,
              "declared": {"busy_min_percent": 50.0, "idle_max_percent": 5.0}}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    spin = "import time\nend=time.monotonic()+6.0\nwhile time.monotonic()<end: pass"
    for name, code in (("busy", spin), ("idle", "import time; time.sleep(6)")):
        proc = subprocess.Popen([python, "-c", code], creationflags=flags)
        try:
            time.sleep(0.5)
            c0 = process_cpu_seconds(proc.pid)
            w0 = time.monotonic()
            time.sleep(4.0)
            c1 = process_cpu_seconds(proc.pid)
            wall = time.monotonic() - w0
        finally:
            proc.wait(timeout=30)
        percent = None if (c0 is None or c1 is None) else round(100.0 * (c1 - c0) / wall, 2)
        result[name] = {"pid": proc.pid, "cpu_seconds": None if c0 is None or c1 is None
                        else round(c1 - c0, 4), "percent_of_one_core": percent}
    busy = result["busy"]["percent_of_one_core"]
    idle = result["idle"]["percent_of_one_core"]
    result["passed"] = (busy is not None and idle is not None
                        and busy >= 50.0 and idle <= 5.0)
    if not result["passed"]:
        result["reason"] = ("the CPU reader cannot distinguish a spinning process from a "
                            "sleeping one on this machine; every CPU number it produces "
                            "is meaningless")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", type=Path, default=ROOT,
                        help="repo tree to boot (a git-archive extract for a BASE arm)")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--label", default="arm")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--idle-seconds", type=float, default=IDLE_SECONDS)
    parser.add_argument("--no-ui", action="store_true")
    parser.add_argument("--engines", action="store_true",
                        help="ENGINES-ON arm: boot from a loopback-rewritten scratch copy "
                             "of config/engines.factory/")
    parser.add_argument("--engines-update-hz", type=float, default=None,
                        help="sensitivity control: force this update_hz on the qualifying engine")
    parser.add_argument("--stop", choices=("sigint", "shutdown", "both"), default="both")
    parser.add_argument("--cpu-self-test", action="store_true",
                        help="prove the CPU reader fires and does not fire on this machine, "
                             "then exit")
    args = parser.parse_args(argv)

    if args.cpu_self_test:
        check = cpu_self_test(args.python)
        print(json.dumps(check, indent=1))
        return 0 if check["passed"] else 1

    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    # SCRATCH INDEXING (MASTER 13, 17:09): before the first file is written.
    marker = scratch / ".metadata_never_index"
    marker.touch()

    result = {
        "schema": "sdpolish-idle-smoke/1",
        "label": args.label,
        "machine": platform.system(),
        "python": args.python,
        "tree": str(args.tree.resolve()),
        "metadata_never_index": marker.exists(),
        "declared": {
            "max_cpu_percent_of_one_core": MAX_CPU_PERCENT_OF_ONE_CORE,
            "max_exit_seconds": MAX_EXIT_SECONDS,
            "idle_seconds": args.idle_seconds,
        },
        "arms": [],
    }

    engines_dir = None
    if args.engines:
        engines_dir = scratch / f"{args.label}-engines"
        if engines_dir.exists():
            shutil.rmtree(engines_dir)
        result["engine_scratch"] = build_engine_scratch(
            args.tree / "config/engines.factory", engines_dir, args.engines_update_hz)
        hits = scan_for_non_loopback(engines_dir)
        result["loopback_scan_hits"] = hits
        result["loopback_scan_count"] = len(hits)
        if hits:
            result["verdict"] = "REFUSED"
            result["reason"] = f"non-loopback target(s) in scratch engine config: {hits}"
            print(json.dumps(result, indent=1))
            return 2

    # Never believe a CPU number from a reader that has not been shown to work
    # on THIS machine, in both directions.
    result["cpu_self_test"] = cpu_self_test(args.python)
    if not result["cpu_self_test"]["passed"]:
        result["verdict"] = "INVALID"
        result["reason"] = result["cpu_self_test"]["reason"]
        print(json.dumps(result, indent=1))
        return 2

    stops = ("sigint", "shutdown") if args.stop == "both" else (args.stop,)
    for stop in stops:
        arm = run_arm(
            name=f"{args.label}-{stop}", tree=args.tree.resolve(), python=args.python,
            scratch=scratch, stop=stop, engines_dir=engines_dir,
            idle_seconds=args.idle_seconds, no_ui=args.no_ui,
            expect_no_sidecar=(platform.system() == "Darwin" and not args.no_ui))
        result["arms"].append(arm)

    verdicts = [a["verdict"] for a in result["arms"] if a["verdict"] != "NOT_APPLICABLE"]
    result["verdict"] = ("INVALID" if "INVALID" in verdicts
                         else "FAIL" if "FAIL" in verdicts
                         else "PASS" if verdicts else "NOT_APPLICABLE")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({
        "label": result["label"], "verdict": result["verdict"],
        "arms": [{"arm": a["arm"], "verdict": a["verdict"],
                  "cpu_percent_of_one_core": a.get("cpu_percent_of_one_core"),
                  "exit_seconds": a.get("exit_seconds"),
                  "new_crash_reports": a.get("new_crash_reports"),
                  "no_sidecar_line": a.get("no_sidecar_line"),
                  "load1_before": a.get("preflight_before", {}).get("load1"),
                  "free_memory_percent": a.get("preflight_before", {}).get("free_memory_percent"),
                  "vault_sync": a.get("preflight_before", {}).get("vault_sync"),
                  "foreign_lines": a.get("preflight_before", {}).get("foreign_lines")}
                 for a in result["arms"]],
        "loopback_scan_count": result.get("loopback_scan_count"),
        "out": str(args.out) if args.out else None,
    }, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
