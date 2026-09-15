"""Mutate timing_ab.py, run the named test, restore, prove restoration by digest."""
import hashlib, subprocess, sys
from pathlib import Path
ROOT = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
target = ROOT / 'scripts/showready/timing_ab.py'
original = target.read_bytes()
digest = hashlib.sha256(original).hexdigest()
MUTANTS = [
 ('R1 t1_pre taken AFTER sendto', 'test_t1_pre_before_and_t1_post_after_sendto_for_every_timed_message',
  """                        t1_pre = time.perf_counter_ns()  # t1_pre: IMMEDIATELY before sendto (M_bridge).
                        written = sender.sendto(payload, (host, port))
                        t1_post = time.perf_counter_ns()  # t1_post: immediately after it returns (diagnostic).""",
  """                        written = sender.sendto(payload, (host, port))
                        t1_pre = time.perf_counter_ns()
                        t1_post = time.perf_counter_ns()"""),
 ('R2 missing stamp silently skipped', 'test_missing_t1_stamp_is_an_error_not_a_skip',
  """            raise ValueError('Timed MIDI without t1_pre/t1_post: step %s packet %s' % (row.get('step'), packet))""",
  """            continue"""),
 ('R3 sensitivity-not-RED exit code removed', 'test_m_bridge_sensitivity_not_red_exits_nonzero',
  """    if invalid:
        code = 3""", """    if False:
        code = 3"""),
 ('R4 M_total computation moved by 1 ns', 'test_m_total_unchanged_against_stored_fixture',
  """    return (t3_ns - t0_ns) / 1e6""", """    return (t3_ns - t0_ns + 1) / 1e6"""),
 ('R5 invalid arm no longer voids M_bridge', 'test_invalid_arm_voids_m_bridge_verdict',
  """    outcome = rule([pooled['m_bridge_ms'][n] for n in ARMS],
                   all(r['every_message_timing_status'] == 'VALID' for r in rows))""",
  """    outcome = rule([pooled['m_bridge_ms'][n] for n in ARMS], True)"""),
]
failures = 0
try:
    for name, test, old, new in MUTANTS:
        text = original.decode()
        assert text.count(old) == 1, name
        target.write_text(text.replace(old, new))
        run = subprocess.run([str(ROOT / '.venv/bin/python'), '-B', '-m', 'unittest', 'tests.test_showready_timing.TimingTests.' + test],
                             cwd=ROOT, capture_output=True, text=True)
        tail = run.stderr.strip().splitlines()[-1]
        print(f'{name}: {test} exit={run.returncode} {tail}')
        failures += run.returncode != 0
finally:
    target.write_bytes(original)
restored = hashlib.sha256(target.read_bytes()).hexdigest() == digest
clean = subprocess.run([str(ROOT / '.venv/bin/python'), '-B', '-m', 'unittest', 'tests.test_showready_timing'], cwd=ROOT, capture_output=True, text=True)
print('restored digest equal:', restored, digest)
print('clean module after restore: exit', clean.returncode, clean.stderr.strip().splitlines()[-1])
print(f'MUTANTS RED {failures}/{len(MUTANTS)}')
sys.exit(0 if restored and clean.returncode == 0 and failures == len(MUTANTS) else 1)
