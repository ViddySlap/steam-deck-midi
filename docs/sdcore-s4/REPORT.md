# sdcore S4 report

S4 makes the Deck sender portable to import on macOS and fans out every event
to a saved set of receiver targets. Branch: `chain/steamdeck-20260914`.
Predecessor: `8dcb482fe34a4389031e9eae1f015530e62ce4ac` (S3), whose launch record
was fetched and confirmed done. Only S4 is implemented. Ben owns the merge.

## Transport and compatibility

`deck/transport.py` owns `parse_target`, `parse_targets`, `send_action`,
`send_axis`, and `send_heartbeat`, with no X11 imports. The original single-target
`parse_target` still returns a tuple; the new `parse_targets` parses the comma
list. The original send functions still accept a single tuple, including the
`target=` keyword, and now also accept a list in the same argument. All these
functions remain importable from `deck.xinput_send` for existing callers.

Each function encodes once through the unchanged `protocol/messages.py`, then
sends the same bytes to every target in order. The sender still opens one
unbound IPv4 UDP socket and increments `seq` once per event. `run_sender` accepts
`targets: list[tuple[str, int]]`; an explicit list takes precedence over the
compatible `target="host:port,host:port"` shim. Empty lists and invalid addresses
or ports fail before hardware opens. The CLI documents `--targets` and retains
`--target`. No primary target or new feedback consumer was introduced.

IPv4 literals bypass DNS. Hostnames use IPv4 UDP `getaddrinfo` at send time;
successful and failed lookups are cached per host/port for 60 seconds. The first
packet after expiry re-resolves. DNS and `sendto` OSErrors do not stop later
targets. Warnings share a per-target 30-second throttle across all event types.
Resolution is synchronous and subject to the operating system's DNS timeout;
this is not an asynchronous DNS service. Caches live in the sender process.

Both X11 and Xi libraries and their ctypes signatures are initialized only when
`Xi2RawListener` is opened, and reused thereafter. Importing the sender or learn
wizard does not require either library. Native Deck event handling is unchanged.
No runtime dependency was added; requirements and both PyInstaller specs are
unchanged. Every existing public function remains available.

## Settings and TTY behavior

`active_targets` is an ordered list of preset names with an empty-list default
on both the dataclass and loader. Existing settings are loaded without rewriting
them, so copy-if-missing installations keep working after a pull. The example
file includes the new empty field. Unknown, repeated, non-string, or ambiguous
active names are refused. Old duplicate preset names can still load when none
are active; new additions and renames refuse duplicate names.

`validate_ipv4_address` remains strict to preserve its public meaning and its
existing rejection assertion. `validate_target_host` accepts IPv4 or ASCII DNS
labels, including single-label hosts and `.local`; both preset creation and the
loader use it. Invalid IPv4 literals, invalid label characters, and IPv6 are
refused because the sender socket remains IPv4.

The menu offers `m. Select multiple targets`. Numbers toggle names in selection
order, `s` saves through the existing atomic `write_runtime_settings` path, and
`q` cancels without writing. The main menu shows `[active]` and offers
`s. Start active targets`; a subsequent launch uses the saved set. Choosing one
preset number clears a prior set and launches only that target. Saving an empty
set restores the original one-at-a-time workflow. Rename follows the active
name, delete removes only that name, and device/add-preset edits preserve the
set. [deck-fanout.md](../deck-fanout.md) provides the user instructions.

## Verification

Commands run from the run root. Fixture files and copied mutation sources live
under `/tmp/sdcore-s4`; none are show presets. [evidence.json](evidence.json)
records the observed results and hashes. Reproduction scripts are committed.

| Check | Observed result |
| --- | --- |
| Baseline `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | 706 tests in 7.531s; FAILED (errors=2, skipped=1), exactly the assigned Xi import errors. |
| Final full suite, same command with `TMPDIR=/tmp/sdcore-s4` | 769 tests in 5.919s; OK (skipped=1). |
| New transport tests before implementation | RED: deck.transport was absent. |
| `python3 -c "import deck.xinput_send"` | Exit 0 on this Mac, system Python 3.14. |
| `.venv/bin/python -c "import deck.xinput_send"` | Exit 0, venv Python 3.12. |
| `.venv/bin/python docs/sdcore-s4/reversions.py` | 33 deliberate regressions caught; pristine and restored 75-test Deck checks pass. |
| `.venv/bin/python docs/sdcore-s4/smoke.py` | Real UDP: two receivers each got identical action, axis, and heartbeat bytes, seq 1/2/3; one sender source; replies from both returned to that socket. |
| `python3 -m deck.xinput_send --help` | Both CLI spellings advertised without loading native libraries. |
| Existing tests/public API/protocol audit | All 11 original config test/helper method ASTs unchanged; other existing test files untouched; all public functions preserved; protocol bytes unchanged. |
| ASCII and `git diff --check` | Pass. |

There are 30 new tests. The now-importable sender and wizard modules contribute
35 original tests in place of two import-error placeholders, explaining the
count increase from 706 to 769. The existing skip is unchanged.

Assertions inspect fake-socket bytes and destinations, encoded JSON, files at
the atomic replacement boundary, persisted settings before the next menu
action, CLI calls, and the real sender loop's sequence progression. Hardware
listeners/readers and the selector are substituted for the loop test; transport
encoding and fan-out are real. A subprocess makes any shared-library load fail
during import. The UDP smoke uses real sockets on ephemeral loopback ports and
closes them all; it is not a physical Deck/MIDI test or a deployment.

Mutation controls cover fan-out count/order, a two-host cap, failure isolation,
warning throttle, DNS refresh/cache/recovery, list parsing, axis/heartbeat
sends, lazy imports/initialization, sender sequence/list handling, CLI spelling,
legacy defaults, persistence/atomic replacement, invalid names/hosts, selection
preservation, rename/delete, markers, toggling, and the actual launched set.
The first audit revealed that a later single selection masked a missing toggle;
the test now asserts the file before that later action, and the mutation is red.
Removing only the explicit legacy CLI alias leaves equivalent argparse
abbreviation behavior, so that non-regression was excluded from the 33 controls.

## S5 and gate handoff

The Deck has no HTTP API yet, explicitly recorded in [api.md](../api.md) as this
item requires. S5 owns HTTP parity for Deck actions, including target CRUD,
active-set selection, and sender controls. Reuse `with_active_targets` and the
atomic writer so TTY and HTTP share validation; pass every selected host/port to
`run_sender(targets=...)`. Keep the empty-list legacy fallback. Do not claim the
lane-wide parity bar is green before S5 and the gate verify it.

Native Deck TTY/input capture, real XI2/HID operation, travel-router mDNS/DHCP
recovery, multiple physical bridges and MIDI output are OWED TO THE GATE.
Loopback binding worked, so there is no sandbox port-bind debt. A received UDP
reply in the smoke proves socket reachability, not application feedback display.
No installed sender/bridge or harness engine was restarted.

The lane log is outside this executor's writable roots and was not written.
This committed report is the durable next-link baton. A pre-existing cleanup
detail outside S4 remains at `deck/xinput_send.py:777`: `selector.close()` is
after an infinite loop and is bypassed on KeyboardInterrupt. The listener closes
in `finally`; broader resource-lifecycle work belongs to a later item.

## Delivery

Push using S1's command-local SSH transport overrides, without upstream tracking
writes. Before the terminal envelope, compare `ls-remote --heads origin
chain/steamdeck-20260914` under those same overrides with `git rev-parse HEAD`
and require empty `git status --porcelain`. The envelope records the published
commit and equality check. Only the engine advances the next link.
