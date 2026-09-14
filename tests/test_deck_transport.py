"""Portable transport contracts; no X11 or Deck hardware needed."""

import json
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

from deck import transport
from protocol.messages import encode_action_event, encode_axis_event, encode_heartbeat_event


class FakeSocket:
    def __init__(self):
        self.sent = []
    def sendto(self, payload, target):
        self.sent.append((payload, target))


class DeckTransportTests(unittest.TestCase):
    def setUp(self):
        transport._address_cache.clear()
        transport._last_error_at.clear()
        self.sock = FakeSocket()
        self.targets = [("192.0.2.1", 45123), ("192.0.2.2", 45124)]

    def test_action_identical_bytes_and_seq_in_target_order(self):
        transport.send_action(self.sock, self.targets, action="BTN_A", state="down",
                              seq=17, profile_name="show", profile_hash="abc")
        expected = encode_action_event(action="BTN_A", state="down", seq=17,
                                       profile_name="show", profile_hash="abc")
        self.assertEqual(self.sock.sent, [(expected, t) for t in self.targets])
        self.assertEqual([json.loads(p)["seq"] for p, _ in self.sock.sent], [17, 17])

    def test_axis_fans_out(self):
        transport.send_axis(self.sock, self.targets, action="PITCH", value=73, seq=18)
        expected = encode_axis_event(action="PITCH", value=73, seq=18)
        self.assertEqual(self.sock.sent, [(expected, t) for t in self.targets])

    def test_fanout_has_no_two_target_limit(self):
        targets = [("192.0.2.1", port) for port in range(1, 9)]
        transport.send_axis(self.sock, targets, action="YAW", value=1, seq=2)
        expected = encode_axis_event(action="YAW", value=1, seq=2)
        self.assertEqual(self.sock.sent, [(expected, t) for t in targets])

    def test_heartbeat_fans_out(self):
        transport.send_heartbeat(self.sock, self.targets, seq=19,
                                 profile_name="show", profile_hash="abc")
        expected = encode_heartbeat_event(seq=19, profile_name="show", profile_hash="abc")
        self.assertEqual(self.sock.sent, [(expected, t) for t in self.targets])

    def test_single_target_keyword_is_compatible(self):
        transport.send_axis(self.sock, target=self.targets[0], action="YAW", value=4, seq=1)
        self.assertEqual(self.sock.sent, [(encode_axis_event(action="YAW", value=4, seq=1),
                                          self.targets[0])])

    def test_send_failure_does_not_block_later_target_for_any_event(self):
        def sendto(payload, target):
            if target == self.targets[0]:
                raise OSError("unreachable")
            self.sock.sent.append((payload, target))
        self.sock.sendto = sendto
        with patch("deck.transport.logger.warning"):
            transport.send_action(self.sock, self.targets, action="BTN_A", state="up", seq=1,
                                  profile_name=None, profile_hash=None)
            transport.send_axis(self.sock, self.targets, action="ROLL", value=2, seq=2)
            transport.send_heartbeat(self.sock, self.targets, seq=3,
                                     profile_name=None, profile_hash=None)
        self.assertEqual([t for _, t in self.sock.sent], [self.targets[1]] * 3)
        self.assertEqual([json.loads(p)["seq"] for p, _ in self.sock.sent], [1, 2, 3])

    def test_errors_are_rate_limited_per_target_across_event_types(self):
        self.sock.sendto = lambda *_: (_ for _ in ()).throw(OSError("offline"))
        with patch("deck.transport.time.monotonic") as clock, \
                patch("deck.transport.logger.warning") as warning:
            for now in [0, 29.999, 30]:
                clock.return_value = now
                transport.send_axis(self.sock, self.targets, action="YAW", value=1, seq=1)
                transport.send_heartbeat(self.sock, self.targets, seq=2,
                                         profile_name=None, profile_hash=None)
            self.assertEqual(warning.call_count, 4)
            self.assertEqual([c.args[1] for c in warning.call_args_list],
                             [self.targets[0], self.targets[1]] * 2)

    def test_parse_comma_separated_targets_and_legacy_single(self):
        self.assertEqual(transport.parse_targets("a:1, b:2"), [("a", 1), ("b", 2)])
        self.assertEqual(transport.parse_target("a:1"), ("a", 1))
        for invalid in ["", "a", "a:0", "a:65536", "a:1,", ":1", "bad host:2"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                transport.parse_targets(invalid)

    def test_hostname_resolves_on_send_and_refreshes_at_60_seconds(self):
        targets = transport.parse_targets("viddymac.local:45123,192.0.2.9:45124")
        answers = [[(socket.AF_INET, socket.SOCK_DGRAM, 17, "", (ip, 45123))]
                   for ip in ["192.0.2.3", "192.0.2.4"]]
        with patch("deck.transport.socket.getaddrinfo", side_effect=answers) as dns, \
                patch("deck.transport.time.monotonic") as clock:
            for now in [0, 59.999, 60]:
                clock.return_value = now
                transport.send_axis(self.sock, targets, action="YAW", value=9, seq=1)
            self.assertEqual(dns.call_count, 2)
            dns.assert_called_with("viddymac.local", 45123, socket.AF_INET, socket.SOCK_DGRAM)
        self.assertEqual([t for _, t in self.sock.sent], [
            ("192.0.2.3", 45123), targets[1], ("192.0.2.3", 45123), targets[1],
            ("192.0.2.4", 45123), targets[1]])

    def test_dns_failure_is_cached_and_does_not_block_then_recovers(self):
        targets = [("missing.local", 1), self.targets[1]]
        answer = [(socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("192.0.2.5", 1))]
        with patch("deck.transport.socket.getaddrinfo", side_effect=[socket.gaierror("missing"), answer]) as dns, \
                patch("deck.transport.time.monotonic") as clock, \
                patch("deck.transport.logger.warning"):
            for now in [0, 59, 60]:
                clock.return_value = now
                transport.send_axis(self.sock, targets, action="YAW", value=9, seq=1)
            self.assertEqual(dns.call_count, 2)
        self.assertEqual([t for _, t in self.sock.sent],
                         [self.targets[1], self.targets[1], ("192.0.2.5", 1), self.targets[1]])

    def test_sender_and_wizard_import_without_loading_shared_libraries(self):
        result = subprocess.run([sys.executable, "-c", "from unittest.mock import patch; "
                                 "guard = patch('ctypes.CDLL', side_effect=AssertionError('eager load')); "
                                 "guard.start(); import deck.xinput_send; import deck.learn_wizard"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sender_and_wizard_import_without_posix_hardware_modules(self):
        result = subprocess.run([sys.executable, "-c", "import sys; "
                                 "sys.modules.update(fcntl=None, termios=None, tty=None); "
                                 "import deck.xinput_send; import deck.learn_wizard; "
                                 "import deck.control_api; import deck.launch_send; "
                                 "assert callable(deck.xinput_send.run_sender); "
                                 "assert callable(deck.learn_wizard.write_bindings)"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
