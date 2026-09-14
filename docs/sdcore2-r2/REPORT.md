# sdcore2 R2: graceful bridge Quit over HTTP

R2 repairs only F3 from docs/sdcore-gate/REPORT.md. Branch:
`chain/steamdeck-20260914`. Parent:
`c246c944b989000a47c3c73ac5eea642fe10ae7f` (R1, fetched launch state done).
R1's F1 repair is preserved. F2 (SIGINT/CPU) and F4 (header wrap) remain
Ben's backlog choices. No signal handling or engine timing was changed.

## Behavior and ownership

`POST /api/shutdown` returns HTTP 202 with `{"stopping": true}` and requests
normal bridge teardown. Only a loopback REMOTE_ADDR is accepted; non-loopback,
missing, and malformed addresses get 403, including after stopping begins.
Forwarded headers confer no permission. IPv4 and IPv6 loopback are covered.
Repeated accepted calls return the same 202 and invoke the callback only once.
A standalone MappingUIServer without an attached bridge callback returns 503.
GET is refused with 405; only POST and Flask's automatic OPTIONS are registered.

There is one bridge stop function: `ActionReceiver.request_shutdown` at
windows/receiver.py:288. It sets the receiver's stop event; the serve loop
checks that event at windows/receiver.py:1014. Both Windows tray modes and
HTTP receive that same bound function in windows/win_recv.py:407, :426, :455.
The Flask route is at windows/ui_server.py:317.

The existing serve-loop finally now calls release_all BEFORE engine shutdown,
then closes UDP and both MIDI inputs (windows/receiver.py:1053). It retains the
existing held-control release implementation, including panic, instead of
adding a second release path. The owner in win_recv closes the preset watcher,
MIDI output and OSC relay, then stops HTTP (windows/win_recv.py:457 and :469).

HTTP uses the existing Werkzeug dependency with an owned server handle
(windows/ui_server.py:751). Request threads are non-daemon, so server_close
waits for their replies; the owner's stop also joins the HTTP serve thread.
This ensures the shutdown response is written before process exit, without a
timer. A real TCP test holds the 202 response open while stop runs, proves
stop cannot finish early, then reads the complete JSON and rebinds the port.

TrayApp joins the bridge before returning to win_recv's final cleanup
(windows/tray.py:463). The old unconditional os._exit timer was removed because
it could cut off MIDI/HTTP teardown. The existing grace_seconds constructor
argument remains accepted for compatibility, but no longer forces process exit.
The icon is created before the bridge starts; an early bridge exit also stops
the icon when ready. HTTP-triggered bridge completion stops the tray too.
Native UI execution debt is listed below; menu callbacks and owner wiring were
executed with fake icons on this Mac.

Every existing public function remains present. An AST comparison of every
existing test function against R1 found zero changed or removed functions.
There is no new runtime dependency: Flask already requires Werkzeug, and the
v2 PyInstaller spec already collects it. Neither spec nor requirements changed.

## API bar update for the gate

The gate's original report is unchanged. Replace its F3 table interpretation
with this row when judging this repair:

| Affordance | Route in docs/api.md | Evidence |
| --- | --- | --- |
| Windows sidecar tray Quit and --tray Quit | POST /api/shutdown | Both callbacks and HTTP are wired to receiver.request_shutdown; real serve-loop release/close and HTTP reply tested. Native tray clicks remain gate-owned. |

The bridge inventory is now 29 explicit method/path registrations plus Flask's
static route. The existing inventory test was run after route registration and
BEFORE documentation: it failed specifically on `('POST', '/api/shutdown')`.
After documenting the route it passes in the whole suite. README.md now has the
two requested Mac stop/backlog lines, including the curl and SIGTERM commands.
No Deck route or UI layout changed.

## Verification

All commands ran from the run root. Scratch and temporary fixtures were under
`/tmp/sdcore-r2/`. The suite is unittest; no pytest or alternate gate was used.

```sh
TMPDIR=/tmp/sdcore-r2 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
TMPDIR=/tmp/sdcore-r2 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -B docs/sdcore2-r2/scripts/mutate.py
.venv/bin/python -B docs/sdcore2-r2/scripts/verify_shutdown.py --headless-tray
```

| Check | Observed result |
| --- | --- |
| Baseline at R1 | 807 tests in 9.014s; OK (skipped=1); exit 0 |
| New route tests before implementation | 5 tests; 9 failures including subtests; missing route returns 404 |
| Route plus inventory before docs | 6 tests; only inventory fails, naming POST /api/shutdown |
| Final whole suite | 821 tests in 11.045s; OK (skipped=1); exit 0 |
| AST preservation | All existing test functions identical; every existing public function present |
| git diff --check | Exit 0 |
| Config preservation | All 36 files byte-identical across both live attempts |

Fourteen added tests cover route registration, status/body, loopback guard,
idempotence, no-callback refusal, real UDP lifetime, MIDI bytes at the output
interface, teardown order, in-flight HTTP replies, both tray callback paths,
owner cleanup, HTTP-driven tray exit, and early bridge exit. The real
ActionReceiver test uses DryRunMidiOut with output-call spies and an ephemeral
UDP socket; it receives real note and CC action packets, holds both, requests
shutdown twice, joins within 3 seconds, asserts note_off and CC off exactly,
asserts panic once, checks fileno == -1, and binds that same UDP port again.
No success assertion depends on a log line.

Logs are in evidence/. Captured non-ASCII test/bridge output is backslash-escaped
in the committed copies; raw output remains in scratch.

## Mutation controls

All mutations ran in a git-exported scratch tree with only the named candidate
files copied over before commit, with bytecode disabled. Each row has its own
pristine GREEN, mutant RED, restored GREEN, and restored SHA256 equality.
The script is repeatable on committed HEAD.

| Reversion | Failing world assertion |
| --- | --- |
| Route missing | POST route registration and method inventory |
| Loopback guard removed | 403 and no stop event for off-loopback requests |
| Route callback removed | Stop event must be set |
| Idempotence guard removed | Callback invoked once across two 202 responses |
| Serve loop ignores stop event | Real worker must exit within 3 seconds |
| release_all omitted | Held note and CC must receive their off messages |
| Release moved after engines | Recorded release_all precedes engines_stop |
| UDP close omitted | fileno -1 and successful same-port bind |
| HTTP request threads made daemon | Owner cannot finish while reply is pending |
| HTTP owner close omitted | Main must close the UI server |
| --tray callback removed | Tray and HTTP must carry receiver.request_shutdown |
| Tray join omitted | Tray owner cannot return before bridge cleanup |
| Early-exit guard omitted | An already-ended bridge must stop the ready icon |

Result: ALL_13_BITE. See evidence/mutations.log and scripts/mutate.py.

## Real source process and capability debt

The probe first proves UDP 45123 and TCP 7723 are free, then starts only its own
child. It uses the Mac launcher's receiver argv, including the current macbook
section and all three IAC port names, plus --dry-run. BROWSER=/usr/bin/true
suppresses the optional browser tab. It does not run the launcher shell, whose
log writes and first-run settings initialization are unnecessary here.

The exact native-tray arm aborted with return code -6 (SIGABRT), after the UI
startup log and before UDP ownership could be established. It ran as a single
process at concurrency one. No causal claim about that abort is proven here;
changing only PYSTRAY_BACKEND=dummy allowed the source process to complete.
The default backend is therefore the current capability boundary, by inference,
not an attributed product regression. See evidence/live-exact.log and
bridge-exact.log. The gate must classify/reproduce the native arm on its host.

The second arm selected pystray's dummy backend, preserving the same argv and
all real receiver/engine/HTTP code. Flask test-client and real socket checks
also passed; there was no port-bind denial.

| Observation | Headless-tray source process |
| --- | --- |
| Engines | 14 loaded, 13 active, from the existing config tree |
| Identity | GET settings: macbook, active EDM Show.json, expected IAC port names |
| Socket ownership | lsof restricted to child PID 71275: UDP *:45123 and TCP 127.0.0.1:7723 LISTEN |
| Request | curl -X POST http://127.0.0.1:7723/api/shutdown |
| Complete response | HTTP 202, {"stopping":true} |
| Process result | Exit 0, 0.106 s from curl start to reaped child |
| Release | Fresh binds to UDP 45123 and TCP 7723 both succeed |
| Config | 36 files before/after, zero changed hashes |

See evidence/live-shutdown.log, bridge-headless.log, and config-preservation.json.
The failed arm was already dead; the successful arm stopped through HTTP.
The script's fallback cleanup uses SIGTERM only if its own child remains alive.
No existing bridge or engine process was stopped or restarted.

OWED TO THE GATE: exact native-tray source boot and native Windows tray clicks
in both modes, including HTTP-driven quit of --tray. The fake-icon tests prove
callback behavior and owner joins but are not native UI proof. No physical
Deck, real MIDI hardware, deployment, or merged-main claim is made.

## F2 note and handoff

F2 remains open. This link did not discover a verified root cause and did not
change signal handling. The existing timeout calculation still takes the
minimum of poll, fade, and engine intervals (windows/receiver.py:1028); no CPU
fix is included. The existing KeyboardInterrupt handler remains at :1051.
README.md explicitly says Ctrl-C is currently ignored on macOS and lists
tray/host Quit, the new HTTP route, or kill -TERM as the stop options.

RG/RJ should repeat the mutation script and source shutdown probe on committed
HEAD, pay the native UI debt above, and keep F2/F4 outside this lap. R1's flat
default and first-run identity behavior are untouched. Reports and evidence are
included in this scoped commit. Push uses the required SSH transport override;
remote HEAD equality and empty porcelain must be verified before the terminal
envelope. The engine owns advancement; this link will not start RG itself.
