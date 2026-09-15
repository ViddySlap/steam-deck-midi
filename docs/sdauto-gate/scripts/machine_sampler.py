"""MASTER 13 15:21 (3) whole-machine sampler: every <= 5 s, load1 and every process above 20% of one core.

  machine_sampler.py --out samples.jsonl --lane-root PID --stop FILE [--interval 5]

Each line: {"t": epoch, "hms", "load1", "procs": [{pid, ppid, pcpu, lane, exempt, command}]}. lane = the pid is the
lane root or a descendant of it at sample time (the arm's own recorded tree: timing_ab, bridge, node client,
Chromium). exempt = WindowServer or kernel_task (recorded, not counted). Stops when FILE exists.
"""
import argparse, json, os, subprocess, time

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True); ap.add_argument("--lane-root", type=int, required=True)
ap.add_argument("--stop", required=True); ap.add_argument("--interval", type=float, default=5.0)
a = ap.parse_args()
with open(a.out, "a", buffering=1) as f:
    while not os.path.exists(a.stop):
        t = time.time()
        load1 = float(subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True).stdout.split()[1])
        rows = []
        for line in subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pcpu=,command="], capture_output=True, text=True).stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            rows.append((int(parts[0]), int(parts[1]), float(parts[2]), parts[3]))
        children = {}
        for pid, ppid, _, _ in rows:
            children.setdefault(ppid, []).append(pid)
        lane, stack = set(), [a.lane_root]
        while stack:
            p = stack.pop()
            if p in lane:
                continue
            lane.add(p)
            stack.extend(children.get(p, []))
        procs = []
        for pid, ppid, pcpu, cmd in rows:
            if pcpu > 20.0:
                name = os.path.basename(cmd.split()[0]) if cmd else ""
                procs.append({"pid": pid, "ppid": ppid, "pcpu": pcpu, "lane": pid in lane,
                              "exempt": name in ("WindowServer", "kernel_task"), "command": cmd[:200]})
        f.write(json.dumps({"t": t, "hms": time.strftime("%H:%M:%S", time.localtime(t)), "load1": load1, "procs": procs}) + "\n")
        time.sleep(max(0.0, a.interval - (time.time() - t)))
