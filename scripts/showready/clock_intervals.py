"""P3(e): inter-message intervals at the MIDI output seam, on the bridge's REAL clock.

WHAT IT MEASURES. A relative_cc repeat and a macro fade are both SCHEDULED
against the receiver's own clock. If that clock advances in 15.625 ms steps
(Windows `time.monotonic`, GetTickCount64) a 40 ms repeat cannot land on 40 ms,
and a fade advances in visible jumps. This records the wall time of every MIDI
message the receiver emits and reports the intervals between them.

THREE THINGS THAT MAKE IT A MEASUREMENT AND NOT A STORY:

1. THE RECEIVER RUNS ON ITS OWN DEFAULT CLOCK. Nothing here passes `clock=` and
   nothing passes `now=`. That is the whole point: this instrument is run
   against two trees (BASE OF LAP and HEAD) whose DEFAULT is the only thing
   that differs, so it must not name a clock. It therefore also works against
   a tree that has no windows/clock.py at all.

   This is also why the timing instrument's `--clock script` mode is wrong for
   this question: it drives the receiver from the script's own timeline and
   bypasses the receiver's clock, which is the thing under test.

2. THE STOPWATCH IS ALWAYS time.perf_counter, ON BOTH ARMS. If the stopwatch
   shared the clock under test, the BASE arm would report smooth intervals
   because the ruler and the thing being measured would be quantized together.
   A coarse clock must be measured with a fine one.

3. THE POLL IS FINER THAN THE EFFECT. The loop advances the receiver every
   --poll-ms (default 1 ms), well under both the 15.625 ms tick and the 40 ms
   target, so any quantization in the output comes from the receiver's clock
   and not from this loop's cadence. The value is recorded in the output.

No MIDI port is opened: MidiOut is replaced by a recorder, exactly as the bar 1
instrument does. Nothing here binds a socket or starts a thread.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from windows.config import MacroCCMapping, MacroSettings, RelativeCCMapping  # noqa: E402
from windows.receiver import ActionReceiver  # noqa: E402

ADDR = ("127.0.0.1", 45999)


class RecordingMidiOut:
    """Records (perf_counter, kind, channel, target, value) for every message."""

    def __init__(self) -> None:
        self.events: list[tuple[float, str, int, int, int]] = []

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.events.append((time.perf_counter(), "note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int) -> None:
        self.events.append((time.perf_counter(), "note_off", channel, note, velocity))

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.events.append((time.perf_counter(), "cc", channel, control, value))

    def panic(self) -> None:  # pragma: no cover - never driven here
        pass

    def close(self) -> None:  # pragma: no cover
        pass


def clock_info() -> dict:
    out = {}
    for name in ("monotonic", "perf_counter"):
        info = time.get_clock_info(name)
        out[name] = {
            "implementation": info.implementation,
            "resolution": info.resolution,
            "monotonic": info.monotonic,
            "adjustable": info.adjustable,
        }
    return out


def run_relative_cc(seconds: float, poll: float, repeat_ms: int) -> tuple[RecordingMidiOut, dict]:
    midi = RecordingMidiOut()
    receiver = ActionReceiver(
        midi,
        {
            "R_PAD_RIGHT": RelativeCCMapping(
                action="R_PAD_RIGHT",
                kind="relative_cc",
                channel=0,
                cc=47,
                step_value=1,
                repeat_interval_ms=repeat_ms,
            )
        },
        timeout_seconds=seconds * 10,
    )
    receiver.handle_datagram(b'{"action":"R_PAD_RIGHT","state":"down","seq":1}', ADDR)
    deadline = time.perf_counter() + seconds
    polls = 0
    while time.perf_counter() < deadline:
        receiver.advance_relative_ccs()
        polls += 1
        time.sleep(poll)
    return midi, {"target_interval_s": repeat_ms / 1000.0, "polls": polls}


def run_fade(seconds: float, poll: float, fade_s: float, update_hz: int) -> tuple[RecordingMidiOut, dict]:
    midi = RecordingMidiOut()
    receiver = ActionReceiver(
        midi,
        {
            "DPAD_DOWN_LONG_PRESS": MacroCCMapping(
                action="DPAD_DOWN_LONG_PRESS",
                kind="macro_cc",
                channel=0,
                cc=20,
                gesture="long_press",
            )
        },
        timeout_seconds=seconds * 10,
        macro_settings=MacroSettings(fade_duration_seconds=fade_s, update_hz=update_hz),
    )
    receiver.handle_datagram(b'{"action":"DPAD_DOWN_LONG_PRESS","state":"down","seq":1}', ADDR)
    deadline = time.perf_counter() + seconds
    polls = 0
    while time.perf_counter() < deadline:
        receiver.advance_fades()
        polls += 1
        time.sleep(poll)
    return midi, {"target_interval_s": 1.0 / update_hz, "polls": polls}


def summarize(events, extra: dict, poll: float) -> dict:
    stamps = [event[0] for event in events]
    intervals = [round(b - a, 9) for a, b in zip(stamps, stamps[1:])]
    values = [event[4] for event in events]
    summary = {
        "messages": len(events),
        "intervals": len(intervals),
        "poll_s": poll,
        **extra,
    }
    if intervals:
        ordered = sorted(intervals)
        summary.update(
            {
                "p50_ms": round(statistics.median(ordered) * 1000, 4),
                "p95_ms": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))] * 1000, 4),
                "max_ms": round(max(ordered) * 1000, 4),
                "min_ms": round(min(ordered) * 1000, 4),
                "distinct_rounded_ms": sorted({round(v * 1000, 3) for v in intervals}),
            }
        )
    summary["values"] = values
    summary["intervals_ms"] = [round(v * 1000, 4) for v in intervals]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--poll-ms", type=float, default=1.0)
    parser.add_argument("--repeat-ms", type=int, default=40)
    parser.add_argument("--fade-seconds", type=float, default=2.0)
    parser.add_argument("--update-hz", type=int, default=30)
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    poll = args.poll_ms / 1000.0
    rel_midi, rel_extra = run_relative_cc(args.seconds, poll, args.repeat_ms)
    fade_midi, fade_extra = run_fade(args.seconds, poll, args.fade_seconds, args.update_hz)

    # What the receiver's clock actually IS in this tree, read off the class
    # rather than assumed, so the record says which arm this is.
    import inspect

    default_clock = inspect.signature(ActionReceiver.__init__).parameters["clock"].default
    result = {
        "label": args.label,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "receiver_default_clock": f"{getattr(default_clock, '__module__', '?')}."
        f"{getattr(default_clock, '__qualname__', repr(default_clock))}",
        "clock_info": clock_info(),
        "relative_cc": summarize(rel_midi.events, rel_extra, poll),
        "fade": summarize(fade_midi.events, fade_extra, poll),
    }
    Path(args.out).write_text(json.dumps(result, indent=2))
    for arm in ("relative_cc", "fade"):
        block = result[arm]
        print(
            f"{args.label} {arm}: n={block['messages']} "
            f"p50={block.get('p50_ms')}ms p95={block.get('p95_ms')}ms max={block.get('max_ms')}ms "
            f"distinct={len(block.get('distinct_rounded_ms') or [])} "
            f"first={(block.get('distinct_rounded_ms') or [])[:6]}"
        )
    print(f"{args.label} receiver_default_clock={result['receiver_default_clock']}")
    print(f"{args.label} monotonic_resolution={result['clock_info']['monotonic']['resolution']}")
    print(f"{args.label} perf_counter_resolution={result['clock_info']['perf_counter']['resolution']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
