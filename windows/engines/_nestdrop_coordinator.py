"""Shared coordinator for NestDrop queue activate+btSpace sequences.

NestDrop's per-deck btSpace advances whichever queue is currently
"active" on that deck. Activation is set by `/Queue/Queue<N> INT32(1)`.
If two engines (e.g. nestdrop_engine and gyro_feedback) both fire
`activate Queue X` -> sleep -> `btSpace Deck N` in parallel, their
OSC sends interleave and one engine's btSpace targets the other
engine's queue. We've seen Queue 3 advance when L4 was pressed and
Queue 5 toggle when L_PAD_UP was pressed because of this race.

The fix: serialize the (activate, sleep, btSpace) sequence across
every engine that talks to NestDrop. A single module-level lock
acquired around each fire.

The sleep happens INSIDE the locked region so other engines wait
their full ~100ms turn rather than queue jumping mid-activation.
At ~100ms per fire that means a burst of rapid button presses can
queue up briefly, but the user-perceived latency for a single press
is unaffected.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)

# Module-level lock shared by every engine that fires NestDrop
# activate+btSpace pairs. Import this lock and acquire it around the
# pair.
NESTDROP_QUEUE_FIRE_LOCK = threading.Lock()


def fire_queue_advance(
    osc_send: Callable[[str, Any], None],
    queue_path: str,
    btspace_path: str,
    activate_delay_seconds: float,
    sleep: Callable[[float], None],
    deactivate_paths: tuple[str, ...] = (),
) -> None:
    """Atomically fire deactivates, queue activate, then btSpace.

    NestDrop allows multiple queues to be active on the same deck
    simultaneously. If two engines both activate their own queue
    without deactivating the previously-active one, the btSpace
    advances whichever queue NestDrop happens to pick (typically
    the most-recently-clicked, not necessarily ours). Result: L4
    press toggles Queue 5 sprite AND L_PAD_UP somehow advances
    Queue 5 too.

    Fix: pass each engine's "siblings on the same deck" as
    `deactivate_paths`. The coordinator sends `<sibling> INT(0)`
    for each sibling, then `<queue_path> INT(1)` to activate the
    target, then `<btspace_path> INT(1)` to advance. All inside
    the lock so a second engine can't race in mid-sequence.
    """
    with NESTDROP_QUEUE_FIRE_LOCK:
        for sibling in deactivate_paths:
            osc_send(sibling, 0)
        osc_send(queue_path, 1)
        if activate_delay_seconds > 0:
            sleep(activate_delay_seconds)
        osc_send(btspace_path, 1)
