"""sdauto A3 Windows F2 arm driver (runs on the laptop with the clone venv python).

Starts one bridge (--dry-run --no-ui --no-engines --no-pulse --no-osc-relay) in a
PRIVATE console, records its pid tree, measures process CPU time over 30 s with
GetProcessTimes, then tries to stop it: console CTRL_C_EVENT, then CTRL_BREAK_EVENT,
then TerminateProcess on the recorded tree only. Writes a JSON result; never prints.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import signal
import socket
import subprocess
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
k32.WaitForSingleObject.restype = wt.DWORD
k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
k32.GetConsoleProcessList.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD]
k32.GenerateConsoleCtrlEvent.argtypes = [wt.DWORD, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
HANDLER = ctypes.WINFUNCTYPE(wt.BOOL, wt.DWORD)
k32.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wt.BOOL]
k32.AttachConsole.argtypes = [wt.DWORD]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", wt.WCHAR * 260)]


k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


def process_table():
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    rows = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        rows.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return rows


def descendants(root):
    rows = process_table()
    found = [root]
    changed = True
    while changed:
        changed = False
        for pid, ppid, _ in rows:
            if ppid in found and pid not in found:
                found.append(pid)
                changed = True
    return found


def image(handle):
    buf = ctypes.create_unicode_buffer(1024)
    size = wt.DWORD(1024)
    if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
        return buf.value
    return None


def cpu_seconds(handle):
    c, e, k, u = (ctypes.c_ulonglong() for _ in range(4))
    if not k32.GetProcessTimes(handle, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
        return None
    return (k.value + u.value) / 1e7


def exit_code(handle):
    code = wt.DWORD()
    k32.GetExitCodeProcess(handle, ctypes.byref(code))
    return code.value


def main():
    a = json.loads(open(sys.argv[1], encoding="utf-8").read())
    out_path = a["out"]
    result = {"label": a["label"], "driver_pid": os.getpid(), "argv": None, "events": []}
    events = result["events"]

    def note(msg):
        events.append([round(time.monotonic(), 3), msg])

    def save():
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

    received = []
    result["console"] = {"enable_ctrl_c": bool(a.get("enable_ctrl_c"))}
    if a.get("enable_ctrl_c"):
        # Clear an inherited "ignore CTRL+C" attribute so the bridge inherits normal Ctrl-C processing.
        result["console"]["SetConsoleCtrlHandler_NULL_FALSE"] = k32.SetConsoleCtrlHandler(None, False)

    env = dict(os.environ)
    env["BROWSER"] = a["browser"]
    env.pop("PYSTRAY_BACKEND", None)
    env["TEMP"] = env["TMP"] = a["work"]
    argv = [a["python"], "-B", "-u", "-m", "windows.win_recv", "--listen", f"127.0.0.1:{a['udp']}",
            "--map", a["map"], "--midi-port", "DECK_IN", "--timeout", "2.0", "--ui-port", str(a["ui"]),
            "--dry-run", "--no-ui", "--no-engines", "--no-pulse", "--no-osc-relay"] + (
                [a["extra"]] if isinstance(a["extra"], str) else list(a["extra"] or []))
    result["argv"] = argv
    log = open(a["log"], "wb")
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    # The bridge gets its OWN hidden console; the driver attaches to it only to send events.
    proc = subprocess.Popen(argv, cwd=a["tree"], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=si)
    note(f"popen pid {proc.pid}")

    # Record the owned tree as soon as the interpreter child exists.
    handles = {}
    deadline = time.monotonic() + 20
    booted = False
    while time.monotonic() < deadline:
        for pid in descendants(proc.pid):
            if pid not in handles:
                h = k32.OpenProcess(0x1000 | 0x100000 | 0x0001, False, pid)
                if h:
                    handles[pid] = h
        with open(a["record"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(str(p) for p in [os.getpid()] + list(handles)) + "\n")
        text = open(a["log"], "rb").read().decode("utf-8", "replace")
        if "listening on udp" in text and len(handles) >= 1:
            booted = True
            break
        if proc.poll() is not None:
            break
        time.sleep(0.25)
    time.sleep(0.5)
    for pid in descendants(proc.pid):
        if pid not in handles:
            h = k32.OpenProcess(0x1000 | 0x100000 | 0x0001, False, pid)
            if h:
                handles[pid] = h
    with open(a["record"], "w", encoding="utf-8") as fh:
        fh.write("\n".join(str(p) for p in [os.getpid()] + list(handles)) + "\n")
    result["booted"] = booted
    result["tree"] = [{"pid": pid, "image": image(h)} for pid, h in handles.items()]
    save()
    if not booted:
        note("boot failed")
    else:
        time.sleep(2)
        t0 = time.perf_counter()
        base = {pid: cpu_seconds(h) for pid, h in handles.items()}
        per_second = []
        prev = dict(base)
        for _ in range(30):
            time.sleep(1)
            now = {pid: cpu_seconds(h) for pid, h in handles.items()}
            per_second.append({str(pid): round(now[pid] - prev[pid], 4) for pid in handles})
            prev = now
        t1 = time.perf_counter()
        wall = t1 - t0
        cores = os.cpu_count()
        rows = []
        for pid, h in handles.items():
            d = prev[pid] - base[pid]
            rows.append({"pid": pid, "image": image(h), "cpu_seconds_before": base[pid],
                         "cpu_seconds_after": prev[pid], "cpu_seconds": round(d, 4),
                         "pct_of_one_core": round(100 * d / wall, 2),
                         "pct_of_all_cores": round(100 * d / wall / cores, 3)})
        total = sum(r["cpu_seconds"] for r in rows)
        result["cpu"] = {"wall_seconds": round(wall, 3), "logical_cores": cores, "per_pid": rows,
                         "tree_cpu_seconds": round(total, 4),
                         "tree_pct_of_one_core": round(100 * total / wall, 2),
                         "tree_pct_of_all_cores": round(100 * total / wall / cores, 3),
                         "per_second_deltas": per_second}
        save()

    # Stop sequence. Console events only when the console holds nothing but this driver's tree.
    result["console"]["driver_executable"] = sys.executable

    def all_gone(ms):
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            if all(k32.WaitForSingleObject(h, 0) == 0 for h in handles.values()):
                return True
            time.sleep(0.05)
        return all(k32.WaitForSingleObject(h, 0) == 0 for h in handles.values())

    stops = []
    owned_csv = ",".join(str(p) for p in handles)
    for name, event in (("CTRL_C_EVENT", 0), ("CTRL_BREAK_EVENT", 1)):
        if all_gone(0):
            break
        t = time.monotonic()
        sender_log = a["out"] + f".{name}.txt"
        sender = subprocess.run([sys.executable, "-B", a["ctrl"], str(proc.pid), str(event), owned_csv, sender_log],
                                capture_output=True, text=True, timeout=20,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        gone = all_gone(5000)
        stops.append({"method": name, "sender_exit": sender.returncode,
                      "sender_log": open(sender_log).read() if os.path.exists(sender_log) else None,
                      "sender_stderr": sender.stderr[-500:], "tree_exited_within_5s": gone,
                      "elapsed": round(time.monotonic() - t, 3),
                      "exit_codes": {str(p): exit_code(h) for p, h in handles.items()}})
        result["stops"] = stops
        save()
    if not all_gone(0):
        t = time.monotonic()
        for pid in sorted(handles, reverse=True):
            if k32.WaitForSingleObject(handles[pid], 0) != 0:
                k32.TerminateProcess(handles[pid], 1)
        gone = all_gone(5000)
        stops.append({"method": "TerminateProcess(recorded tree)", "tree_exited_within_5s": gone,
                      "elapsed": round(time.monotonic() - t, 3),
                      "exit_codes": {str(p): exit_code(h) for p, h in handles.items()}})
    result["stops"] = stops
    result["driver_signals_received"] = received
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        pass
    result["popen_returncode"] = proc.returncode
    result["final_exit_codes"] = {str(p): exit_code(h) for p, h in handles.items()}
    result["all_gone"] = all_gone(0)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", a["udp"]))
        result["udp_port_rebind"] = "ok"
    except OSError as exc:
        result["udp_port_rebind"] = f"failed: {exc}"
    finally:
        s.close()
    log.close()
    result["log_tail"] = open(a["log"], "rb").read().decode("utf-8", "replace").splitlines()[-6:]
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
