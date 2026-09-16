"""Select and pace a short timing workload from the pinned sdwin Deck script."""
import argparse
from collections import Counter
import math
from pathlib import Path
import json

from deck_script import canonical, packet, read_json, seal, sender_axes, sha, validate
from timing_subset_check import check_subset

DECK_SHA256 = '4833fd173df64ef6782422cd3264291f47e9ff8480b1517a703d518991182c34'
WORST_CASE = 'simultaneous-sticks-triggers-60hz'
SIMULTANEOUS_AXES = ('L_STICK_X_AXIS', 'L_STICK_Y_AXIS', 'R_STICK_X_AXIS',
                     'R_STICK_Y_AXIS', 'L_TRIGGER_PRESSURE', 'R_TRIGGER_PRESSURE')
SWEEP_BLOCKS = 14  # 14 * lcm(20, 18) ticks = 42 seconds at the sender rate.


def generate(deck, sender):
    validate(deck)
    if deck['sha256'] != DECK_SHA256:
        raise ValueError('Full Deck script pin changed; review required')
    axes, interval = sender_axes(sender)
    if interval != deck['parameters']['fast_axis_interval_ns'] or axes != deck['axes']:
        raise ValueError('Sender rate/ranges differ from pinned Deck script')
    sweeps = {action: [s['event'] for s in deck['steps']
                       if s['phase'] == 'axis-60hz' and s['event']['action'] == action]
              for action in axes}
    steps, segments = [], []
    now = 100_000_000

    def add(event, duration, segment, **extra):
        nonlocal now
        steps.append({'id': len(steps), 'at_ns': now, 'event': dict(event),
                      'phase': 'axis-60hz' if event['kind'] == 'axis' else 'tap',
                      'segment': segment, **extra})
        now += duration

    # Exactly one original down/up pair per button-like ID. Timer probes still
    # advance fades/staged work; overlapping timers retain their causal input.
    for action in deck['actions']:
        if action in axes:
            continue
        for state, dwell in (('down', 100_000_000), ('up', 250_000_000)):
            event = next(s['event'] for s in deck['steps']
                         if s['event'] == {'kind': 'action', 'action': action, 'state': state})
            add(event, dwell, 'buttons-once')
    horizon = round(deck['parameters']['gap_seconds'] * 1e9)
    now += horizon  # All button timers settle before the worst-case segment.
    start = now
    ticks = SWEEP_BLOCKS * math.lcm(*(len(sweeps[a]) for a in SIMULTANEOUS_AXES))
    for tick in range(ticks):
        # One event per axis per tick. 1 ns separates packet timestamps solely
        # to preserve the existing strictly ordered script format.
        for index, action in enumerate(SIMULTANEOUS_AXES):
            add(sweeps[action][tick % len(sweeps[action])],
                interval - (len(SIMULTANEOUS_AXES) - 1) if index == len(SIMULTANEOUS_AXES) - 1 else 1,
                WORST_CASE, tick=tick)
    segments.append({'name': WORST_CASE, 'start_ns': start, 'end_ns': now,
                     'axes': list(SIMULTANEOUS_AXES), 'ticks': ticks, 'interval_ns': interval})
    for action in axes:
        if action not in SIMULTANEOUS_AXES:
            for event in sweeps[action]:
                add(event, interval, 'other-axes-60hz')
    now += horizon
    packets = []
    timer_tick = deck['parameters']['timer_tick_ns']
    for index, step in enumerate(steps):
        end = steps[index + 1]['at_ns'] if index + 1 < len(steps) else now
        events = [(step['at_ns'], step['event'])]
        events += [(t, {'kind': 'heartbeat'}) for t in range(step['at_ns'] + timer_tick, end, timer_tick)]
        for timestamp, event in events:
            packets.append({'at_ns': timestamp, 'step': step['id'],
                            'hex': packet(event, len(packets) + 1).hex()})
    packets.append({'at_ns': now, 'step': steps[-1]['id'],
                    'hex': packet({'kind': 'heartbeat'}, len(packets) + 1).hex()})
    result = seal({'schema': 'sdlive-timing-script/1', 'actions': deck['actions'], 'axes': axes,
                   'source_deck_sha256': deck['sha256'], 'source_sha256': deck['source_sha256'],
                   'parameters': {'fast_axis_interval_ns': interval, 'timer_tick_ns': timer_tick,
                                  'tap_seconds': .1, 'release_gap_seconds': .25,
                                  'timer_horizon_seconds': horizon / 1e9, 'sweep_blocks': SWEEP_BLOCKS},
                   'worst_case_segment': WORST_CASE, 'segments': segments,
                   'duration_ns': now, 'steps': steps, 'packets': packets})
    check_subset(result, deck)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deck_script', type=Path)
    parser.add_argument('--sender', type=Path, default=Path(__file__).resolve().parents[2] / 'deck/xinput_send.py')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    script = generate(read_json(args.deck_script), args.sender)
    # A release workload is written once. Regeneration goes to a fresh scratch
    # file and is compared byte-for-byte; never overwrite the pinned artifact.
    with args.out.open('xb') as output:
        output.write(canonical(script) + b'\n')
    print(json.dumps({'script_sha256': script['sha256'], 'file_sha256': sha(args.out.read_bytes()),
                      'steps_by_kind': dict(Counter(s['event']['kind'] for s in script['steps'])),
                      'packets_by_kind': dict(Counter(json.loads(bytes.fromhex(p['hex']))['kind'] for p in script['packets'])),
                      'seconds': script['duration_ns'] / 1e9, 'segments': script['segments']}))


if __name__ == '__main__':
    main()
