"""MASTER 13 15:21 (3) validity of every arm of a timing_ab run from whole-machine samples.

  arm_validity.py SCRATCH_DIR SAMPLES [--format jsonl|loadlog]

Arm window = mtime of <arm>/start .. latest mtime of any file in <arm>/ (accepted attempts only: the highest
try per arm name). INVALID if any in-window sample has load1 > 5.0, or any non-lane, non-exempt process holds
> 50% of one core for > 10 s (same pid above 50% in consecutive samples spanning > 10 s). loadlog format
(the 5 s load.log of run 1 / sensitivity) carries load1 only: the process clause is reported NOT CHECKABLE.
Prints one JSON line per arm and a summary; exit 0 only if every arm is VALID.
"""
import json, os, re, sys
from pathlib import Path
from datetime import datetime

scratch, samples_path = Path(sys.argv[1]), Path(sys.argv[2])
fmt = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "--format" else "jsonl"
samples = []
day = None
for line in samples_path.read_text().splitlines():
    if fmt == "jsonl":
        samples.append(json.loads(line))
    else:
        m = re.match(r"(\d\d:\d\d:\d\d) load1=([\d.]+)", line)
        if m:
            samples.append({"hms": m.group(1), "load1": float(m.group(2)), "procs": None})
run = next(p for p in scratch.iterdir() if p.is_dir() and p.name.startswith("timing-"))
arms = {}
for d in sorted(run.iterdir()):
    m = re.match(r"r(\d+)-(CLOSED-B|CLOSED|OPEN)-try(\d+)$", d.name)
    if not m or not (d / "start").exists():
        continue
    key = (int(m.group(1)), m.group(2))
    if key not in arms or int(m.group(3)) > arms[key][0]:
        arms[key] = (int(m.group(3)), d)
all_ok = True
for (rep, arm), (tr, d) in sorted(arms.items()):
    start = (d / "start").stat().st_mtime
    end = max(p.stat().st_mtime for p in d.rglob("*") if p.is_file())
    if fmt == "jsonl":
        inwin = [s for s in samples if start <= s["t"] <= end]
    else:
        day0 = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
        conv = lambda s: datetime.strptime(day0 + " " + s["hms"], "%Y-%m-%d %H:%M:%S").timestamp()
        inwin = [dict(s, t=conv(s)) for s in samples if start - 1 <= conv(s) <= end + 1]
    max_load = max((s["load1"] for s in inwin), default=None)
    over = [s["hms"] for s in inwin if s["load1"] > 5.0]
    hogs = []
    if fmt == "jsonl":
        runs = {}
        for s in inwin:
            seen = set()
            for p in s["procs"]:
                if p["pcpu"] > 50 and not p["lane"] and not p["exempt"]:
                    seen.add(p["pid"])
                    r = runs.setdefault(p["pid"], {"first": s["t"], "last": s["t"], "command": p["command"], "max": p["pcpu"]})
                    r["last"] = s["t"]; r["max"] = max(r["max"], p["pcpu"])
            for pid in list(runs):
                if pid not in seen:
                    r = runs.pop(pid)
                    if r["last"] - r["first"] > 10: hogs.append(r)
        hogs += [r for r in runs.values() if r["last"] - r["first"] > 10]
    valid = bool(inwin) and not over and not hogs
    all_ok &= valid
    print(json.dumps({"repeat": rep, "arm": arm, "try": tr, "start": datetime.fromtimestamp(start).strftime("%H:%M:%S"),
                      "end": datetime.fromtimestamp(end).strftime("%H:%M:%S"), "samples": len(inwin), "max_load1": max_load,
                      "load1_over_5": over, "hogs_over_50pct_10s": hogs if fmt == "jsonl" else "NOT CHECKABLE (load1-only log)",
                      "valid": valid}))
print("ARM_VALIDITY", "ALL VALID" if all_ok else "INVALID PRESENT", len(arms), "arms")
sys.exit(0 if all_ok else 1)
