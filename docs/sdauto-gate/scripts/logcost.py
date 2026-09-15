# sdauto gate diagnostic: per-record cost of the logging a --no-engines timing arm does on EVERY axis event
# (receiver.py `LOGGER.exception("engine_registry.on_axis_event failed")`), configured as windows.win_recv.main does.
import logging, sys, time, os
sys.path.insert(0, sys.argv[1])
ring = sys.argv[2] == "ring"
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=open(os.devnull, "w"))
if ring:
    from windows.log_ring import install_ring_handler
    install_ring_handler()
log = logging.getLogger("windows.receiver")
N = 15246
def one():
    try:
        None.on_axis_event
    except Exception:
        log.exception("engine_registry.on_axis_event failed")
for _ in range(500): one()
best = []
for rep in range(5):
    t = time.perf_counter_ns()
    for _ in range(N): one()
    best.append((time.perf_counter_ns() - t) / N / 1000)
print(("ring" if ring else "no-ring"), "per record us: min %.1f median %.1f" % (min(best), sorted(best)[2]), "handlers", [type(h).__name__ for h in logging.getLogger().handlers])
