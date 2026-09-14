import sys; sys.argv=["x"]
exec(open("/tmp/sdcore2-gate/scripts/boot_arms.py").read().split("res = {}")[0])
BASE.mkdir(parents=True, exist_ok=True)
t = export("f809be1", "C0-f809be1-fresh")
r = run_arm("C0-f809be1-fresh", t, LAUNCHER + DRY, wait=6.0)
print("CONTROL", r)
