# sdhost H1 report

H1 implements the SwiftPM package and headless SteamDeckHostKit on
`chain/steamdeck-20260914`. Entry HEAD was
`e50b78f799d4425c4d9a66310bc4518dc4d6f6e5`, with empty porcelain. The executable
prints `SteamDeckHostKit 0.1.0` and exits; window, SMAppService adapter and app
bundle wiring remain H2 work. No app was installed or deployed.

The locked design is implemented in the Kit: unknown-key-preserving atomic
settings, owned-process supervision, the separate parent-watching bridge
guard, orphan reconciliation, log ring/file capture, JSON health probe,
sentence/page decisions, launch context, login-item protocol, controller,
loopback HTTP server, route table and menu model. The bridge Python code and
all machine-local config/preset files are unchanged.

## Verification

The Python suite ran at HEAD before edits:

```text
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
Ran 821 tests in 10.833s
OK (skipped=1)
```

Final Python run:

```text
Ran 821 tests in 9.436s
OK (skipped=1)
```

The required Swift command was run with both required switches:

```sh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi/mac
swift build --disable-sandbox --jobs 1 && swift test --disable-sandbox --jobs 1
```

Build: exit 0. Full test command: exit 1. Exact test summary:

```text
Test run with 33 tests failed after 34.243 seconds with 2 issues.
```

32 tests passed; one parameterized test has two executor-denied cases.

The full suite remains enabled. This is a bounded completion under the house
rule for executor-only obligations, not aggregate Swift green. The only
remaining failures are the two parameter cases of the real ps-backed orphan
identity test, described below. Real bind/listener and process spawn work in
this executor. The build uses Swift 6.1.2 and the built-in Testing Library
124.4 with zero package dependencies; there is no Package.resolved or XCTest.

Evidence is stored here as ASCII-escaped output:

- `swift-build.txt`: required build result.
- `swift-tests.txt`: complete final Swift test output, including both denied cases.
- `python-summary.txt`: before/after Python summaries and the one repaired documentation-test regression.
- `mutations.json`: eight baseline/RED/restored-GREEN controls.
- `verify-mutations.py`: reproduces those controls in a fresh `/tmp/sdhost-h1/` subtree.
- `deck-doc-control.txt`: the existing Deck route assertion still fails if an actual Deck route disappears from its table.

The eight mutations remove unknown-key preservation, accept HTML health,
render a stopped bridge as a page, break a menu route, remove environment
overrides, ignore held ports, bypass login registration, and refuse owned
orphan reaping. All eight first passed, failed on mutation, and passed after
restoration. Mutations ran in a scratch copy; the source tree was never
mutated by these controls.

The real process tests assert stdout and stderr in both the ring and file,
the two environment values in actual child output, null stdin and cwd, TERM
handling despite ignored INT, KILL escalation, and `kill(pid, 0)` returning
ESRCH after stop. Exit-3 fixtures prove backoff and the five-crash latch using
an injected clock. Held TCP and UDP sockets remain held and their owner stays
alive. Guard tests kill an owned fake host with SIGKILL, observe the bridge
gone within ten seconds, check TERM/INT forwarding, and run a stubborn child
through the actual eight-second TERM/KILL ladder. The guard removes its
pidfile only after exit. No process listing or broad kill command is used by
those tests.

The ephemeral Network listener exercises every route and observes its actual
JSON and controller side effects. It also rejects bad JSON, wrong methods,
unknown paths and invalid values; raw HTTP tests reject oversized and chunked
bodies. Non-loopback bind inputs are refused. The menu/route/action invariant
and both Mac documentation inventories stay in the suite.

## Documentation test correction

Appending a third service to `docs/api.md` exposed an assumption in
`test_every_deck_route_is_documented`: it read everything after the Deck
heading through end-of-file, treating Mac routes as Deck routes. The first
post-edit Python run therefore reported `FAILED (failures=1, skipped=1)`.
H1 changed only that test's section extraction to stop at the next level-two
heading. Its `self.assertEqual(documented, self.server.routes)` assertion is
unchanged; every registered Deck route is still required and extras are still
rejected. Removing `/api/learn/cancel` from a scratch copy of the Deck table
produced RED and restoration produced GREEN. The bridge source and all other
Python tests are untouched.

## OWED TO THE GATE

1. Run the complete required Swift command outside this executor's process
   inspection restriction. The retained
   `GuardTests.leftoverPIDReapsOnlyMatchingCommand` cases for true and false
   both fail while spawning `/bin/ps`, before making a signalling decision.
   Exact error, with the Unicode apostrophe escaped to keep this report ASCII:

   ```text
   Cannot run /bin/ps: The operation couldn\u2019t be completed. Operation not permitted
   ```

   The original underlying error was
   `Error Domain=NSPOSIXErrorDomain Code=1 "Operation not permitted"`.
   Gate acceptance is the real matching live fixture reaped (ESRCH and pidfile
   removed) and the real nonmatching live fixture untouched (still alive and
   pidfile byte-identical). The separate injected-identity tests pass against
   real live fixture PIDs but do not pay for real `ps` inspection.

2. The lane log is outside this executor's writable roots. The one append
   attempt failed exactly with:

   ```text
   [Errno 1] Operation not permitted: '/Users/viddyslap/Documents/ViddyVault/Ai playground/batons/lane-steamdeck-20260914.md'
   ```

   This committed report is the durable H1 handoff. No alternate vault write
   or permissions bypass was attempted.

## Public Kit types

- `HostKit`: Kit version for the executable.
- `HostError`: readable, equatable operation/validation error.
- `HostPaths`: injectable host settings, pidfile and log locations.
- `AtomicFile`: same-directory temporary write plus rename.
- `HostSettings`: validated JSON object, typed defaults and unknown-key preservation.
- `ProcessSpecification`: executable, arguments, cwd and full environment.
- `ChildProcess`: the single owned child handle and signal operations.
- `ProcessLaunching`: injectable process creation with output/exit callbacks.
- `FoundationProcessLauncher`: real Process implementation, guard mode by default.
- `FoundationProcessLauncher.Mode`: guarded production launch or direct fixture launch.
- `HostClock`: injectable monotonic time and cancellable sleeps.
- `SystemHostClock`: system uptime and Task sleep adapter.
- `BridgeLog`: 2000-line ring plus append-only captured output file.
- `PortTransport`: TCP or UDP.
- `BridgePort`: required port/protocol derived from settings and argv.
- `PortChecking`: injectable occupancy probe.
- `BindPortChecker`: real loopback bind probes and optional lsof PID lookup.
- `ProcessInspection`: signal-zero liveness and read-only subprocess inspection.
- `BridgePIDRecord`: atomic bridge/guard/start record and matching removal.
- `OrphanResult`: absent, reaped or foreign live PID result.
- `ProcessIdentifying`: injectable command-line and process birth identity.
- `SystemProcessIdentity`: real ps command and lstart inspection.
- `OrphanReconciling`: asynchronous leftover-process reconciliation interface.
- `OrphanReaper`: verified-owned orphan TERM/KILL/reap behavior.
- `BridgeGuard`: child lifetime tied to a kqueue host-exit watch and stop signals.
- `BridgeGuard.Invocation`: strict guard argv parser.
- `BridgeSupervisor`: child lifecycle, health, logging, stop and crash retry decisions.
- `HealthTransport`: injectable HTTP transport for health.
- `URLSessionHealthTransport`: real URLSession transport.
- `HealthChecking`: asynchronous bridge-health interface.
- `HealthProbe`: one-second HTTP 200 JSON-object health gate.
- `BridgeState`: stopped, starting, running, stopping, crashed, portBusy or failed.
- `HealthResult`: healthy or unhealthy with reason.
- `PageLoadResult`: loaded or failed with navigation error.
- `ViewTone`: neutral, progress or error sentence tone.
- `ViewState`: pure sentence/page decision.
- `LaunchMode`: window, background or CLI.
- `LaunchContext`: textual bundle/argument launch rule.
- `LoginItemStatus`: four SMAppService-facing statuses.
- `LoginItem`: headless status/enable protocol for the H2 adapter.
- `ControllerAction`: exhaustive host action vocabulary.
- `ControlRoute`: HTTP method/path and controller action.
- `RouteTable`: all eleven host routes.
- `HostMenuItem`: readable title plus required control route.
- `MenuModel`: seven menu entries used by H2 to build NSMenu.
- `HostController`: shared host action methods and injected window/quit handlers.
- `HTTPFailure`: HTTP status plus JSON error text.
- `ControlRequest`: parsed method, path, query and JSON body.
- `ControlResponse`: JSON status/body plus post-send quit action.
- `HTTPRequestParser`: bounded Content-Length HTTP/1.1 framing.
- `ControlRouter`: exhaustive route-to-controller dispatch.
- `ControlServer`: Network listener pinned to 127.0.0.1.

## H2 handoff

Read [mac-host.md](../mac-host.md) for integration details and the API table.
Dispatch guard mode before AppKit, using `BridgeGuard.Invocation.parse` and
`BridgeGuard.run`. A normal app launch creates one live `HostPaths`, loads
settings, constructs the supervisor/controller and calls `bootstrap()` even
when autostart is false. Pass the live executable to the guarded launcher if
argv[0] is not already an absolute executable path. Never use direct mode for
the application. Bootstrap failures must be visible.

Use `supervisor.uiURL` with its state and health to resolve `ViewState`; this
preserves health/URL identity while settings changes await bridge restart.
Supply the H2 SMAppService adapter in the executable only. Build NSMenu from
the model, dispatch its routes through the shared router, and honor local
`afterSend` actions after consuming responses. Network dispatch already does
this after transmitting Quit's 202 response. `HostController.quit()` stops
the bridge before invoking the application termination closure.

No engine restart, next-link launch, pause change, launchctl, sfltool, tccutil,
real signing or installation was performed. Publish uses the required
command-local SSH override, with remote SHA equality and empty porcelain
checked before the final engine envelope. Ben owns merging this branch.
