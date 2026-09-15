"""Render the E3 report directly from final raw receipts and verification logs."""
import gzip
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path('/tmp/sdlive-e3')
OUT = ROOT / 'docs/sdlive-e3'
EVIDENCE = OUT / 'evidence'
EVIDENCE.mkdir(exist_ok=True)

def read(name):
    data = (SCRATCH / name).read_bytes()
    return json.loads(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)

clean = read('final-clean.json.gz')
sensitivity = read('final-sensitivity.json.gz')
dead = read('final-dead.json.gz')
browser = read('browser-hook.json.gz')
commands = read('final-commands.json')
assert len(commands) == 3
assert sensitivity['sensitivity_timing_red'] and sensitivity['summary']['byte_identical']
assert all(r['arm']['passed'] for r in sensitivity['runs'] + clean['runs'])
assert dead['runs'][0]['arm']['client_counts'] == [0]
assert dead['runs'][0]['arm']['cleanup']['pid_gone']
assert browser['arm']['passed'] and browser['arm']['browser_cleanup']['gone']
assert all(c['exit_code'] == 0 for c in read('node-results.json'))
assert clean['summary']['null_control']['passed']
assert not clean['bar3_counts']
for name in ['final-clean.json.gz','final-sensitivity.json.gz','final-dead.json.gz',
             'browser-hook.json.gz','final-commands.json','node-results.json','raw-verification.json',
             'scope.json','final-sensitivity.log','final-clean.log','final-dead.log',
             'mac-suite.log','geometry.log','browser-hook.log','focused-final.log','mutation.log',
             'ui_controller_check.log','ui_controller_macro_check.log','ui_reload_check.log','ui_sections_check.log']:
    source = SCRATCH / name
    if name.endswith('.log'):
        # Stored human-readable evidence is plain ASCII. Raw result JSON retains
        # exact timestamps/bytes; escaping console Unicode does not alter it.
        (EVIDENCE / name).write_text(source.read_text(errors='replace').encode('ascii', 'backslashreplace').decode(), encoding='ascii')
    else:
        shutil.copyfile(source, EVIDENCE / name)
# Keep the initial invalid sensitivity attempt's error/cleanup without treating
# its packet-loss failure as a sensitivity success.
initial = read('sensitivity.json.gz')
(EVIDENCE / 'initial-overflow.json').write_text(json.dumps({
    'command': initial['command'], 'error': initial['error'],
    'arms': [{k:a.get(k) for k in ('error','cleanup','command')} for r in initial['runs'] for a in [r['arm']]],
    'classification': 'Invalid accelerated attempt: packet loss, not timing sensitivity credit.'
}, indent=2)+'\n', encoding='ascii')
geometry_log = (SCRATCH / 'geometry.log').read_text()
receipt_path = Path(re.search(r'^RECEIPT (.+)$', geometry_log, re.M)[1])
shutil.copyfile(receipt_path, EVIDENCE / 'geometry-receipt.json')
suite = (SCRATCH / 'mac-suite.log').read_text()
count = re.search(r'^Ran .+$', suite, re.M)[0]
status = re.search(r'^OK.*$', suite, re.M)[0]
report = [f'''E3 ENTRY HEAD bd1bdda42d9f9926ec23ab5d5218e029435f50a4

# sdlive E3 - bar 3 timing instrument

Instrument built and tested. Bar 3 qualification is OWED TO THE GATE.
No laptop acts, hardware acts, real MIDI ports, deployment or merge.
All Mac timing arms in this report are UNVERIFIED-LOAD and accelerated
DIAGNOSTICS. They cannot authorize an upgrade, even when the numeric rule passes.

The serial load check returned exit 3 with exact stderr:

```
sysmon request failed with error: sysmond service not found
pgrep: Cannot get process list
```

Command: `pgrep -f "while True: pass"`. The instrument ran it serially before
and after every arm, retaining exit code, stdout, stderr and os.getloadavg().
No denied result was treated as empty. This executor cannot qualify the Mac
load check; the gate's full-rate measurement is authoritative.

## Delivered and scope

- `scripts/showready/timing_ab.py`: serial CLOSED, OPEN, CLOSED-B triplets on
  one archived HEAD, sectioned EDM Show from verified fixtures, UI always on.
  CLOSED uses no HTTP client. OPEN uses an SSE reader with snapshot recovery,
  plus a 250 ms snapshot presence monitor. Both Python and browser clients must
  provide nonzero real data events, client counts and explicit dropped counts.
- `capture_runner.py`: optional `--timing-config` enables the UI and a sender
  thread in the same bridge process. The existing bar 1 invocation and all
  real-MIDI denial/port/config checks remain. Default still requires --no-ui.
- `timing_browser.cjs`: foreground native Chromium/Edge client hook, real
  Controller visible and Follow on, actual EventSource observations, cooperative
  stop, client process wait and independently checked browser PID absence.
- `tests/test_showready_timing.py`: percentile, tolerance, wide-floor, byte,
  empty-sample, dead-client, load retry/denial, causal attribution, clock and
  process-cleanup controls. SHA256SUMS repinned; README defines usage and limits.

`scope.json` records `git diff bd1bdda -- windows protocol deck config mac` and
existing instrument/rail/UI test paths: empty. No mapping handlers, semantics,
MIDI product paths, public functions, existing assertions or UI affordances
changed. All scratch/config saves were under /tmp/sdlive-e3. No vault write.
Predecessor E1/E2 launch records were fetched into Mac scratch and their reports,
the W3 latency report and pinned kit were read before implementation.

## Clock and attribution

Sender and Recorder call `time.perf_counter_ns()` in ONE process per arm.
Both timestamps and that PID are embedded in every result; no inter-process
offset is needed. The legacy Recorder field `monotonic_ns` is retained and
mirrored as `perf_counter_ns`. Clock implementation/resolution is in each arm.
The new sender-clock test supplies disagreeing perf_counter/monotonic readings
and asserts the actual two emitted packet timestamps and same-process PID.

Accepted input publication and E1's current Action ID associate each message
with its initiating input. Note/CC release belongs to UP. Fade, repeat and
staged sends keep their DOWN origin through release. Raw records retain both
causal step and current replay step. Startup bytes are compared but have no
fabricated input latency. Missing attribution, negative latency and zero
samples fail. Intentional timer delays remain INCLUDED in the distribution.
`--clock script` controls receiver scheduling as in W3; latency timestamps and
pacing are real perf_counter time. This is not ordinary scheduler certification.

### Bridge clock finding for Ben (source read, no MIDI-path change)

`windows/receiver.py:132` defaults `_clock` to time.monotonic, saved at :148.
Datagram timestamp :232, fades :374, relative repeats :467 and staged work :478
use it. `windows/engines/base.py:27` has the same default; live engine ticks
come from time.monotonic at receiver.py:1037, :1059 and :1067. MIDI feedback
also uses monotonic (`windows/midi.py:239`). The axis dispatcher at
receiver.py:891-977 has no direct time-based MIDI throttle: it emits for each
mapped non-deadzone packet and passes `_clock()` to engines at :897. The button
loop guard/dedupe uses datagram time (:493-546). Deck axis pacing is a separate
sender concern; no Deck hardware was measured.

W4's existing laptop probe (docs/sdwin-w4/REPORT.md:272-277, commit b3b2861)
measured Python 3.12 GetTickCount64 at 15.625 ms for monotonic versus QPC at
100 ns for perf_counter. Inference from that probe and the source: coarse
monotonic ticks CAN quantize fade progress, due-time decisions, repeat batching
and engine timing on that runtime. High-resolution capture does not repair
that bridge clock. Current laptop runtime behavior is UNVERIFIED-BY-EXECUTION
here and is a finding for Ben/gate, not an authorized change in E3.

## R and duration

Generator command:
`.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdlive-e3/deck-script.json`.
It produced {len(clean['script']['steps'])} steps, {len(clean['script']['packets'])} packets and
{clean['script']['duration_ns']/1e9:.9f} seconds of schedule. Its digest is
`{clean['script']['sha256']}`.

R={clean['repeats']}, the required minimum, minimizes runtime. The full-rate lower
bound is 3 * R * script duration = {3*clean['repeats']*clean['script']['duration_ns']/1e9:.9f}
seconds ({3*clean['repeats']*clean['script']['duration_ns']/1e9/60:.2f} minutes), excluding setup.
The locked full script/R requirements cannot fit a roughly ten-minute real-rate
run. E3 used --speed 15 diagnostics with the full packet stream and script clock.
Accelerated mode additionally drains each preceding loop before sending again,
preventing compressed timer probes from overflowing UDP in the sleep mutant.
This drain is disabled at speed 1. Neither speed 15 nor unreadable load earns
bar 3 credit. Full-rate Mac and laptop runs are UNVERIFIED-BY-EXECUTION, owed
to the gate, including fresh full-rate sensitivity for each client type.

## Locked verdict rule

Compute p50, p95, p99 and max of latency per arm (pooled over repeats) and per
repeat. The NOISE FLOOR is |CLOSED - CLOSED-B| per statistic. Bar 3 PASSES when,
for p50, p95 and p99, |OPEN - CLOSED| <= NOISE FLOOR + 1.0 ms AND the byte sequence
of every arm is identical to CLOSED (the bar 1 property, re-checked), AND the
stream's dropped count is reported (drops are allowed; delay is not). Report max
separately, not as a pass criterion, with the top 5 outliers and their steps.

`BAR3_TOLERANCE_MS = 1.0` is the sole tolerance constant. Percentiles linearly
interpolate `(N-1)*p/100`. Pooled rule determines the numeric outcome; per-repeat
outcomes remain visible. A floor that admits a synthetic +2 ms shift is invalid.
A qualified clean pass additionally needs a matching actual sensitivity receipt
whose OPEN timing inequality failed, with complete valid arms and identical
bytes. Same host/runtime, candidate, preset, script, client, clock and kit hashes
are required. If the 2 ms control passes, the instrument explicitly says it
cannot see that delay with this noise floor and bar 3 does not count.

## Executed controls and suites

| Control | Actual observation | Exit |
| --- | --- | --- |
| Planted publisher sleep 0.002 s while a client exists | All arms complete; identical MIDI; OPEN timing inequality RED | {commands[0]['exit_code']} |
| NULL, raw CLOSED vs CLOSED-B | Nonempty byte equality; latency difference within its measured floor | 0 (verify_results.py) |
| Dead OPEN (client creation omitted) | Ordinary presence guard observed clients=0 and rejected it; bridge gone | {commands[2]['exit_code']} |
| Rule assertion pristine / inequality removed / restored | Named +2 ms rejection assertion GREEN / RED / GREEN; scratch source restored | 0 / 1 / 0 |
| Real browser hook, speed 50, one full-script OPEN | Actual Controller/Follow/live checks, real data events, browser/client/bridge gone | 0 |
| Whole Mac suite | {count}; {status} | 0 |
| Four standalone Node checks | All four unchanged check programs returned success | 0 |
| Unchanged real Chromium geometry detector | SUMMARY 1048/1048 PASS; bridge PID gone | 0 |

The initial accelerated sensitivity attempt overflowed UDP and exited 1; this
was invalid arm evidence, NOT sensitivity proof. It led to diagnostic-only
packet draining. See evidence/initial-overflow.json for its error and teardown.
A completed intermediate R=5 control was then rerun after final pinning; only
final-* artifacts below are used for the reported table.

The NULL timing inequality uses the CLOSED/CLOSED-B floor by definition. Its
independent useful assertions are nonzero captures and exact bytes; it does not
prove a quiet host. Diagnostic sensitivity also does not establish full-rate
2 ms resolution. No result here is aggregate show-ready green.

Exact matrix commands and exit codes are in evidence/final-commands.json:

```sh
''']
for row in commands:
    # POSIX shell quoting is for rendering only; execution used argv arrays.
    import shlex
    report.append(shlex.join(row['command'])+f"\n# exit {row['exit_code']}; measured wall {row['wall_seconds']:.3f} seconds\n")
report.append('''```

Other executed commands (from the run root):

```sh
TMPDIR=/tmp/sdlive-e3 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -B -m unittest tests.test_showready_timing -v
.venv/bin/python -B docs/sdlive-e3/check_mutation.py
.venv/bin/python -B docs/sdlive-e3/check_browser_hook.py --script /tmp/sdlive-e3/deck-script.json --chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell
TMPDIR=/tmp/sdlive-e3 .venv/bin/python -B docs/sdlive-e2/check_geometry.py --chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell --scratch /tmp/sdlive-e3/geometry --single-process
TMPDIR=/tmp/sdlive-e3 node tests/ui_controller_check.cjs
TMPDIR=/tmp/sdlive-e3 node tests/ui_controller_macro_check.cjs
TMPDIR=/tmp/sdlive-e3 node tests/ui_reload_check.cjs
TMPDIR=/tmp/sdlive-e3 node tests/ui_sections_check.cjs
.venv/bin/python -B docs/sdlive-e3/verify_results.py /tmp/sdlive-e3/final-sensitivity.json.gz /tmp/sdlive-e3/final-clean.json.gz
```

The raw verifier re-subtracts every non-startup MIDI timestamp from the
recorded causal send, checks the exact sample population, all packet counts and
digests, every arm's raw byte sequence, nonempty streams/drop counts, both load
checks and PID absence. It recomputes the entire summary and requires equality.
It verifies data integrity, not host load qualification.

''')
for title, data in [('Final clean Mac diagnostic', clean), ('Final planted-delay Mac diagnostic', sensitivity)]:
    summary = data['summary']
    report.append(f'## {title}\n\nProducer: its exact timing_ab.py command above. All rows UNVERIFIED-LOAD, speed 15.\n\n')
    report.append('| Repeat | Arm | MIDI / samples | p50 ms | p95 ms | p99 ms | max ms | Stream / publisher drops |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n')
    for r in summary['rows']:
        s=r['statistics_ms']
        report.append(f"| {r['repeat']} | {r['arm']} | {r['midi_messages']} / {s['count']} | {s['p50']:.3f} | {s['p95']:.3f} | {s['p99']:.3f} | {s['max']:.3f} | {r['stream_dropped'] if r['stream_dropped'] is not None else 'no stream'} / {r['publisher_dropped']} |\n")
    report.append('\nPooled statistics and contrasts (max is informational only):\n\n| Statistic | CLOSED | OPEN | CLOSED-B | Noise floor | Open delta | Rule |\n| --- | --- | --- | --- | --- | --- | --- |\n')
    p=summary['pooled_ms']
    for key in ('p50','p95','p99','max'):
        c,o,b=(p[n][key] for n in ('CLOSED','OPEN','CLOSED-B'))
        verdict=summary['rule']['within'].get(key)
        report.append(f"| {key} ms | {c:.3f} | {o:.3f} | {b:.3f} | {abs(c-b):.3f} | {abs(o-c):.3f} | {'informational' if verdict is None else 'PASS' if verdict else 'FAIL'} |\n")
    report.append(f"\nPooled numeric rule: **{'PASS' if summary['rule']['passed'] else 'FAIL'}**. "
                  f"Byte-identical: {summary['byte_identical']}. "
                  f"Synthetic +2 ms visible against floor: {summary['rule']['floor_can_resolve_2ms']}. "
                  f"Bar 3 counts: **{data['bar3_counts']}**.\n\n")
    if not summary['rule']['floor_can_resolve_2ms']:
        report.append('The measured noise floor can hide a uniform +2 ms shift. This run does not count for bar 3, even if the accelerated publisher fault amplifies into a larger timing RED.\n\n')
    report.append('Per-repeat rules: '+', '.join(f"R{r['repeat']}={'PASS' if r['passed'] else 'FAIL'}" for r in summary['per_repeat'])+'.\n\n')
    report.append('Top five individual latencies, including intentional timer delay:\n\n| Repeat / arm | ms | Cause step | Action / phase | MIDI bytes |\n| --- | --- | --- | --- | --- |\n')
    for r in summary['top_five_outliers']:
        report.append(f"| {r['repeat']} / {r['arm']} | {r['latency_ms']:.3f} | {r['cause_step']} | {r['input']['event']['action']} / {r['input']['phase']} | {r['bytes']} |\n")
    report.append('\nBoth pgrep checks per arm, from raw receipts. All have empty stdout and the exact exit-3 stderr quoted above. Load averages are (1, 5, 15 minute), produced by os.getloadavg():\n\n| Repeat / arm | Before exit | Before load averages | After exit | After load averages |\n| --- | --- | --- | --- | --- |\n')
    for run in data['runs']:
        for attempt in run['attempts']:
            b,a=attempt['before'],attempt['after']
            report.append(f"| {run['repeat']} / {run['name']} (try {attempt['attempt']}) | {b['exit_code']} | {b['load_average']} | {a['exit_code']} | {a['load_average']} |\n")
    report.append('\n')
b=browser['arm']
report.append(f'''## Browser hook and cleanup evidence

The check_browser_hook.py command above observed {b['stream']['data_events']}
real stream data events and {len(b['stream']['page_checks'])} actual page samples;
every sample kept Controller visible, Follow on and live. Stream drops:
{b['stream']['dropped']}. This was a one-arm accelerated lifecycle control,
not the gate's browser latency matrix. No E3 UI proof is only node:vm.
Client PID {b['client_cleanup']['pid']} exited {b['client_cleanup']['exit_code']};
browser PIDs {b['browser_cleanup']['pids']} were independently absent; bridge
PID {b['cleanup']['pid']} was terminated, waited and absent. Every final matrix
bridge has the corresponding exact PID/exit/kill-zero proof in its receipt.
The Python stream reader also joins and proves its thread gone.

## Gate handoff and exact commands

Full-rate load-verified Mac timing, Windows suite and timing, real-browser
matrices on both hosts, Ben's hardware check and rollback readiness remain
OWED TO THE GATE/Ben. A push is not deployment. This link only builds the
instrument and reports its bounded diagnostic evidence. Gate must inspect
sensitivity_timing_red and bar3_counts, never infer PASS from an exit-1 control.

The following is copied from the pinned README so the gate can execute it
without this conversation. It uses no accelerated or unverified-load flags.
Windows commands are UNVERIFIED-BY-EXECUTION in E3. Allow at least 117 minutes
per five-triplet full-rate run, plus overhead; each client type needs its own
sensitivity run followed by clean. Run one timing arm at a time.

''')
readme=(ROOT/'scripts/showready/README.md').read_text()
report.append(readme[readme.index('### Gate commands: Mac'):])
(OUT/'REPORT.md').write_text(''.join(report),encoding='ascii')
print(OUT/'REPORT.md')
