# Mac host

The SwiftPM package lives in `mac/` and targets macOS 13 with Swift tools 5.9.
It has no package dependencies and uses the Command Line Tools toolchain.

| Path | Purpose |
| --- | --- |
| `mac/Sources/SteamDeckHostKit/` | Headless library: settings, supervision, guard, health, presentation decisions, controller, HTTP server and menu model. Foundation and Network only. |
| `mac/Sources/SteamDeckMIDI/main.swift` | H1 placeholder prints the Kit version and exits 0. H2 supplies the application and platform adapters. |
| `mac/Tests/SteamDeckHostKitTests/` | swift-testing tests, including real child processes, guard parent death, held sockets and HTTP exchanges. |
| `mac/Tests/SteamDeckHostKitTests/Fixtures/` | TERM-aware, INT-ignoring bridge; immediate exit-3 bridge; stubborn bridge; headless guard driver. |

Build and test from `mac/`:

```sh
swift build --disable-sandbox --jobs 1
swift test --disable-sandbox --jobs 1
```

No XCTest, Xcode project, dependency resolution or `Package.resolved` is needed.
`mac/.build/` is ignored. Tests write only beneath `/tmp/sdhost-h1/`.

## Settings and paths

`HostPaths` defaults to these machine-local host files. Tests inject separate
Application Support and log directories.

- `~/Library/Application Support/SteamDeckMIDI/host.json`
- `~/Library/Application Support/SteamDeckMIDI/bridge.pid`
- `~/Library/Logs/SteamDeckMIDI/bridge.log`

| host.json key | Default |
| --- | --- |
| `bridge_root` | `/Users/viddyslap/Documents/project-workspaces/steam-deck-midi` |
| `python` | `<bridge_root>/.venv/bin/python` |
| `bridge_args` | The argv below. |
| `bridge_env` | `{"PYSTRAY_BACKEND":"dummy","BROWSER":"/usr/bin/true"}` |
| `ui_url` | `http://127.0.0.1:7723` |
| `control_port` | `7724` |
| `autostart_bridge` | `true` |

```json
["-m", "windows.win_recv", "--listen", "0.0.0.0:45123",
 "--map", "config/windows_midi_map.json", "--midi-port", "IAC Driver DECK_IN",
 "--feedback-port", "IAC Driver DECK_OUT", "--pulse-port", "IAC Driver PULSE_OUT",
 "--timeout", "2.0", "--ui-port", "7723"]
```

This is `scripts/mac/run_receiver.command`'s argv after Python, without
`--preset-section`. Verified in `windows/win_recv.py`: `load_startup_config`
loads `BridgeSettings` from the map directory's `bridge.local.json`, passing
the optional CLI override. The host never reads that file. Python remains
responsible for bridge settings, presets and all bridge behavior.

Missing keys use defaults; a missing file does not create or reset settings.
Malformed files raise an error naming the file and remain unchanged. Saves
preserve unknown JSON keys and replace the file by same-directory temporary
file plus rename. Saved JSON retains absent keys as absent, so the Python
default continues to follow a changed `bridge_root`. GET settings expands all
defaults. PUT settings merges top-level keys, validates, saves, then publishes
the new configuration. A supplied `bridge_env` object replaces that entire
object; `{}` removes both host overrides, or supply one key to retain only it.

The bridge inherits the host environment with only those configured overrides.
The dummy pystray backend prevents the bridge's second Mac tray and its stop
crash; BROWSER suppresses bridge-opened browser tabs. No Python code is changed.

Bridge executable, argv, environment and health URL changes apply on its next
start/restart. `supervisor.uiURL` and status `ui_url` continue to name the
active process's health URL until then. The executable must relaunch the host
to apply a changed control port. `autostart_bridge` applies at host launch.

## Supervision and rendering

The states are `stopped`, `starting`, `running`, `stopping`,
`crashed(exitCode, restarts)`, `port-busy(port, pid?)`, and `failed(reason)`.
`HostController.status()` returns state-specific fields, the owned child
`pid` (the guard in production), `bridge_pid`, `healthy`, optional
`health_error`, and the active `ui_url`.

Before a start, orphan reconciliation runs, then loopback TCP/UDP bind probes
inspect the ports in `ui_url`, `--ui-port` and `--listen`. A held port prevents
spawn. `lsof` supplies its PID when available; an unavailable PID remains null.
No foreign port holder is signalled.

The supervisor launches one guard using the host executable:

```text
<host executable> --bridge-guard <host pid> -- <python> <bridge_args...>
```

The guard starts Python in the inherited bridge-root working directory with
null stdin and inherited output/environment. Before spawning, it registers a
kqueue EVFILT_PROC NOTE_EXIT watch on the host. TERM and INT received by the
guard both cause TERM to Python. Host death does the same. After eight seconds
it kills a still-running child, reaps it, removes its matching pidfile and
exits. The supervisor never kills the guard during this ladder. A successful
process spawn alone is not running: `/api/settings` must return HTTP 200 and a
JSON object with a one-second request timeout. HTML, arrays and errors fail.

Both output streams append to `bridge.log`; the in-memory ring retains the
last 2000 complete lines, including a final unterminated line on exit. A clean
stop sends TERM, waits for observed child exit, and only then reports stopped.
The direct launcher used by tests escalates to KILL at eight seconds. An
unrequested exit restarts after 1, 2, 4, 8, 16 and then 30 seconds. Five crashes
inside 60 seconds latch `failed("crashed repeatedly")`; an explicit start resets
that latch. Restart stops the old child before spawning another.

The guard writes `bridge.pid` with `bridge_pid`, `guard_pid` and Unix
`start_time`. On launch, a live leftover bridge PID is inspected using
`ps -o command= -p`. A command containing `windows.win_recv` is reaped with the
TERM/KILL ladder. Before escalation, the command and `ps -o lstart=` birth
signature are checked again. Other live processes are left alone and reported;
inspection failures also refuse startup. A stale dead PID is removed. An old
guard cannot delete a newer guard's record.

`ViewState.resolve` is the only page-versus-sentence decision. Every non-running
state is a Swift sentence even if a health result says healthy. A running but
unhealthy bridge is also a sentence. Only running and healthy yields a page
URL. A WebKit navigation failure becomes a sentence naming its error. H2 feeds
this result to the window instead of showing WebKit's unavailable-page sheet.

## Launch and platform wiring for H2

`LaunchContext.mode(arguments:bundlePath:)` receives arguments without argv[0].
No arguments inside a `.app` select window mode; exactly `--background` selects
background mode; any other arguments select CLI mode, even inside the bundle.
The path check is textual and works for nonexistent paths. The executable
handles login-launch detection as background, sets accessory activation for
background/closed windows, and regular activation while a window is open.

H2 must dispatch `--bridge-guard` through `BridgeGuard.Invocation.parse` and
`BridgeGuard.run` before initializing AppKit. Use the live `HostPaths` for both
the controller and the guard. The production `FoundationProcessLauncher`
defaults to the current executable and host PID; `.direct` is a fixture seam.

H2 constructs one `HostController`, injects its SMAppService `LoginItem`
adapter and window/quit closures, and calls `bootstrap()` before enabling
normal actions. Bootstrap reconciles leftovers even with autostart disabled.
Its error must be shown, not discarded. Start the loopback `ControlServer`
with the configured port. Decisions and controller calls run on the main
actor; Network callbacks and subprocess output return to that actor.

Build NSMenu from `MenuModel.items`. Each entry carries a route and action;
the suite asserts route membership and complete controller-action coverage.
Use the same `ControlRouter` dispatch for local menu actions, honoring
`ControlResponse.afterSend` after consuming a local result. Show Log displays
the GET log response. Launch at Login sends `{"enabled":bool}` to its PUT
route. No additional UI action bypasses the controller.

The `LoginItem` protocol has `enabled`, `requiresApproval`, `notRegistered`
and `notFound` statuses. Its real adapter belongs only in the executable and
uses `SMAppService.mainApp`; the Kit and tests require no app bundle. Quit
waits for stop before invoking the injected application termination closure.

## Control API

Bound to `127.0.0.1:<control_port>` only. The default is 7724 on the Mac;
the Deck sender's independent 7724 API is on the Deck. Every response is JSON.
The server handles one HTTP/1.1 request per connection and closes it, accepts
Content-Length bodies only (maximum 64 KB), limits headers to 16 KB, rejects
duplicate framing headers and transfer encoding, and times out incomplete
requests after five seconds. Non-loopback bind requests are refused.

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| GET | `/host/status` | None | State fields, owned PIDs, health, active UI URL. |
| POST | `/host/bridge/start` | None or `{}` | Status after requesting start; poll until healthy. |
| POST | `/host/bridge/stop` | None or `{}` | Status after owned child exit. |
| POST | `/host/bridge/restart` | None or `{}` | Status after old child exits and new start is requested. |
| GET | `/host/log?lines=N` | None | `{"lines":[...],"path":".../bridge.log"}`; default 200, allowed 0-2000. |
| GET | `/host/login-item` | None | `{"status":"..."}` using one of the four login-item states. |
| PUT | `/host/login-item` | `{"enabled":true}` or `false` | Updated login-item status. |
| GET | `/host/settings` | None | Settings object including defaults and unknown keys. |
| PUT | `/host/settings` | Partial settings object | Persisted settings including defaults and unknown keys. |
| POST | `/host/window/open` | None or `{}` | `{"ok":true}` after calling the window handler. |
| POST | `/host/quit` | None or `{}` | 202 `{"quitting":true}`; after reply, stop bridge and quit host. |

Success is 200 except quit. Bad JSON or invalid values return 400, unknown
paths 404, wrong methods 405, request timeout 408, oversized bodies 413 and
oversized unfinished headers 431. Errors have `{"error":"..."}`. Operational
exceptions return 500. An accepted start can return `port-busy` or `failed`
inside its status JSON; inspect the state rather than treating HTTP 200 as
proof that Python is healthy.
