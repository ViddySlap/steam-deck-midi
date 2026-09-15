"""The timing detector must reject known delay, missing clients and unread load."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts/showready'))
import timing_ab as timing


class TimingTests(unittest.TestCase):
    def test_percentiles_fixed_interpolated_list(self):
        values = [10, 0, 30, 20, 40]
        self.assertEqual(timing.percentile(values, 50), 20)
        self.assertEqual(timing.percentile(values, 95), 38)
        self.assertEqual(timing.percentile(values, 99), 39.6)
        self.assertEqual(timing.percentile(values, 100), 40)
        self.assertEqual(timing.percentile([3], 99), 3)
        with self.assertRaises(ValueError):
            timing.percentile([], 50)

    def test_two_ms_shift_fails_and_small_shift_within_floor_passes(self):
        base = timing.stats([1, 2, 3, 4, 5])
        def check(shift, floor):
            return timing.verdict(base, timing.stats([x + shift for x in [1, 2, 3, 4, 5]]),
                timing.stats([x + floor for x in [1, 2, 3, 4, 5]]),
                identical=True, dropped_reported=True, live=True)
        self.assertFalse(check(2, 0)['passed'])
        self.assertFalse(check(-2, 0)['passed'])
        self.assertTrue(check(.2, .5)['passed'])
        self.assertTrue(check(0, .5)['passed'])
        self.assertFalse(check(0, 2)['passed'], 'A floor that hides 2 ms cannot pass')
        for key in ('identical', 'dropped_reported', 'live'):
            flags = dict(identical=True, dropped_reported=True, live=True)
            flags[key] = False
            self.assertFalse(timing.verdict(base, base, base, **flags)['passed'])
        huge_max = {**base, 'max': 10000}
        self.assertTrue(timing.verdict(base, huge_max, base,
            identical=True, dropped_reported=True, live=True)['passed'])

    def test_pgrep_guard_reruns_contaminated_arm_and_keeps_both_checks(self):
        states = iter(['empty', 'load-present', 'empty', 'empty'])
        seen = []
        checks = []
        def check():
            value = {'status': next(states), 'load_average': [1, 2, 3]}
            checks.append(value)
            return value
        result = timing.guarded_arm(lambda number: seen.append(number) or {'value': number},
                                    check, pause=lambda _: None)
        self.assertEqual(seen, [1, 2])
        self.assertEqual(result['arm']['value'], 2)
        self.assertEqual(len(result['attempts']), 2)
        self.assertEqual(result['attempts'][0]['after']['status'], 'load-present')
        self.assertEqual(result['attempts'][1]['before']['status'], 'empty')
        self.assertEqual(len(checks), 4)
        self.assertTrue(result['accepted'])

    def test_unreadable_is_never_empty_and_preexisting_load_skips_work(self):
        seen = []
        denied = lambda: {'status': 'unreadable', 'stderr': 'Cannot get process list'}
        result = timing.guarded_arm(lambda _: seen.append(True), denied)
        self.assertFalse(result['accepted'])
        self.assertEqual(seen, [])
        allowed = timing.guarded_arm(lambda _: {'ok': True}, denied, allow_unverified=True)
        self.assertTrue(allowed['accepted'])
        self.assertEqual(allowed['load_status'], 'UNVERIFIED-LOAD')
        states = iter(['load-present', 'empty', 'empty', 'empty'])
        result = timing.guarded_arm(lambda n: seen.append(n) or {},
                                    lambda: {'status': next(states)}, pause=lambda _: None)
        self.assertEqual(seen, [2])
        self.assertTrue(result['accepted'])

    def test_load_command_exit_one_and_denied_are_different(self):
        if os.name == 'nt':
            self.assertEqual(timing.load_check()['status'], 'not applicable')
            return
        with patch.object(timing.os, 'getloadavg', return_value=(1, 2, 3)), patch.object(timing.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 1, '', '')
            self.assertEqual(timing.load_check()['status'], 'empty')
            run.assert_called_with(['pgrep', '-f', 'while True: pass'], capture_output=True, text=True)
            run.return_value = subprocess.CompletedProcess([], 3, '', 'pgrep: Cannot get process list\n')
            result = timing.load_check()
            self.assertEqual(result['status'], 'unreadable')
            self.assertEqual(result['exit_code'], 3)
            self.assertEqual(result['stderr'], 'pgrep: Cannot get process list\n')

    def test_dead_client_fails_even_with_identical_latency_and_bytes(self):
        clean = {'client_counts': [1, 1], 'stream': {'data_events': 3, 'dropped': 0, 'error': None}}
        self.assertTrue(timing.live_valid(clean))
        for counts, events in (([0, 0], 0), ([1, 0, 1], 3), ([1, 1], 0), ([], 3)):
            bad = {'client_counts': counts, 'stream': {'data_events': events, 'dropped': 0}}
            self.assertFalse(timing.live_valid(bad))
        self.assertFalse(timing.live_valid({'client_counts': [1], 'stream': {'data_events': 2}}))

    def test_clock_and_causal_attribution_includes_delayed_midi_after_release(self):
        # Isolated fake publisher; no production/global observer is modified.
        class Live:
            def __init__(self):
                pass
            def publish(self, event):
                return event
        from types import SimpleNamespace
        action = ['BTN_A']
        module = SimpleNamespace(LiveEvents=Live, current_action=lambda: action[0])
        context = {'step': 0}
        capture = timing.CaptureTiming({'mappings': {'BTN_A': {'type': 'staged_note_macro'},
                                                     'BTN_B': {'type': 'note'}}}, {}, context)
        capture.install(module)
        publisher = Live()
        capture.sent = {0: 1000000, 1: 9000000}
        publisher.publish({'kind': 'input', 'action': 'BTN_A', 'state': 'down'})
        context['step'] = 1
        publisher.publish({'kind': 'input', 'action': 'BTN_A', 'state': 'up'})
        row = {'record': 'midi', 'step': 1, 'monotonic_ns': 10000000}
        capture.enrich(row)
        self.assertEqual(row['cause_step'], 0)
        self.assertEqual(row['send_perf_counter_ns'], 1000000)
        self.assertEqual(row['latency_ms'], 9)
        action[0] = 'BTN_B'
        publisher.publish({'kind': 'input', 'action': 'BTN_B', 'state': 'up'})
        row = {'record': 'midi', 'step': 1, 'monotonic_ns': 10000000}
        capture.enrich(row)
        self.assertEqual(row['cause_step'], 1)
        self.assertEqual(row['latency_ms'], 1)

    def test_summary_rechecks_every_message_and_exposes_top_outlier_step(self):
        import copy
        script = {'steps': [{'id': 0, 'event': {'action': 'BTN_A'}, 'phase': 'tap'}]}
        runs = []
        for repeat in range(1, 6):
            for name in timing.ARMS:
                samples = [{'record': 'midi', 'step': 0, 'cause_step': 0,
                            'bytes': [144, 60, value], 'latency_ms': float(value)}
                           for value in (1, 2, 3)]
                runs.append({'name': name, 'repeat': repeat, 'load_status': 'verified',
                    'arm': {'records': samples, 'samples': samples,
                            'snapshot_after': {'dropped': 0}, 'stream': {'dropped': 0}, 'live_valid': True}})
        result = timing.summarize(runs, script)
        self.assertTrue(result['rule']['passed'])
        self.assertTrue(result['null_control']['passed'])
        self.assertEqual(result['pooled_ms']['OPEN']['count'], 15)
        self.assertEqual(result['top_five_outliers'][0]['input']['event']['action'], 'BTN_A')
        self.assertEqual(len(result['top_five_outliers']), 5)
        mutant = copy.deepcopy(runs)
        mutant[1]['arm']['records'][0]['bytes'] = [144, 61, 1]
        self.assertFalse(timing.summarize(mutant, script)['rule']['passed'])
        mutant = copy.deepcopy(runs)
        mutant[1]['arm']['samples'] = []
        with self.assertRaisesRegex(ValueError, 'Zero latency observations'):
            timing.summarize(mutant, script)

    def test_sender_records_perf_counter_not_coarse_monotonic(self):
        from types import SimpleNamespace
        from time import sleep
        packets = [{'step': i, 'at_ns': i + 1, 'hex': '7b7d'} for i in range(2)]
        script = {'steps': [{'id': i, 'at_ns': i + 1, 'phase': 'tap',
                            'event': {'kind': 'action', 'action': 'BTN_A'}} for i in range(2)],
                  'packets': packets}
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'start').touch()
            (work / 'capture').touch()
            (work / 'capture.done.json').write_text('{}')
            owner = timing.CaptureTiming({'start': str(work / 'start'), 'result': str(work / 'result'),
                                          'speed': 1, 'mappings': {}}, script, {})
            owner.live = SimpleNamespace(snapshot=lambda: {'clients': 0})
            with patch.object(timing, 'wait_gap'), patch.object(timing.time, 'perf_counter_ns', return_value=1000000), \
                    patch.object(timing.time, 'monotonic_ns', return_value=999), patch.object(timing.socket, 'socket') as factory:
                sender = factory.return_value.__enter__.return_value
                sender.sendto.return_value = 2
                owner.start('127.0.0.1', 47899, work / 'capture')
                for _ in range(200):
                    if (work / 'result').exists():
                        break
                    sleep(.01)
                result = json.loads((work / 'result').read_text())
                self.assertEqual(sender.sendto.call_count, 2)
                sender.sendto.assert_called_with(b'{}', ('127.0.0.1', 47899))
                self.assertEqual(result['sends'], {'0': 1000000, '1': 1000000})
                self.assertEqual(result['pid'], os.getpid())

    def test_cleanup_waits_and_proves_direct_client_gone(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
        try:
            result = timing.stop_process(child)
            self.assertTrue(result['pid_gone'])
            self.assertTrue(result['was_alive'])
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


if __name__ == '__main__':
    unittest.main()
