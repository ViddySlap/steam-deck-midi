"""Deterministic Deck packets. Standard library only; never imports an arm."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def action_ids(path):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    ids = []
    for line in lines:
        line = line.split('#', 1)[0].strip()
        if not line or line == 'actions:':
            continue
        if not re.fullmatch(r'- [A-Z][A-Z0-9_]*', line):
            raise ValueError('Unsupported actions.yaml line: ' + line)
        ids.append(line[2:])
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('Empty/duplicate Action IDs')
    return ids


def sender_axes(path):
    """Read static HID IDs/centers without loading X11 or HID libraries."""
    source = Path(path).read_text(encoding='utf-8')
    tree = ast.parse(source)
    reader = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'HidrawAxisReader')
    values = {n.targets[0].id: ast.literal_eval(n.value) for n in reader.body
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
              and n.targets[0].id in ('_STATIC_AXIS_MAP', '_GYRO_OFFSETS')}
    interval = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'AXIS_MIN_INTERVAL')
    if not isinstance(interval, ast.BinOp) or not isinstance(interval.op, ast.Div):
        raise ValueError('Review changed sender interval')
    seconds = ast.literal_eval(interval.left) / ast.literal_eval(interval.right)
    # These guards deliberately refuse source drift in the dynamic range paths.
    for fragment in ('struct.unpack_from("<h", data, offset)', 'struct.unpack_from("<H", data, offset)',
                     'value = raw - center', 'max(-32767, min(32767, round(self._gyro_position[action])))'):
        if fragment not in source:
            raise ValueError('Review changed sender range: ' + fragment)
    ranges = {name: [(-32768 if signed else 0) - center, (32767 if signed else 65535) - center]
              for name, _, center, signed in values['_STATIC_AXIS_MAP']}
    for name, _ in values['_GYRO_OFFSETS']:
        ranges[name] = [-32767, 32767]
    for name in re.findall(r'\("([LR]_PAD_[XY]_POS)", \d+\)', source):
        ranges[name] = [-32768, 32767]
    if len(ranges) != 13:
        raise ValueError('Review changed sender axis inventory')
    return ranges, round(seconds * 1_000_000_000)


def effective(raw, section=None):
    if 'sections' not in raw:
        return raw
    selected = raw['sections'][section]
    return {**selected, 'mappings': {**raw.get('shared', {}).get('mappings', {}), **selected['mappings']}}


# A lap's scratch is /tmp/sd<lap>-<link>/... (/private/tmp is the same directory on
# macOS). A pattern, not a hard-coded lap name, so a new lap needs no edit here - and
# still nothing outside that shape, so no arm can be pointed at the run root or a vault.
SCRATCH_PATTERN = re.compile(r'^/(?:private/)?tmp/sd[a-z0-9]+-[a-z0-9]+(?:/|$)')


def scratch_ok(path):
    """True only for a scratch under /tmp/sd<lap>-<link>/ or its /private/tmp form.

    A `..` segment is refused outright: a caller that has not resolved its path could
    otherwise satisfy the prefix and still land anywhere on the disk.
    """
    text = str(path)
    if '..' in text.split('/'):
        return False
    return bool(SCRATCH_PATTERN.match(text))


def verify_fixtures(root):
    """Verify BOTH W2 manifests and every recorded byte before consumption."""
    verified = {}
    for host, count in (('mac', 5), ('windows-installed', 11)):
        directory = (Path(root) / host).resolve()
        manifest = directory / 'MANIFEST.sha256'
        entries = read_json(manifest)['entries']
        if len(entries) != count:
            raise ValueError('Missing fixture observations: ' + host)
        seen = set()
        for row in entries:
            path = (directory / row['relative']).resolve()
            if not path.is_relative_to(directory) or path in seen:
                raise ValueError('Unsafe/duplicate fixture path')
            seen.add(path)
            data = path.read_bytes()
            digest = sha(data)
            if len(data) != row['bytes'] or any(digest != row[k] for k in
                    ('sha256_before', 'sha256_after', 'sha256_copy')):
                raise ValueError('Fixture hash mismatch: ' + str(path))
            verified[str(path)] = digest
        verified[str(manifest)] = sha(manifest.read_bytes())
    return verified


def delay_bound(documents):
    rows = []
    for label, document in documents:
        settings = document.get('macro_settings', {})
        for key, mapping in document['mappings'].items():
            if mapping['type'] == 'macro_cc' and mapping.get('gesture') != 'click':
                seconds = mapping.get('fade_duration_seconds', settings.get('fade_duration_seconds', 2.0))
                rows.append({'source': label + '/mappings/' + key + '/fade_duration_seconds', 'seconds': seconds})
            elif mapping['type'] == 'staged_note_macro':
                for field, default in (('macro_delay_ms', 80), ('modifier_hold_ms', 2000)):
                    seconds = mapping.get(field, settings.get(field, default)) / 1000
                    rows.append({'source': label + '/mappings/' + key + '/' + field, 'seconds': seconds})
    longest = max([r['seconds'] for r in rows] + [0])
    return longest, rows


def packet(event, seq):
    return canonical({**event, 'seq': seq})


def stream_digest(packets):
    digest = hashlib.sha256()
    for row in packets:
        payload = bytes.fromhex(row['hex'])
        digest.update(struct.pack('!I', len(payload)))
        digest.update(payload)
    return digest.hexdigest()


def seal(script):
    script.pop('sha256', None)
    script['packet_stream_sha256'] = stream_digest(script['packets'])
    script['sha256'] = sha(canonical(script))
    return script


def validate(script):
    bare = {k: v for k, v in script.items() if k != 'sha256'}
    if sha(canonical(bare)) != script['sha256'] or stream_digest(script['packets']) != script['packet_stream_sha256']:
        raise ValueError('Script digest mismatch')
    previous = -1
    for seq, row in enumerate(script['packets'], 1):
        if row['at_ns'] <= previous or json.loads(bytes.fromhex(row['hex']))['seq'] != seq:
            raise ValueError('Non-monotonic script')
        previous = row['at_ns']


def generate(actions, sender, documents):
    ids = action_ids(actions)
    axes, fast_ns = sender_axes(sender)
    if set(axes) - set(ids):
        raise ValueError('Sender axis absent from actions.yaml')
    longest, sources = delay_bound(documents)
    gap = round((longest + 0.25) * 1e9)
    steps = []
    now = 100_000_000

    def add(event, duration, phase):
        nonlocal now
        steps.append({'id': len(steps), 'at_ns': now, 'event': event, 'phase': phase})
        now += duration

    # Bridge relative_cc repeats while held; staged holds and macro fades also
    # outlive a tap. LONG_PRESS/LAYER_2 are independent Deck-selected IDs.
    for action in ids:
        if action in axes:
            continue
        for phase, dwell in (('tap', 100_000_000), ('hold', 1_600_000_000)):
            add({'kind': 'action', 'action': action, 'state': 'down'}, dwell, phase)
            add({'kind': 'action', 'action': action, 'state': 'up'}, gap, phase)
    for action in ids:
        if action not in axes:
            continue
        low, high = axes[action]
        points = sorted(set([round(low + (high - low) * i / 8) for i in range(9)] + [0]))
        sweep = points + points[-2::-1] + [0]
        for phase, interval in (('axis-60hz', fast_ns), ('axis-10hz', 100_000_000)):
            for i, value in enumerate(sweep):
                add({'kind': 'axis', 'action': action, 'value': value},
                    gap if i == len(sweep) - 1 else interval, phase)
    # Explicit deterministic timer probes, using legal protocol heartbeats.
    # At 10 ms they exercise staged polling; no product timer is disabled.
    packets = []
    for index, step in enumerate(steps):
        end = steps[index + 1]['at_ns'] if index + 1 < len(steps) else now
        events = [(step['at_ns'], step['event'])]
        events += [(t, {'kind': 'heartbeat'}) for t in range(step['at_ns'] + 10_000_000, end, 10_000_000)]
        for timestamp, event in events:
            packets.append({'at_ns': timestamp, 'step': step['id'], 'hex': packet(event, len(packets) + 1).hex()})
    packets.append({'at_ns': now, 'step': steps[-1]['id'], 'hex': packet({'kind': 'heartbeat'}, len(packets) + 1).hex()})
    return seal({'schema': 'sdwin-deck-script/1', 'actions': ids, 'axes': axes,
                 'parameters': {'fast_axis_interval_ns': fast_ns, 'slow_axis_interval_ns': 100_000_000,
                                'tap_seconds': 0.1, 'hold_seconds': 1.6, 'gap_seconds': gap / 1e9,
                                'longest_delay_seconds': longest, 'delay_sources': sources,
                                'timer_tick_ns': 10_000_000, 'axis_divisions': 8,
                                'range_note': 'Sender representable HID ranges; physical calibration not measured. Zero probes include sender-suppressed centers.'},
                 'source_sha256': {'actions.yaml': sha(Path(actions).read_bytes()), 'xinput_send.py': sha(Path(sender).read_bytes())},
                 'duration_ns': now, 'steps': steps, 'packets': packets})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    fixtures = args.fixtures or args.repo / '.showready/fixtures'
    verified = verify_fixtures(fixtures)
    documents = []
    for path in sorted(verified):
        if path.endswith(('.json', '.bak')):
            raw = read_json(path)
            if not isinstance(raw, dict):
                continue
            for name, doc in raw.get('sections', {'flat': raw}).items():
                if 'mappings' in doc:
                    documents.append((str(Path(path).relative_to(fixtures.resolve())) + ':' + name, doc))
    script = generate(args.repo / 'config/actions.yaml', args.repo / 'deck/xinput_send.py', documents)
    args.out.write_bytes(canonical(script) + b'\n')
    print(json.dumps({'script_sha256': script['sha256'], 'file_sha256': sha(args.out.read_bytes()),
                      'steps': len(script['steps']), 'packets': len(script['packets']), 'seconds': script['duration_ns'] / 1e9}))


if __name__ == '__main__':
    main()
