"""Run either archived bridge with a byte recorder and fail-closed MIDI ports."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import time
import types

sys.dont_write_bytecode = True


class PortOpenDenied(BaseException):
    pass


def deny_ports(module, on_violation=None):
    def denied(*args, **kwargs):
        if on_violation:
            on_violation()
        raise PortOpenDenied('Real MIDI access forbidden by capture_runner')
    for name in ('open_input', 'open_output', 'open_ioport', 'get_input_names',
                 'get_output_names', 'get_ioport_names', 'Backend', 'set_backend',
                 'MidiIn', 'MidiOut', 'open_midiinput', 'open_midioutput'):
        setattr(module, name, denied)
    return denied


def midi_bytes(kind, channel, data1, data2):
    status = {'note_on': 0x90, 'note_off': 0x80, 'control_change': 0xB0}[kind]
    if type(channel) is not int or not 0 <= channel <= 15:
        raise ValueError('MIDI channel must be zero-based 0..15')
    if any(type(v) is not int or not 0 <= v <= 127 for v in (data1, data2)):
        raise ValueError('MIDI data must be 0..127')
    return bytes((status | channel, data1, data2))


class Recorder:
    port_name = 'SDWIN_RECORDER_NO_REAL_PORT'
    port_index = None

    def __init__(self, emit, context, dead=False):
        self.emit, self.context, self.dead = emit, context, dead

    def send(self, kind, channel, data1, data2):
        raw = midi_bytes(kind, channel, data1, data2)
        if not self.dead:
            self.emit({'record': 'midi', 'monotonic_ns': time.perf_counter_ns(),
                       'step': self.context['step'], 'logical_ns': self.context['logical_ns'],
                       'bytes': list(raw)})

    def note_on(self, channel, note, velocity):
        self.send('note_on', channel, note, velocity)

    def note_off(self, channel, note, velocity=0):
        self.send('note_off', channel, note, velocity)

    def control_change(self, channel, control, value):
        self.send('control_change', channel, control, value)

    def panic(self):
        for channel in range(16):
            self.control_change(channel, 123, 0)

    def close(self):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arm_tree', type=Path)
    parser.add_argument('config_dir', type=Path)
    parser.add_argument('out_file', type=Path)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--clock', choices=('script', 'wall'), default='script')
    parser.add_argument('--dead-recorder', action='store_true')
    parser.add_argument('--timing-config', type=Path,
                        help='Bar 3 same-process sender configuration; enables UI')
    # Parse our arguments separately: everything after -- belongs to main.
    argv = list(sys.argv[1:] if argv is None else argv)
    split = argv.index('--')
    args = parser.parse_args(argv[:split])
    bridge_argv = argv[split + 1:]
    required = {'--no-engines', '--no-pulse', '--no-osc-relay'}
    if not args.timing_config:
        required.add('--no-ui')
    elif '--no-ui' in bridge_argv:
        raise ValueError('Timing arms require UI on')
    if not required.issubset(bridge_argv) or any(v in bridge_argv for v in
            ('--tray', '--feedback-port', '--list-ports', '--check-midi-port')):
        raise ValueError('Unsafe bridge arguments')
    # Enforce ports/config from parsed argv again after the arm import below.
    tree = args.arm_tree.resolve()
    config = args.config_dir.resolve()
    if not config.is_relative_to(tree):
        raise ValueError('Config must be in the disposable arm tree')
    sys.path.insert(0, str(tree))
    from deck_script import canonical, read_json, validate
    script = read_json(args.script)
    validate(script)
    context = {'step': -1, 'logical_ns': 0}
    timing = None
    if args.timing_config:
        from timing_ab import CaptureTiming
        timing = CaptureTiming(read_json(args.timing_config), script, context)
    with args.out_file.open('x', encoding='ascii', buffering=1) as output:
        def emit(row):
            if timing:
                timing.enrich(row)
            output.write(json.dumps(row, separators=(',', ':')) + '\n')

        def violation():
            emit({'record': 'forbidden_midi_open'})
            os._exit(70)  # Also fatal from a product background thread.

        denied = None
        for name in ('mido', 'rtmidi', 'rtmidi.midiutil'):
            module = types.ModuleType(name)
            denied = deny_ports(module, violation)
            sys.modules[name] = module
        sys.modules['rtmidi'].midiutil = sys.modules['rtmidi.midiutil']
        bridge = importlib.import_module('windows.win_recv')
        receiver_module = importlib.import_module('windows.receiver')
        midi_module = importlib.import_module('windows.midi')
        if timing:
            timing.install(importlib.import_module('windows.live_events'))
        for name, module in list(sys.modules.items()):
            if name.startswith(('windows.', 'protocol.')) and getattr(module, '__file__', None):
                if not Path(module.__file__).resolve().is_relative_to(tree):
                    raise ValueError('Foreign arm import: ' + name)
        parsed = bridge.build_parser().parse_args(bridge_argv)
        host, port = bridge.parse_listen(parsed.listen)
        if host != '127.0.0.1' or port in (0, 45123, 7723) or parsed.ui_port in (0, 45123, 7723):
            raise ValueError('Unsafe/default port')
        if Path(parsed.map_path).resolve() != config / 'windows_midi_map.json':
            raise ValueError('Map outside disposable config')
        for kind, check_port in ((socket.SOCK_DGRAM, port), (socket.SOCK_STREAM, parsed.ui_port)):
            with socket.socket(socket.AF_INET, kind) as check:
                check.bind((host, check_port))
        if timing:
            timing.start(host, port, args.out_file)
        recorder = Recorder(emit, context, args.dead_recorder)
        bridge.open_midi_output = midi_module.open_midi_output = lambda *a, **k: recorder
        bridge.open_midi_input = midi_module.open_midi_input = lambda port_name, *a, **k: None if not port_name else denied()
        midi_module.MidoMidiIn = midi_module.MidoMidiOut = denied
        original_receiver = bridge.ActionReceiver

        class ObservedReceiver(original_receiver):
            def __init__(self, *a, **kw):
                if args.clock == 'script':
                    kw['clock'] = lambda: 1000 + context['logical_ns'] / 1e9
                super().__init__(*a, **kw)

            def handle_datagram(self, payload, addr, now=None):
                handled = super().handle_datagram(payload, addr, now)
                event = json.loads(payload)
                if event['kind'] != 'heartbeat':
                    emit({'record': 'input', 'step': context['step'], 'event': event, 'handled': handled})
                return handled

        bridge.ActionReceiver = ObservedReceiver
        digest = hashlib.sha256()
        count = 0

        class ObservedSocket(socket.socket):
            def bind(self, address):
                if address != (host, port):
                    raise ValueError('Unexpected receiver socket')
                super().bind(address)
                Path(str(args.out_file) + '.ready.json').write_bytes(canonical({
                    'pid': os.getpid(), 'bound': list(self.getsockname()), 'clock': args.clock,
                    'bridge_file': bridge.__file__, 'argv': bridge_argv}))

            def recvfrom(self, *a, **kw):
                nonlocal count
                # Entering the next receive proves the last full bridge loop ran.
                if timing:
                    timing.completed_packets = count
                if count == len(script['packets']):
                    Path(str(args.out_file) + '.done.json').write_bytes(canonical({
                        'packets_received': count, 'packet_stream_sha256': digest.hexdigest(),
                        'pid': os.getpid()}))
                payload, addr = super().recvfrom(*a, **kw)
                row = script['packets'][count]
                if payload != bytes.fromhex(row['hex']):
                    raise ValueError('Dropped, reordered or foreign UDP packet at ' + str(count))
                context.update(step=row['step'], logical_ns=row['at_ns'])
                digest.update(struct.pack('!I', len(payload)))
                digest.update(payload)
                count += 1
                return payload, addr

        receiver_module.socket = types.SimpleNamespace(socket=ObservedSocket, AF_INET=socket.AF_INET,
                                                       SOCK_DGRAM=socket.SOCK_DGRAM, timeout=socket.timeout)
        emit({'record': 'metadata', 'pid': os.getpid(), 'tree': str(tree), 'clock': args.clock})
        return bridge.main(bridge_argv)


if __name__ == '__main__':
    sys.exit(main())
