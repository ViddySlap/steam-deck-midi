"""E4 workload, power floor, interleaved pacing and segment population controls."""
import copy
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts/showready'))
import deck_script
import timing_ab as timing
import timing_script
from timing_subset_check import check_subset


def synthetic_runs(count=1000):
    script = {'worst_case_segment': 'six-axes', 'steps': [
        {'id': 0, 'segment': 'buttons'}, {'id': 1, 'segment': 'six-axes'}]}
    runs = []
    for name in timing.ARMS:
        samples = [{'record': 'midi', 'step': 1, 'cause_step': 0, 'bytes': [144, 36, 127], 'latency_ms': 100.0}
                   for _ in range(count - 4)]
        # Replay-step 0 deliberately disagrees with cause-step 1. Segment
        # attribution must follow the initiating input, including timed MIDI.
        samples += [{'record': 'midi', 'step': 0, 'cause_step': 1, 'bytes': [176, 1, value], 'latency_ms': float(value)}
                    for value in (1, 2, 3, 4)]
        runs.append({'name': name, 'repeat': 1, 'load_status': 'verified',
                     'arm': {'samples': samples, 'records': copy.deepcopy(samples), 'passed': True,
                             'snapshot_after': {'dropped': 0}, 'stream': {'dropped': 0}, 'live_valid': True}})
    return script, runs


class TimingScriptTests(unittest.TestCase):
    def test_sensitivity_delay_yields_until_two_ms_deadline(self):
        readings = iter([100, 100, 1000100, 2000099, 2000100])
        pauses = []
        timing.sensitivity_delay(clock=lambda: next(readings), pause=lambda: pauses.append(True))
        self.assertEqual(pauses, [True, True, True])
        with self.assertRaises(StopIteration):
            next(readings)

    def test_power_floor_999_is_invalid_and_blocks_otherwise_green_verdict(self):
        script, runs = synthetic_runs()
        clean = timing.summarize(runs, script)
        self.assertTrue(clean['rule']['passed'])
        self.assertTrue(clean['per_repeat'][0]['passed'])
        self.assertTrue(all(r['timing_status'] == 'VALID' and r['timed_midi_messages'] == 1000 for r in clean['rows']))
        # Identical raw bytes and green timing alone cannot rescue an underpowered arm.
        runs[1]['arm']['samples'].pop(0)
        bad = timing.summarize(runs, script)
        self.assertTrue(bad['byte_identical'])
        self.assertTrue(all(bad['rule']['within'].values()))
        self.assertEqual(bad['rows'][1]['timed_midi_messages'], 999)
        self.assertEqual(bad['rows'][1]['timing_status'], 'INVALID')
        self.assertFalse(bad['rule']['passed'])
        self.assertFalse(bad['per_repeat'][0]['passed'])
        self.assertFalse(timing.verdict(*(clean['pooled_ms'][n] for n in timing.ARMS),
            identical=True, dropped_reported=True, live=True, valid_arms=False)['passed'])

    def test_segment_statistics_use_only_own_causal_messages(self):
        script, runs = synthetic_runs()
        result = timing.summarize(runs, script)
        expected = {'count': 4, 'p50': 2.5, 'p95': 3.85, 'p99': 3.97, 'max': 4.0}
        for key, value in expected.items():
            self.assertAlmostEqual(result['worst_case']['pooled_ms']['OPEN'][key], value)
            self.assertAlmostEqual(result['rows'][1]['worst_case_statistics_ms'][key], value)
        self.assertEqual(result['pooled_ms']['OPEN']['p50'], 100)
        for s in runs[1]['arm']['samples']:
            s['cause_step'] = 0
        with self.assertRaisesRegex(ValueError, 'Zero worst-case'):
            timing.summarize(runs, script)

    def test_pinned_workload_all_buttons_once_and_six_axes_every_tick_at_sender_rate(self):
        script = deck_script.read_json(ROOT / 'scripts/showready/timing_script.json')
        deck_script.validate(script)
        axes, interval = deck_script.sender_axes(ROOT / 'deck/xinput_send.py')
        buttons = set(deck_script.action_ids(ROOT / 'config/actions.yaml')) - set(axes)
        observed = Counter((s['event']['action'], s['event'].get('state')) for s in script['steps'] if s['event']['kind'] == 'action')
        self.assertEqual(observed, Counter({(a, state): 1 for a in buttons for state in ('down', 'up')}))
        self.assertEqual(script['source_deck_sha256'], timing_script.DECK_SHA256)
        self.assertGreaterEqual(script['duration_ns'], 60e9)
        self.assertLessEqual(script['duration_ns'], 90e9)
        segment, = script['segments']
        self.assertEqual(segment['name'], timing_script.WORST_CASE)
        self.assertEqual(segment['interval_ns'], interval)
        rows = [s for s in script['steps'] if s['segment'] == segment['name']]
        self.assertGreater(len(rows), 0)
        self.assertEqual(len(rows), 6 * segment['ticks'])
        for tick in range(segment['ticks']):
            group = rows[tick * 6:(tick + 1) * 6]
            self.assertEqual([s['event']['action'] for s in group], list(timing_script.SIMULTANEOUS_AXES))
            self.assertEqual([s['tick'] for s in group], [tick] * 6)
            self.assertEqual([s['at_ns'] for s in group], [segment['start_ns'] + tick * interval + i for i in range(6)])
        for action in axes:
            self.assertGreaterEqual(len({s['event']['value'] for s in script['steps'] if s['event']['action'] == action}), 9)

    def test_generator_is_a_deterministic_subset_and_cli_rejects_foreign_wire_value(self):
        # Synthetic preset supplies the same 2-second timer horizon; the real
        # source pin is separately required and tested, never fixture-dependent.
        deck = deck_script.generate(ROOT / 'config/actions.yaml', ROOT / 'deck/xinput_send.py',
            [('synthetic', {'mappings': {'DPAD_UP': {'type': 'macro_cc', 'fade_duration_seconds': 2}}})])
        with self.assertRaisesRegex(ValueError, 'pin changed'):
            timing_script.generate(deck, ROOT / 'deck/xinput_send.py')
        with patch.object(timing_script, 'DECK_SHA256', deck['sha256']):
            script = timing_script.generate(deck, ROOT / 'deck/xinput_send.py')
            self.assertEqual(script, timing_script.generate(deck, ROOT / 'deck/xinput_send.py'))
        pinned = deck_script.read_json(ROOT / 'scripts/showready/timing_script.json')
        self.assertEqual(script['steps'], pinned['steps'])
        self.assertEqual(script['packets'], pinned['packets'])
        self.assertTrue(check_subset(script, deck)['passed'])
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            original = deck_script.canonical(script)
            (work / 'deck.json').write_bytes(deck_script.canonical(deck))
            command = [sys.executable, '-B', str(ROOT / 'scripts/showready/timing_subset_check.py'),
                       str(work / 'timing.json'), str(work / 'deck.json')]
            for foreign in (False, True, False):
                mutated = json.loads(original)
                if foreign:
                    step = next(s for s in mutated['steps'] if s['event']['kind'] == 'axis')
                    step['event']['value'] = 12345
                    packet = next(p for p in mutated['packets'] if p['at_ns'] == step['at_ns'])
                    event = json.loads(bytes.fromhex(packet['hex']))
                    event['value'] = 12345
                    packet['hex'] = deck_script.canonical(event).hex()
                    deck_script.seal(mutated)  # A valid digest cannot pay encoding membership.
                (work / 'timing.json').write_bytes(deck_script.canonical(mutated))
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1 if foreign else 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)['passed'], not foreign)
                if foreign:
                    self.assertIn('Foreign encoding', json.loads(result.stdout)['error'])

    def test_interleaved_pacing_observes_each_axis_and_rejects_overspeed(self):
        script = deck_script.read_json(ROOT / 'scripts/showready/timing_script.json')
        sends = {s['id']: s['at_ns'] for s in script['steps']}
        result = timing.timing_pacing(script, sends, 1)
        self.assertEqual(len(result), 13)
        self.assertTrue(all(r['no_overspeed'] and r['count'] > 0 for r in result.values()))
        rows = [s for s in script['steps'] if s['event']['action'] == 'L_STICK_X_AXIS']
        sends[rows[1]['id']] -= 1
        key = timing_script.WORST_CASE + '/L_STICK_X_AXIS'
        self.assertFalse(timing.timing_pacing(script, sends, 1)[key]['no_overspeed'])

    def test_explicit_script_r1_cli_and_qualification_repeat_thresholds(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            argv = ['timing_ab.py', '--script', str(work / 'explicit.json'), '--repeats', '1',
                    '--scratch', str(work), '--out', str(work / 'result.json')]
            with patch.object(sys, 'argv', argv), patch.object(timing, 'run', return_value={'passed': True, 'bar3_counts': False}) as run:
                self.assertEqual(timing.main(), 78)
                self.assertEqual(run.call_args.args[0].script, work / 'explicit.json')
                self.assertEqual(run.call_args.args[0].repeats, 1)
        _, triplet = synthetic_runs()
        args = SimpleNamespace(repeats=3, speed=1, control='sensitivity', client_cmd=['browser'])
        self.assertTrue(timing.measurement_qualified(args, triplet * 3))
        args.control = None
        self.assertFalse(timing.measurement_qualified(args, triplet * 3))
        args.repeats = 5
        self.assertTrue(timing.measurement_qualified(args, triplet * 5))
        args.speed = 2
        self.assertFalse(timing.measurement_qualified(args, triplet * 5))
        args.speed = 1
        args.client_cmd = None
        with patch.object(timing.os, 'name', 'posix'):
            self.assertFalse(timing.measurement_qualified(args, triplet * 5))
        with patch.object(timing.os, 'name', 'nt'):
            self.assertTrue(timing.measurement_qualified(args, triplet * 5))

    def test_r3_sensitivity_receipt_is_accepted_but_r2_invalid_or_mismatched_is_not(self):
        result = {'host': 'fixture', 'candidate': 'sha', 'preset_sha256': 'preset', 'client': ['browser'],
                  'receiver_clock': 'script', 'instrument_sha256': {'kit': 'sha'}, 'script': {'sha256': 'script'}}
        control = {**result, 'control': 'sensitivity', 'repeats': 3, 'measurement_qualified': True,
                   'sensitivity_timing_red': True, 'summary': {'byte_identical': True, 'rule': {'valid_arms': True}}}
        self.assertTrue(timing.sensitivity_matches(control, result))
        self.assertFalse(timing.sensitivity_matches({**control, 'repeats': 2}, result))
        self.assertFalse(timing.sensitivity_matches({**control, 'client': 'python'}, result))
        control['summary']['rule']['valid_arms'] = False
        self.assertFalse(timing.sensitivity_matches(control, result))


if __name__ == '__main__':
    unittest.main()
