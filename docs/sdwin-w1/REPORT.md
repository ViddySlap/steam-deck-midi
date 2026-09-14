GUARD GREEN: final compare exit 0; every baseline field unchanged; no python/pythonw under CLONE or LAPTOP WORK.

# sdwin W1 - Windows rail and suite baseline

W1 delivered the pinned rail and guard, created the isolated Windows clone,
and passed the full Python suite on both hosts. This is bar 2's suite baseline;
A/B MIDI replay, controller-view timing, Ben's hardware check and rollback
remain later work. No UI or mapping behavior was changed.

Branch: `chain/steamdeck-20260914`. Entry HEAD:
`1b12b59b18be6963b1d65c591d588be36de55839` (clean).
Final tested code and laptop clone HEAD:
`84e583b329bff502553864d1b5f3663dadd6559a` (clean).
The final report/evidence commit is appended after the last laptop act.
The next link must fast-forward the clone to that report commit before work.

## Route proof - executed first

```sh
ssh -i ~/.ssh/claude-mac-win-key -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 ben@viddyslaptop.local 'hostname & whoami'
```

Exit 0. Output:

```text
ViddySlaptop
viddyslaptop\ben
```

No address fallback was needed or attempted. See `route.txt`.

## Rail and guard controls

All commands below ran from the Mac run root. Local proof scripts are copied
in this report directory; their original execution paths were /tmp/sdwin-w1/.
Every remote script and log was under
`C:\Users\Ben\AppData\Local\Temp\sdwin\w1\`.

| Command/control | Observed result |
| --- | --- |
| `scripts/showready/win_rail.sh run w1 /tmp/sdwin-w1/exit7.ps1` | Exit 7; empty stdout/stderr. |
| `scripts/showready/win_rail.sh run w1 /tmp/sdwin-w1/stderr0.ps1` | Exit 0; stderr `RAIL STDERR control`. |
| `scripts/showready/win_rail.sh run w1 /tmp/sdwin-w1/args.ps1 -Value 'spaces , * literal' -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\w1\argument result.txt'` | Exit 0; spaces, comma and wildcard survived as one literal value. |
| `scripts/showready/win_rail.sh get 'C:\Users\Ben\AppData\Local\Temp\sdwin\w1\argument result.txt' '/tmp/sdwin-w1/argument result.txt'` | Exit 0; local read_bytes equality to `b'spaces , * literal'` passed. |
| `win_rail.sh run w1 scripts/showready/win_guard.ps1 -Mode snapshot -Out C:\Users\Ben\AppData\Local\Temp\sdwin\w1\baseline.json` | Exit 0 before clone creation. |
| Same guard, `-Mode compare -Baseline ...\baseline.json -Out ...\guard-clean.json` | Exit 0 against the untouched baseline. |
| Same compare with `-Baseline ...\baseline-mutant.json -Out ...\guard-mutant.json` | Exit 1; `DIFF $.protectedProcesses[0].pid baseline=5269 current=5268`. Only a COPY of baseline JSON was edited. |
| `win_rail.sh run w1 /tmp/sdwin-w1/leak-control.ps1` | A harmless sleeping venv Python caused guard exit 1 and a nonempty `pythonProcesses` diff; orderly file-signal shutdown then Get-Process proved launcher 276236 and worker 273052 gone. Control script exit 0. |
| `verify_pins(Path('/tmp/sdwin-w1/pin-control'))` through the repo venv Python | Clean exit 0, unpinned scratch edit exit 1, restored exit 0. Exact argv and exception in `pin-control.json`. |
| Windows `kit-check.ps1` | `Ran 6 tests in 2.339s`, `OK (skipped=2)`, exit 0. Real PowerShell compare handles changed fields, Python records, missing observations, both-empty observations and UTF-8 JSON. |

`rail-proof.json`, `guard-clean.txt`, `guard-mutant.txt`, `leak-control.txt`,
`pin-control.json`, and `guard-utf8-green.txt` retain the observations.
Synthetic compare fixtures do not claim live process-collection coverage;
the separate real leak control does exercise Get-Process collection.

Pin generation was executed with:

```sh
find scripts/showready -type f ! -name SHA256SUMS -exec shasum -a 256 {} \; | LC_ALL=C sort > /tmp/sdwin-w1/SHA256SUMS
cp /tmp/sdwin-w1/SHA256SUMS scripts/showready/SHA256SUMS
```

The local `.gitattributes` pins LF line endings on Windows. The test verifies
the exact file set and bytes, forbids `-Command` in the rail, and checks every
SSH/SCP invocation uses the shared complete option array. Mac execution tests
also observe remote exit propagation, stderr, argument quoting, SCP failure
short-circuiting and rejection before transport of unsafe arguments.

## Protected installed state and config evidence

USER CONFIG FOUND:
`C:\Program Files\STEAMDECK MIDI Receiver 2\config`.

Evidence read before implementation:

- `docs/windows-install.md`, `docs/windows-receiver.md`,
  `docs/windows-packaging.md`, both PyInstaller specs and both installer files.
- `installer/windows/steamdeck-midi-receiver-2.iss:40` grants users write access
  to installed config; its shortcuts/Run key supply that directory's map.
- `scripts/windows/start_installed_receiver_v2.ps1:19` derives the local
  settings file from InstallRoot. It was READ, never executed.
- `windows/tray.py:199` puts logs, not config, under LOCALAPPDATA.
- `win_rail.sh run w1 /tmp/sdwin-w1/inspect.ps1` read live Win32_Process command
  lines: both installed tray processes point `--map` into that installed config.

`win_guard.ps1` snapshot plus Python extraction of `baseline.json` recorded:
UDP 0.0.0.0:45123 and TCP 127.0.0.1:7723 owned by tray PID 23640;
tray PIDs 5268 and 23640; loopMIDI PID 16020; their UTC start times;
44 installed files in the metadata digest and 38 config files individually
SHA256-hashed. `baseline.json` contains the full field values and paths.

The Local app directory existed with logs. Roaming and VirtualStore app
config alternatives were absent. The guard records existence/hash lists for
the installed, Local, Roaming and VirtualStore config directories. Missing
required observations or unreadable state is RED, even if both sides are empty.

Orphan checkout reads used only `git --no-optional-locks`:
HEAD `d1367870b93921b115b4c0972c13393792ea5307`, empty porcelain SHA256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
No orphan checkout write or installed configuration write was performed.

## Clone and dependencies

`inspect.ps1` and `clone.ps1` both checked that the clone did not exist.
The successful clone command was:

```powershell
git clone --branch chain/steamdeck-20260914 https://github.com/ViddySlap/steam-deck-midi.git C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc
```

The laptop's existing GitHub access worked. Bundle fallback was not needed
and is UNVERIFIED-BY-EXECUTION. `clone.txt` records initial HEAD equal to Mac
`1b12b59b18be6963b1d65c591d588be36de55839` and the peeled v0.4.9 commit
`e66ff44b36eadb6d43db01680c65279df82cd63c`. This is an annotated tag;
`git rev-parse v0.4.9` alone names its tag object, not that commit.

Commands run by `setup.ps1`:

```powershell
py -3.12 -m venv C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip freeze
```

`py -3.12 --version` returned Python 3.12.10. Pip's last stdout line:

```text
Successfully installed Flask-3.1.3 Pillow-12.3.0 blinker-1.9.0 click-8.5.0 itsdangerous-2.2.0 jinja2-3.1.6 markupsafe-3.0.3 mido-1.3.3 packaging-26.3 pystray-0.19.5 python-rtmidi-1.5.8 six-1.17.0 werkzeug-3.1.8
```

Pip also printed an upgrade notice on stderr; no upgrade was performed.
The full `pip freeze`, Python process exits and empty clone porcelain are in
`setup-retry.txt`. `.venv/` was already ignored; no clone exclude edit was needed.
No installer download or system-wide installation occurred.

## Full suites

Mac command, from the run root:

```sh
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

| Run | Exact summary | Exit |
| --- | --- | --- |
| Entry HEAD | `Ran 821 tests in 11.454s`; `OK (skipped=1)` | 0 |
| Final code | `Ran 828 tests in 11.803s`; `OK (skipped=2)` | 0 |

Windows command, from the isolated clone:

```powershell
C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Executed through `win_rail.sh run w1 /tmp/sdwin-w1/suite.ps1`, with labels
`windows-before`, `windows-after`, `windows-final`, `windows-final-code`.
No `-X utf8` was needed for the suite console. `suite.ps1` sets
PYSTRAY_BACKEND=dummy, BROWSER to a no-op cmd invocation, and TEMP/TMP to
LAPTOP WORK. Actual network tests allocate free ephemeral ports; receiver
CLI tests stub the tray, browser, MIDI and default-port bind edges. No receiver
process was launched with `--tray`; existing in-process tray-mode tests use
fake tray modules. No real MIDI input/output port was opened.

| Windows revision/run | Exact summary | Exit |
| --- | --- | --- |
| Entry 1b12b59 | `Ran 755 tests in 15.125s`; `FAILED (failures=4, errors=5, skipped=1)` | 1 |
| After import/path repairs, 08b426c | `Ran 828 tests in 15.002s`; `FAILED (failures=1, errors=2, skipped=5)` | 1 |
| After socket fixture, 62b0dc4 | `Ran 828 tests in 15.182s`; `OK (skipped=5)` | 0 |
| Final code, 84e583b | `Ran 828 tests in 14.930s`; `OK (skipped=5)` | 0 |

`windows-before.txt` and `windows-after-imports.txt` retain every failed/error
traceback. `windows-final-code.txt` retains the complete final suite output.
`mac-suites.txt` records all Mac summaries.

Platform skips are explicit: Windows skips the two POSIX Mac launcher
execution tests and two Mac rail execution tests. Mac skips the PowerShell
comparison test, which executed on Windows. Both retain the existing skipped
`CcBaseOffsetTests.test_cc_base_override_remaps_channel_ccs` test. No assertion
was deleted to obtain a passing suite; this is not a claim that skipped tests
executed on Windows.

## Every suite red and its classification

| Failing/erroring test | Classification and repair |
| --- | --- |
| Import of `test_deck_control_api` | Windows-only import defect: eager `fcntl` in `deck/xinput_send.py` prevented pure helpers importing. |
| Import of `test_deck_fanout_launch` | Same eager POSIX import defect. |
| Import of `test_deck_sender` | Same eager POSIX import defect. |
| Import of `test_learn_wizard` | Windows-only import defect: eager `termios`/`tty` in `deck/learn_wizard.py`. |
| `test_sender_and_wizard_import_without_loading_shared_libraries` | Same eager POSIX imports. Move imports only into the hardware/terminal methods. New missing-POSIX-modules import control: GREEN, original-imports RED, restored GREEN in scratch. See `imports-*.txt`. |
| `test_section_snippet_creates_missing_file_and_preserves_existing_bytes` (before=None) | Test assumes POSIX paths/bash/python environment. Keep its body and assertions; require POSIX bash. Executes green on Mac. |
| `test_local_section_is_passed_as_one_argument_and_missing_file_still_works` (both sections) | Test assumes executable POSIX shebang fixtures and paths. Same platform precondition; both cases execute green on Mac. |
| `test_disk_active_marker_applies_new_scene` | Test assumes POSIX slash. Replace suffix-only `/Other.json` assertion with equality to the full resolved target Path. MIDI byte/parameter assertions remain unchanged. |
| `test_learn_full_capture_confirm_duplicate_skip_and_save` | Test assumes POSIX pipe can be selected. Replace the fake listener's pipe with a socket pair; every HTTP/file/candidate assertion unchanged. |
| `test_learn_single_action_preserves_siblings_and_cancel_does_not_write` | Same pipe fixture: worker exited and closed descriptor before emit. |
| `test_learn_single_skip_cancels_and_invalid_action_is_rejected` | Same pipe fixture: capture exited, so skip returned no `saved` result. |

The last three tests were exposed only after import repair. Windows
`pipe-control.ps1` ran the fixed fixture GREEN (all three), original fixture
RED (one failure/two errors), then fixed GREEN again, with PID teardown.
See `pipe-control.txt`. No product learning or MIDI send code changed.

Instrument/probe reds during W1, also resolved:

- The initial guard flattened PowerShell-wrapped scalars as objects and
  encountered an empty-property error. Compare now handles primitive types
  before object properties; the real untouched baseline is GREEN and edited
  PID baseline RED. No protected-state difference occurred.
- The new UTF-8 filename fixture exposed ANSI baseline decoding in PowerShell
  5. Guard reads baseline as UTF-8, matching its writer. Same Windows test
  failed before and passed after; see `guard-utf8-red.txt`/`guard-utf8-green.txt`.
- The initial setup script did not retain the Start-Process handle, so it
  observed a null ExitCode after venv creation. It already proved that PID
  gone. Retaining `.Handle` before WaitForExit produced real exit codes for
  subsequent setup and suite runs; no installer workaround was used.
- Two clone-update probes supplied a mistyped expected SHA. Their identity
  assertions refused the probe after a valid fast-forward. Re-running with
  the exact observed full SHA succeeded. The final update derives and checks
  the Mac SHA programmatically; see `update-final-code.txt`.
- An intermediate diff check rejected trailing spaces in a copied table log.
  Only trailing whitespace in that evidence file was trimmed.

## Final laptop act and handoff

`cleanup.ps1` checked the final suite and live-leak-control PIDs with
Get-Process, checked all python/pythonw paths, and confirmed clone HEAD and
empty porcelain. See `cleanup.txt`. Then the LAST laptop act was:

```sh
scripts/showready/win_rail.sh run w1 scripts/showready/win_guard.ps1 -Mode compare -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\w1\guard-final.json' -Baseline 'C:\Users\Ben\AppData\Local\Temp\sdwin\w1\baseline.json'
```

Exit 0, output in `guard-final.txt`. The guard itself takes a fresh
Get-Process inventory. The remote `guard-final.json` remains at that path;
it was not downloaded afterward, preserving the last-act rule.

Use `scripts/showready/README.md` for the next link's exact before/after guard,
clone update and suite commands. Its first laptop act must be a new guard
snapshot and its last a compare. Test arms and logs stay in LAPTOP WORK.
Presets remain untouched; W2 owns the ignored fixture directory.

`git diff 1b12b59..84e583b -- windows/receiver.py windows/midi.py windows/static config mac`
was empty. The only product-source edits are local POSIX import placement in
Deck helpers. No HTTP route was added. The installed runtime was not deployed,
restarted or upgraded. Ben still owns merge and show-readiness acceptance.

## OWED - needs a link

No unresolved W1 test failure or larger Windows defect was found. The existing
cc_base skip remains pre-existing deferred behavior. W1 does not pay the A/B,
controller-view timing, hardware or rollback bars; those remain their assigned
later links/Ben. The parked mac/ H1 work is unchanged and receives no gate
credit from these Python suites.
