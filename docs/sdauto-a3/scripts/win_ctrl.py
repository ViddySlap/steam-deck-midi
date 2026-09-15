"""sdauto A3: disposable sender. Attach to <pid>'s console and send one console control event."""
import ctypes
import ctypes.wintypes as wt
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.AttachConsole.argtypes = [wt.DWORD]
k32.GenerateConsoleCtrlEvent.argtypes = [wt.DWORD, wt.DWORD]
k32.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wt.BOOL]
k32.GetConsoleProcessList.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD]
pid, event = int(sys.argv[1]), int(sys.argv[2])
allowed = {int(x) for x in sys.argv[3].split(",")}
out = [f"free={k32.FreeConsole()}"]
out.append(f"attach={k32.AttachConsole(pid)} err={ctypes.get_last_error()}")
buf = (wt.DWORD * 64)()
n = k32.GetConsoleProcessList(buf, 64)
attached = sorted(buf[i] for i in range(min(n, 64)))
import os
others = [p for p in attached if p != os.getpid() and p not in allowed]
out.append(f"attached={attached} foreign={others}")
if others or not attached:
    open(sys.argv[4], "w").write(" ".join(out) + " REFUSED\n")
    sys.exit(3)
out.append(f"ignore_ctrl_c={k32.SetConsoleCtrlHandler(None, True)}")
open(sys.argv[4], "w").write(" ".join(out) + "\n")
ok = k32.GenerateConsoleCtrlEvent(event, 0)
with open(sys.argv[4], "a") as fh:
    fh.write(f"generate={ok} err={ctypes.get_last_error()}\n")
sys.exit(0 if ok else 4)
