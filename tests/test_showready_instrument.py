"""Fast assertions at the packet, MIDI-byte, coverage and real-port seams."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'scripts/showready'
sys.path.insert(0, str(KIT))
import deck_script as deck
import capture_runner as capture
import ab_run as ab


class InstrumentTests(unittest.TestCase):
    def test_scratch_is_on_the_authorized_showready_rail(self):
        expected = (Path(os.environ['LOCALAPPDATA']) / 'Temp/sdwin/w3'
                    if os.name == 'nt' else Path('/tmp/sdwin-w3'))
        self.assertEqual(ab.default_scratch(), expected)
        ab.validate_scratch(expected)
        with self.assertRaises(ValueError):
            ab.validate_scratch(Path('/').resolve())

    def script(self):
        return deck.generate(ROOT / 'config/actions.yaml', ROOT / 'deck/xinput_send.py',
                             [('default', deck.read_json(ROOT / 'config/presets/default.json'))])

    def test_all_action_ids_buttons_holds_axes_and_repeatable_digest(self):
        script = self.script()
        deck.validate(script)
        self.assertEqual(script, self.script())
        self.assertEqual(set(deck.action_ids(ROOT / 'config/actions.yaml')),
                         {s['event']['action'] for s in script['steps']})
        self.assertEqual(len(script['axes']), 13)
        for action in script['actions']:
            rows = [s for s in script['steps'] if s['event']['action'] == action]
            if action in script['axes']:
                for phase in ('axis-60hz', 'axis-10hz'):
                    sweep = [r for r in rows if r['phase'] == phase]
                    self.assertEqual(min(r['event']['value'] for r in sweep), script['axes'][action][0])
                    self.assertEqual(max(r['event']['value'] for r in sweep), script['axes'][action][1])
                    self.assertEqual(sweep[-1]['event']['value'], 0)
                    interval = 16_666_667 if phase == 'axis-60hz' else 100_000_000
                    self.assertTrue(all(y['at_ns'] - x['at_ns'] == interval for x, y in zip(sweep, sweep[1:])))
            else:
                self.assertEqual([(r['phase'], r['event']['state']) for r in rows],
                                 [('tap', 'down'), ('tap', 'up'), ('hold', 'down'), ('hold', 'up')])
                self.assertGreaterEqual(rows[3]['at_ns'] - rows[2]['at_ns'], 1_500_000_000)
        self.assertGreater(script['parameters']['gap_seconds'], script['parameters']['longest_delay_seconds'])

    def test_sender_ranges_include_calibration_offsets_and_unsigned_triggers(self):
        axes, rate = deck.sender_axes(ROOT / 'deck/xinput_send.py')
        self.assertEqual(axes['L_STICK_X_AXIS'], [-32886, 32649])
        self.assertEqual(axes['R_STICK_Y_AXIS'], [-32432, 33103])
        self.assertEqual(axes['L_TRIGGER_PRESSURE'], [0, 65535])
        self.assertEqual(axes['GYRO_PITCH'], [-32767, 32767])
        self.assertEqual(axes['L_PAD_X_POS'], [-32768, 32767])
        self.assertEqual(rate, 16_666_667)

    def test_midi_spec_status_and_data_bytes_channels_one_and_sixteen(self):
        for channel, on, off, cc in ((0, 0x90, 0x80, 0xB0), (15, 0x9F, 0x8F, 0xBF)):
            self.assertEqual(capture.midi_bytes('note_on', channel, 60, 127), bytes([on, 60, 127]))
            self.assertEqual(capture.midi_bytes('note_off', channel, 60, 0), bytes([off, 60, 0]))
            self.assertEqual(capture.midi_bytes('control_change', channel, 7, 99), bytes([cc, 7, 99]))
        for channel, data in ((16, 7), (-1, 7), (0, 128), (0, -1)):
            with self.assertRaises(ValueError):
                capture.midi_bytes('note_on', channel, data, 0)

    def test_one_byte_change_zero_messages_and_missing_action_are_red(self):
        event = {'kind': 'action', 'action': 'BTN_A', 'state': 'down'}
        script = {'steps': [{'id': 0, 'event': event}]}
        mapping = {'BTN_A': {'type': 'note', 'channel': 0, 'note': 60}}
        received = {'record': 'input', 'step': 0, 'event': event, 'handled': True}
        message = {'record': 'midi', 'step': 0, 'bytes': [144, 60, 127]}
        clean = [received, message]
        self.assertTrue(ab.compare(script, clean, clean, mapping, mapping)['passed'])
        mutant = [received, {**message, 'bytes': [144, 61, 127]}]
        red = ab.compare(script, clean, mutant, mapping, mapping)
        self.assertFalse(red['passed'])
        self.assertEqual(red['different_mappings'], ['BTN_A'])
        self.assertFalse(ab.compare(script, [], [], mapping, mapping)['passed'])
        self.assertFalse(ab.compare(script, [received], [received], mapping, mapping)['passed'])
        # Startup MIDI cannot pay per-mapping coverage.
        startup = [{**message, 'step': -1}]
        red = ab.compare({'steps': []}, startup, startup, mapping, mapping)
        self.assertFalse(red['passed'])
        self.assertEqual(red['unexercised_mappings'], ['BTN_A'])

    def test_runner_port_guard_refuses_fake_mido_without_open_calls(self):
        calls = []
        module = types.ModuleType('mido')
        module.open_input = lambda *a, **k: calls.append('input')
        module.open_output = lambda *a, **k: calls.append('output')
        capture.deny_ports(module)
        for name in ('open_input', 'open_output', 'open_ioport', 'Backend', 'MidiIn', 'MidiOut'):
            with self.assertRaises(capture.PortOpenDenied):
                getattr(module, name)('REAL_PORT')
        self.assertEqual(calls, [])

    def test_port_violation_is_nonzero_in_a_child(self):
        code = ('import sys,types; sys.path.insert(0,sys.argv[1]); import capture_runner as c; '
                'm=types.ModuleType("mido"); c.deny_ports(m); m.open_output("REAL_PORT")')
        child = subprocess.Popen([sys.executable, '-B', '-c', code, str(KIT)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = child.communicate(timeout=15)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn(b'PortOpenDenied', stderr)
        self.assertIsNotNone(child.poll())

    def test_packet_encoder_matches_protocol_and_tamper_fails(self):
        from protocol.messages import parse_action_event
        for event in ({'kind': 'action', 'action': 'BTN_A', 'state': 'down'},
                      {'kind': 'axis', 'action': 'L_STICK_X_AXIS', 'value': -32886}):
            parsed = parse_action_event(deck.packet(event, 7))
            self.assertEqual(parsed.action, event['action'])
            self.assertEqual(parsed.seq, 7)
        script = self.script()
        script['packets'][0]['hex'] = deck.packet({'kind': 'heartbeat'}, 1).hex()
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            deck.validate(script)

    def test_recorder_keeps_bytes_timestamps_and_panic(self):
        rows = []
        recorder = capture.Recorder(rows.append, {'step': 4, 'logical_ns': 900})
        recorder.note_on(15, 127, 99)
        recorder.note_off(15, 127)
        recorder.panic()
        self.assertEqual(rows[0]['bytes'], [159, 127, 99])
        self.assertEqual(rows[1]['bytes'], [143, 127, 0])
        self.assertEqual([r['bytes'] for r in rows[2:]], [[176 + ch, 123, 0] for ch in range(16)])
        self.assertTrue(all(r['monotonic_ns'] > 0 and r['step'] == 4 for r in rows))


if __name__ == '__main__':
    unittest.main()
