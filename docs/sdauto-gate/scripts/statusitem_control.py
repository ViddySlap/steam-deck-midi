# sdauto gate: positive control for the status-item detector: a Python process that owns a real NSStatusItem (main thread).
import subprocess, os, threading
import AppKit, Foundation
app = AppKit.NSApplication.sharedApplication()
app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSVariableStatusItemLength)
item.button().setTitle_("GATE")
def probe():
    import time; time.sleep(2)
    r1 = subprocess.run(['/tmp/sdauto-gate/s3/statusitems', str(os.getpid())], capture_output=True, text=True).stdout.strip()
    print("WITH_ITEM", r1.splitlines()[-1], flush=True)
    AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(item)
    time.sleep(1.5)
    r2 = subprocess.run(['/tmp/sdauto-gate/s3/statusitems', str(os.getpid())], capture_output=True, text=True).stdout.strip()
    print("AFTER_REMOVE", r2.splitlines()[-1], flush=True)
    os._exit(0)
threading.Thread(target=probe, daemon=True).start()
app.run()
