"""Time the receiver-thread task of PUT /api/engines/<type>/config.

Usage (run root): .venv/bin/python -B docs/sdauto-a2/swap_cost.py
Loads a temp tree of loopback-rewritten factory stanzas (OSC to a bound
local UDP sink, REST to a closed local TCP port, so REST fails fast with
connection refused), then times ReceiverTaskQueue.drain() around N PUTs
per live-swappable type. This is how long MIDI dispatch waits during a PUT
on this machine when Resolume is not answering REST instantly-refused; an
unresponsive REST host adds up to rest.timeout_seconds per REST read.
"""

from __future__ import annotations

import json
import re
import socket
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests._engine_helpers import RecordingMidiOut  # noqa: E402
from tests.test_ui_server import _make_server  # noqa: E402
from windows.engine_config_api import LIVE_SWAPPABLE_TYPES  # noqa: E402
from windows.engines.registry import load_engines  # noqa: E402
from windows.receiver_tasks import ReceiverTaskQueue  # noqa: E402

N = 20


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sink:
        sink.bind(("127.0.0.1", 0))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            rest = f"http://127.0.0.1:{s.getsockname()[1]}"
        root = Path(tmp)
        (root / "engines").mkdir()
        (root / "engines.factory").mkdir()
        sink_port = sink.getsockname()[1]

        def loopback(node):
            if isinstance(node, dict):
                out = {}
                for key, value in node.items():
                    if key in ("host", "camera_nic_ip"):
                        out[key] = "127.0.0.1"
                    elif key in ("port", "visca_port") and isinstance(value, int):
                        out[key] = sink_port
                    elif key == "base_url":
                        out[key] = rest
                    elif key == "cameras" and isinstance(value, dict):
                        out[key] = {k: "127.0.0.1" for k in value}
                    elif key == "rest" and isinstance(value, dict):
                        out[key] = {**loopback(value), "timeout_seconds": 1.5}
                    else:
                        out[key] = loopback(value)
                return out
            if isinstance(node, list):
                return [loopback(v) for v in node]
            return node

        for type_name in sorted(LIVE_SWAPPABLE_TYPES):
            raw = json.loads((ROOT / f"config/engines.factory/{type_name}.json").read_text(encoding="utf-8"))
            text = json.dumps(loopback(raw))
            foreign = [ip for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) if ip != "127.0.0.1"]
            if foreign:
                raise SystemExit(f"refusing to run: {type_name} still targets {foreign}")
            (root / "engines.factory" / f"{type_name}.json").write_text(text, encoding="utf-8")
        registry = load_engines(root / "engines", RecordingMidiOut(), state_dir=root / "state")
        server, *_ = _make_server()
        server.engine_registry = registry
        tasks = ReceiverTaskQueue()
        server.receiver_tasks = tasks
        client = server._app.test_client()
        timings: dict[str, list[float]] = {}
        stop = threading.Event()
        current = [None]

        def receiver():
            while not stop.is_set():
                start = time.perf_counter()
                ran = tasks.drain()
                if ran:
                    timings.setdefault(current[0], []).append((time.perf_counter() - start) * 1000.0)
                time.sleep(0.001)

        thread = threading.Thread(target=receiver)
        thread.start()
        statuses = {}
        try:
            for type_name in sorted(LIVE_SWAPPABLE_TYPES):
                spec = json.loads((root / "engines.factory" / f"{type_name}.json").read_text(encoding="utf-8"))
                current[0] = type_name
                for _ in range(N):
                    statuses.setdefault(type_name, set()).add(
                        client.put(f"/api/engines/{type_name}/config", json=spec).status_code)
        finally:
            stop.set()
            thread.join()
            registry.shutdown()
        result = {t: {"statuses": sorted(statuses[t]), "n": len(v),
                      "p50_ms": round(statistics.median(v), 3), "max_ms": round(max(v), 3)}
                  for t, v in sorted(timings.items())}
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
