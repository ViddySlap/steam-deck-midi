"""Real loopback fan-out and feedback on one sender socket; no Deck required."""

import contextlib
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from deck.transport import send_action, send_axis, send_heartbeat
from protocol.messages import encode_action_event, encode_axis_event, encode_heartbeat_event


with contextlib.ExitStack() as stack:
    receivers = [stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
                 for _ in range(2)]
    for receiver in receivers:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2)
    sender = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    sender.settimeout(2)
    targets = [("localhost", receivers[0].getsockname()[1]), receivers[1].getsockname()]
    send_action(sender, targets, action="BTN_A", state="down", seq=1,
                profile_name="loopback", profile_hash=None)
    send_axis(sender, targets, action="YAW", value=64, seq=2)
    send_heartbeat(sender, targets, seq=3, profile_name="loopback", profile_hash=None)
    expected = [encode_action_event(action="BTN_A", state="down", seq=1, profile_name="loopback"),
                encode_axis_event(action="YAW", value=64, seq=2),
                encode_heartbeat_event(seq=3, profile_name="loopback")]
    sources = []
    for index, receiver in enumerate(receivers):
        packets = [receiver.recvfrom(65535) for _ in range(3)]
        assert [p for p, _ in packets] == expected
        sources.extend(address for _, address in packets)
        receiver.sendto(f"feedback-{index}".encode("ascii"), packets[-1][1])
    feedback = {sender.recvfrom(65535)[0] for _ in range(2)}
    assert len(set(sources)) == 1
    assert feedback == {b"feedback-0", b"feedback-1"}
    result = {"status": "PASS", "receivers": 2, "packets_per_receiver": 3,
              "identical_payloads": True, "seq": [1, 2, 3],
              "sender_source_count": len(set(sources)), "feedback_count": len(feedback),
              "scope": "real macOS loopback UDP; no physical Deck or MIDI"}

scratch = Path("/tmp/sdcore-s4")
scratch.mkdir(parents=True, exist_ok=True)
(scratch / "smoke.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
