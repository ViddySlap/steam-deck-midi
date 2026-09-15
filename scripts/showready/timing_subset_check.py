"""Check every timing packet encoding against the pinned full Deck script."""
import argparse
import json
from pathlib import Path

from deck_script import canonical, read_json, validate


def encoding(event):
    # Ignore ONLY sequence: kind, action, state/value and any extra wire keys
    # must match. Canonical JSON distinguishes integer, boolean and float values.
    return canonical({k: v for k, v in event.items() if k != 'seq'})


def check_subset(timing, deck):
    for script in (timing, deck):
        validate(script)
        if not script['steps'] or not script['packets']:
            raise ValueError('Empty script cannot prove a subset')
    allowed = {encoding(json.loads(bytes.fromhex(p['hex']))) for p in deck['packets']}
    at = {}
    for row in timing['packets']:
        event = json.loads(bytes.fromhex(row['hex']))
        if encoding(event) not in allowed:
            raise ValueError('Foreign encoding at packet ' + str(event['seq']) + ': ' + encoding(event).decode())
        at[row['at_ns']] = (row['step'], encoding(event))
    for step in timing['steps']:
        encoded = encoding(step['event'])
        if encoded not in allowed:
            raise ValueError('Foreign encoding at step ' + str(step['id']))
        if at.get(step['at_ns']) != (step['id'], encoded):
            raise ValueError('Step/packet encoding mismatch at step ' + str(step['id']))
    return {'passed': True, 'steps': len(timing['steps']), 'packets': len(timing['packets']),
            'distinct_encodings': len({encoding(s['event']) for s in timing['steps']}),
            'deck_sha256': deck['sha256'], 'timing_sha256': timing['sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('timing_script', type=Path)
    parser.add_argument('deck_script', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check_subset(read_json(args.timing_script), read_json(args.deck_script))))
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
