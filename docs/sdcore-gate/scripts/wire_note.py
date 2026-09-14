import sys, socket, time, mido
sys.path.insert(0, ".")
from protocol.messages import encode_action_event
seq = int(sys.argv[1])
inp = mido.open_input("IAC Driver DECK_IN")
for _ in inp.iter_pending(): pass
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for i, state in enumerate(("down", "up")):
    s.sendto(encode_action_event(action="BTN_A", state=state, seq=seq + i, profile_name=None, profile_hash=None), ("127.0.0.1", 45123))
    time.sleep(0.15)
time.sleep(0.3)
msgs = [m for m in inp.iter_pending() if m.type in ("note_on", "note_off")]
print("IAC DECK_IN received:", [(m.type, m.channel, m.note, m.velocity) for m in msgs])
