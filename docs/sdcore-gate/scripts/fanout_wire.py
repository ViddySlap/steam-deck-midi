"""sdcore gate: real deck.transport fan-out to two real UDP listeners. Nothing faked."""
import hashlib
import json
import socket
import sys

sys.path.insert(0, "/Users/viddyslap/Documents/project-workspaces/steam-deck-midi")
import deck.transport as t

print("deck.transport from", t.__file__)
rx = {}
for port in (45123, 45124):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))
    s.settimeout(2)
    rx[port] = s
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
targets = t.parse_targets("127.0.0.1:45123,127.0.0.1:45124")
print("parse_targets ->", targets)
t.send_action(tx, targets, action="BTN_A", state="down", seq=1, profile_name="gate", profile_hash="abc")
t.send_axis(tx, targets, action="LSTICK_X", value=12345, seq=2)
t.send_heartbeat(tx, targets, seq=3, profile_name="gate", profile_hash="abc")
got = {p: [s.recvfrom(4096) for _ in range(3)] for p, s in rx.items()}
ok = True
for i in range(3):
    (da, aa), (db, ab) = got[45123][i], got[45124][i]
    ja, jb = json.loads(da), json.loads(db)
    same = da == db and aa == ab
    ok &= same and ja["seq"] == jb["seq"] == i + 1
    print(f"pkt{i + 1}: seq={ja['seq']}/{jb['seq']} sha256={hashlib.sha256(da).hexdigest()[:16]}/"
          f"{hashlib.sha256(db).hexdigest()[:16]} identical_bytes={da == db} src={aa}/{ab}")
    print(f"  bytes: {da.decode()}")
print("sender source", tx.getsockname(), "same source seen by both:", got[45123][0][1] == got[45124][0][1])
print("FANOUT_PASS" if ok else "FANOUT_FAIL")
sys.exit(0 if ok else 1)
