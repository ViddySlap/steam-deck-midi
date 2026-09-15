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
                           for value in (1, 2, 3) * 334]
                runs.append({'name': name, 'repeat': repeat, 'load_status': 'verified',
                    'arm': {'records': samples, 'samples': samples,
                            'snapshot_after': {'dropped': 0}, 'stream': {'dropped': 0}, 'live_valid': True}})
        result = timing.summarize(runs, script)
        self.assertTrue(result['rule']['passed'])
        self.assertTrue(result['null_control']['passed'])
        self.assertEqual(result['pooled_ms']['OPEN']['count'], 5010)
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

    def replay_with_sendto(self, sendto_effect):
        """Run the real sender loop over two packets of one step with a fake socket."""
        from types import SimpleNamespace
        from time import sleep
        packets = [{'step': 0, 'at_ns': 1, 'hex': '7b7d'}, {'step': 0, 'at_ns': 2, 'hex': '7b7e7d'}]
        script = {'steps': [{'id': 0, 'at_ns': 1, 'phase': 'tap', 'event': {'kind': 'action', 'action': 'BTN_A'}}],
                  'packets': packets}
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'start').touch()
            (work / 'capture').touch()
            (work / 'capture.done.json').write_text('{}')
            owner = timing.CaptureTiming({'start': str(work / 'start'), 'result': str(work / 'result'),
                                          'speed': 1, 'mappings': {}}, script, {})
            owner.live = SimpleNamespace(snapshot=lambda: {'clients': 0})
            owner.action = lambda: 'BTN_A'
            owner.origins = {'BTN_A': 0}
            calls = []
            def sendto(payload, address):
                packet = packets[len(calls)]
                calls.append(payload)
                return sendto_effect(owner, packet, payload)
            with patch.object(timing, 'wait_gap'), patch.object(timing.socket, 'socket') as factory:
                factory.return_value.__enter__.return_value.sendto.side_effect = sendto
                owner.start('127.0.0.1', 47899, work / 'capture')
                for _ in range(300):
                    if (work / 'result').exists():
                        break
                    sleep(.01)
                return json.loads((work / 'result').read_text())

    def test_t1_pre_before_and_t1_post_after_sendto_for_every_timed_message(self):
        from time import perf_counter_ns, sleep
        def stalled(owner, packet, payload):
            sleep(.005)  # The send stalls; the bridge receives and writes MIDI at its end.
            owner.enrich({'record': 'midi', 'monotonic_ns': perf_counter_ns(), 'step': packet['step'],
                          'logical_ns': packet['at_ns'], 'bytes': [144, 60, 1]})
            return len(payload)
        result = self.replay_with_sendto(stalled)
        self.assertNotIn('error', result)
        self.assertEqual(result['every_message_timed_midi_messages'], 2)
        self.assertEqual([s['cause_packet'] for s in result['bridge_samples']], [0, 1])
        self.assertEqual([s['first_packet'] for s in result['bridge_samples']], [True, False])
        for index, sample in enumerate(result['bridge_samples']):
            self.assertGreaterEqual(result['t1_post_ns'][index] - result['t1_pre_ns'][index], 5_000_000)
            self.assertEqual(sample['t1_pre_ns'], result['t1_pre_ns'][index])
            self.assertGreaterEqual(sample['m_bridge_ms'], 5, 'M_bridge includes the send stall')
            self.assertLess(sample['m_post_ms'], 5, 'M_post excludes the send stall')
            self.assertGreaterEqual(sample['latency_ms'], 5, 'M_total includes the send stall')
            self.assertGreaterEqual(sample['latency_ms'], sample['m_bridge_ms'])

    def test_missing_t1_stamp_is_an_error_not_a_skip(self):
        timed = [{'step': 0, 'cause_step': 0, 'cause_packet': 0, 'first_packet': True, 't3_ns': 50, 'latency_ms': 1.0},
                 {'step': 0, 'cause_step': 0, 'cause_packet': 1, 'first_packet': False, 't3_ns': 90, 'latency_ms': 2.0}]
        joined = timing.bridge_join(timed, [10, 40], [20, 45])
        self.assertEqual([j['m_bridge_ms'] for j in joined], [40e-6, 50e-6])
        self.assertEqual([j['m_post_ms'] for j in joined], [30e-6, 45e-6])
        for pre, post in (([10, None], [20, 45]), ([10, 40], [20, None]), ([10], [20])):
            with self.assertRaisesRegex(ValueError, 'without t1_pre/t1_post'):
                timing.bridge_join(timed, pre, post)
        with self.assertRaisesRegex(ValueError, 'without t1_pre/t1_post'):
            timing.bridge_join([{**timed[0], 'cause_packet': None}], [10], [20])
        with self.assertRaisesRegex(ValueError, 'Impossible'):
            timing.bridge_join(timed, [10, 95], [20, 96])
        # Every packet the sender loop sends carries both stamps.
        result = self.replay_with_sendto(lambda owner, packet, payload: len(payload))
        self.assertEqual(len(result['t1_pre_ns']), 2)
        self.assertTrue(all(type(v) is int for v in result['t1_pre_ns'] + result['t1_post_ns']))

    def bridge_runs(self, shift=lambda arm, value: value, counts=None):
        script = {'steps': [{'id': 0, 'segment': 'axes', 'event': {'action': 'L_STICK_X_AXIS'}}],
                  'worst_case_segment': 'axes'}
        base = [1.0 + (i % 100) / 100 for i in range(1000)] + [5.0] * 20
        runs = []
        for repeat in range(1, 6):
            for name in timing.ARMS:
                values = [shift(name, v) for v in base[:(counts or {}).get((repeat, name), len(base))]]
                samples = [{'record': 'midi', 'step': 0, 'cause_step': 0, 'bytes': [176, 1, 1],
                            'latency_ms': v + 3} for v in values]
                joined = [{'step': 0, 'cause_step': 0, 'cause_packet': 0, 'first_packet': True,
                           'm_bridge_ms': v, 'm_post_ms': v - .01, 'latency_ms': v + 3} for v in values]
                runs.append({'name': name, 'repeat': repeat, 'load_status': 'verified',
                             'arm': {'samples': samples, 'bridge_samples': joined, 'records': samples,
                                     'stream': {'dropped': 0}, 'live_valid': True, 'snapshot_after': {'dropped': 0}}})
        return runs, script

    def test_m_bridge_rule_passes_within_floor_and_fails_two_ms_p99_shift(self):
        runs, script = self.bridge_runs(lambda arm, v: v + .3 if arm == 'OPEN' else v)
        result = timing.summarize_bridge(runs, script, True)
        self.assertTrue(result['rule']['passed'])
        self.assertAlmostEqual(result['rule']['open_delta_ms']['p99'], .3)
        self.assertEqual(result['rows'][0]['counts'], {'first_packet_join': 1020, 'every_message': 1020,
            'every_message_cause_first_packet': 1020, 'every_message_cause_later_packet': 0})
        self.assertIn('m_total_ms', result['pooled_ms'])
        self.assertIn('m_post_ms', result['worst_case']['pooled_ms'])
        runs, script = self.bridge_runs(lambda arm, v: v + 2 if arm == 'OPEN' and v >= 5 else v)
        result = timing.summarize_bridge(runs, script, True)
        self.assertEqual(result['rule']['within'], {'p50': True, 'p95': True, 'p99': False})
        self.assertFalse(result['rule']['passed'])
        self.assertTrue(all(not r['passed'] for r in result['per_repeat']))
        self.assertFalse(timing.summarize_bridge(self.bridge_runs()[0], script, False)['rule']['passed'],
                         'Different bytes void the M_bridge verdict too')

    def test_invalid_arm_voids_m_bridge_verdict(self):
        runs, script = self.bridge_runs(counts={(3, 'OPEN'): 999})
        result = timing.summarize_bridge(runs, script, True)
        self.assertFalse(result['rule']['valid_arms'])
        self.assertFalse(result['rule']['passed'])
        self.assertEqual([r['passed'] for r in result['per_repeat']], [True, True, False, True, True])
        self.assertEqual(result['rows'][7]['every_message_timing_status'], 'INVALID')
        args = type('Args', (), {'control': 'sensitivity', 'repeats': 3, 'speed': 1, 'client_cmd': ['x'], 'rule': 'm_bridge'})()
        clean, _ = self.bridge_runs()
        self.assertTrue(timing.measurement_qualified(args, [{**r, 'arm': {**r['arm'], 'passed': True}} for r in clean[:9]]))
        self.assertFalse(timing.measurement_qualified(args, [{**r, 'arm': {**r['arm'], 'passed': True}} for r in runs[:9]]))

    def test_m_bridge_sensitivity_not_red_exits_nonzero(self):
        from io import StringIO
        from contextlib import redirect_stdout
        argv = ['timing_ab.py', '--script', 'x.json', '--scratch', '/tmp/x', '--out', '/tmp/x.json',
                '--repeats', '3', '--control', 'sensitivity']
        def main(rule, red):
            result = {'passed': False, 'bar3_counts': False, 'rule': rule}
            if red is not None:
                result['m_bridge_sensitivity_timing_red'] = red
            out = StringIO()
            with patch.object(sys, 'argv', argv + ['--rule', rule]), patch.object(timing, 'run', return_value=result), \
                    patch.object(timing, 'write_result', return_value='/tmp/x.json'), redirect_stdout(out):
                return timing.main(), out.getvalue()
        for red in (False, None):
            code, printed = main('m_bridge', red)
            self.assertEqual(code, 3)
            self.assertIn(timing.M_BRIDGE_INVALID, printed)
        code, printed = main('m_bridge', True)
        self.assertEqual(code, 1)
        self.assertNotIn(timing.M_BRIDGE_INVALID, printed)
        self.assertEqual(main('locked', False)[0], 1)

    def test_m_total_unchanged_against_stored_fixture(self):
        fixture = json.loads((ROOT / 'tests/showready_m_total_fixture.json').read_text())
        capture = timing.CaptureTiming({'mappings': {}}, {}, {})
        capture.sent = {int(k): v for k, v in fixture['sends'].items()}
        current = [None]
        capture.action = lambda: current[0]
        for stored in fixture['rows']:
            current[0] = stored['action']
            capture.origins = {stored['action']: stored['cause_step']}
            row = {k: stored[k] for k in ('record', 'monotonic_ns', 'step', 'logical_ns', 'bytes')}
            capture.enrich(row)
            self.assertEqual(row['latency_ms'], stored['latency_ms'])
        self.assertEqual(len(capture.samples), len(fixture['rows']))
        self.assertEqual(timing.stats([s['latency_ms'] for s in capture.samples]), fixture['base_statistics_ms'])

    def test_foreign_lines_match_engine_tests_and_void_the_load_check(self):
        tests = timing.FOREIGN_TESTS
        ps = '\n'.join(['  11 /bin/zsh ' + tests + 'e54-guard.sh', '  12 node /x/run-all.sh --fast',
                        '  13 zsh -c ' + tests + 'x.sh', '  14 codex exec zsh ' + tests + 'y.sh',
                        '  15 /usr/bin/python3 ' + tests + 'z.py', '  16 bash -x ' + tests + 'w.sh'])
        self.assertEqual([line.split()[0] for line in timing.foreign_lines(ps)], ['11', '12', '16'])
        if os.name == 'nt':
            return
        empty = lambda: {'status': 'empty', 'load_average': [1, 2, 3]}
        with patch.object(timing.subprocess, 'run') as run:
            run.side_effect = [subprocess.CompletedProcess([], 0, '  1 /sbin/launchd\n', ''),
                               subprocess.CompletedProcess([], 0, '{ 1.50 1.20 1.00 }\n', '')]
            clean = timing.foreign_load_check(empty)
            self.assertEqual((clean['status'], clean['foreign']['foreign_lines'], clean['foreign']['load1']), ('empty', 0, 1.5))
            run.side_effect = [subprocess.CompletedProcess([], 0, ps, ''),
                               subprocess.CompletedProcess([], 0, '{ 1.50 1.20 1.00 }\n', '')]
            self.assertEqual(timing.foreign_load_check(empty)['status'], 'load-present')
            run.side_effect = [subprocess.CompletedProcess([], 1, '', 'denied'),
                               subprocess.CompletedProcess([], 0, '{ 1.50 1.20 1.00 }\n', '')]
            self.assertEqual(timing.foreign_load_check(empty)['status'], 'unreadable')

    def test_m_bridge_sensitivity_receipt_must_be_an_m_bridge_red(self):
        result = {'host': 'h', 'candidate': 'c', 'preset_sha256': 'p', 'client': 'k', 'receiver_clock': 'script',
                  'instrument_sha256': 'i', 'script': {'sha256': 's'}}
        control = {**result, 'control': 'sensitivity', 'repeats': 3, 'measurement_qualified': True,
                   'summary': {'byte_identical': True, 'rule': {'valid_arms': True}}, 'sensitivity_timing_red': True,
                   'rule': 'm_bridge', 'm_bridge_sensitivity_timing_red': True, 'm_bridge': {'rule': {'valid_arms': True}}}
        self.assertTrue(timing.sensitivity_matches(control, result, 'm_bridge'))
        self.assertTrue(timing.sensitivity_matches(control, result))
        self.assertFalse(timing.sensitivity_matches({**control, 'm_bridge_sensitivity_timing_red': False}, result, 'm_bridge'))
        self.assertFalse(timing.sensitivity_matches({**control, 'rule': 'locked'}, result, 'm_bridge'))
        self.assertFalse(timing.sensitivity_matches({**control, 'sensitivity_timing_red': False}, result))

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

    def test_bridge_noop_browser_command_really_succeeds(self):
        # A failing BROWSER makes webbrowser fall back to the default browser, a real live client.
        import shlex, webbrowser
        self.assertIs(webbrowser.GenericBrowser(shlex.split(timing.NOOP_BROWSER)).open('http://127.0.0.1:9/'), True)


if __name__ == '__main__':
    unittest.main()
