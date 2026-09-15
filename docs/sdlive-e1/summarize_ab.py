"""Check full capture bytes and packet/cleanup evidence, not just verdict text."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
output = []
for label in ("edm", "ptz", "default"):
    source = root / f"ab-{label}.json.gz"
    with gzip.open(source, "rt") as handle:
        result = json.load(handle)
    assert result["passed"] and not result.get("error")
    assert result["clock"] == "script" and result["wall_speed"] == 1
    streams = {}
    for name, arm in result["arms"].items():
        assert arm["cleanup"]["pid_gone"]
        assert arm["received"]["packets_received"] == len(result["script"]["packets"])
        assert arm["received"]["packet_stream_sha256"] == result["packet_stream_sha256"]
        streams[name] = [[row["step"], row["bytes"]] for row in arm["records"] if row["record"] == "midi"]
        assert streams[name]
    for name, comparison in result["comparisons"].items():
        assert streams["A"] == streams[name]
        assert comparison["passed"] and comparison["identical"]
        assert comparison["totals"]["mappings_exercised"] == comparison["totals"]["mappings"]
        assert not comparison["different_mappings"] and not comparison["unexercised_mappings"]
    for arm in result["pacing"].values():
        assert all(phase["no_overspeed"] for phase in arm.values())
    output.append({"preset": label, "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                   "candidate": result["candidate"], "script_sha256": result["script_sha256"],
                   "packet_stream_sha256": result["packet_stream_sha256"], "wall_speed": result["wall_speed"],
                   "clock": result["clock"], "steps": len(result["script"]["steps"]),
                   "packets_per_arm": len(result["script"]["packets"]),
                   "comparisons": {k: v["totals"] for k, v in result["comparisons"].items()},
                   "raw_step_bytes_identical": True, "mapping_coverage_complete": True,
                   "cleanup": {k: {"pid": v["received"]["pid"], **v["cleanup"]} for k, v in result["arms"].items()},
                   "latency_credit": "NONE: CPU inventory unreadable; bar 1 byte/pacing evidence only"})
summary = {"command": [sys.executable, *sys.argv], "results": output, "status": "PASS"}
Path(sys.argv[2]).write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
print(json.dumps(summary, indent=2))
