GUARD GREEN: final compare exit 0; all protected baseline fields unchanged; pythonProcesses=0.

# sdwin W2 - Installed fixtures and Windows launcher execution

W2 captured read-only fixtures and discharged R1's Windows existing-file
back-fill execution debt. Windows EDM Show and PTZ equal the Mac backups and
Windows sections by sorted-key JSON. All three unchanged launchers back-fill
and pass `windows`; existing `grandma` settings stay byte-identical and are
passed through. A genuinely absent settings file fails before launch on all
three. This first-run finding is recorded below, as required by W2 arm (c).
No product code, existing test assertion, MIDI send path, UI or mac/ file changed.

Entry and tested clone HEAD: `72d3a21239fbb79d3b2552c690bee4769b604c74` on
`chain/steamdeck-20260914`. The clone fast-forwarded from W1's tested code HEAD
`84e583b329bff502553864d1b5f3663dadd6559a` with `git -C <CLONE> pull --ff-only`.
The commit for this report is made after the last laptop act. The next link
must pull that report commit. No installed runtime deployment occurred.

## Commands and locations

All Mac commands ran from
`/Users/viddyslap/Documents/project-workspaces/steam-deck-midi`.
Mac scratch: `/tmp/sdwin-w2/`. Laptop scripts, arms and logs:
`C:\Users\Ben\AppData\Local\Temp\sdwin\w2\`.
The committed `.ps1` files here are exact copies of the final scripts run from
Mac scratch. Capture/download scripts refuse existing destination trees;
they are one-time capture records, not overwrite/refresh tools.

First laptop act:

```sh
scripts/showready/win_rail.sh run w2 scripts/showready/win_guard.ps1 -Mode snapshot -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\w2\before.json'
```

Exit 0. The later `capture.ps1` pulled the clone and listed the installed
layout. `inspect.ps1` and `capture.ps1` read both live tray command lines.
Both point `--map` at the path below; the actual image name includes `-Tray`.
No alternate config location was needed.

## Installed source and fixture manifests

Confirmed installed user-config directory:
`C:\Program Files\STEAMDECK MIDI Receiver 2\config`.
Confirmed live map: `config\windows_midi_map.json` under that install root.
Active marker contains `EDM Show.json`, read from the copied `.active` file
with Python `Path.read_text()`.

Windows destination:
`C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures\windows-installed\`.
Mac destinations under the run root:
`.showready/fixtures/windows-installed/` and `.showready/fixtures/mac/`.
Both contain `MANIFEST.sha256` as JSON with schema `sdwin-fixtures/1` and
per-file `source`, `destination`, `relative`, `bytes`, `sha256_before`,
`sha256_after`, `sha256_copy`. The Windows manifest retains its original
Windows source/destination paths and is byte-identical on the Mac.

Executed acquisition commands:

```sh
scripts/showready/win_rail.sh run w2 /tmp/sdwin-w2/capture.ps1
python3 /tmp/sdwin-w2/download.py
```

Windows capture uses `Get-FileHash` before `Copy-Item`, after it, and on the
copy; all three must match before the destination is marked read-only.
Download uses the pinned rail's `get` for every file and verifies SHA256 again.
Mac capture used `hashlib.sha256(src.read_bytes())`, `shutil.copyfile`, then
SHA256 of source and copy, and `chmod(0o444)` on each copy and manifest.
Only copies were written; no source was opened for writing.
`.showready/` is now ignored. No fixture or local configuration is committed.

Manifest summary, produced with Python `json.loads`, `len(entries)`,
`sum(e['bytes'] for e in entries)` and `hashlib.sha256(manifest.read_bytes())`:

| Fixture set | Files | Bytes (excluding manifest) | Before/after/copy/download hashes | Manifest SHA256 |
| --- | ---: | ---: | --- | --- |
| windows-installed | 11 | 57621 | All equal | `7c6dad5b30ab05f1d005d1d722964ec847e6db19726bf0eb500d8bbcf10e331d` |
| mac | 5 | 57753 | All equal | `0c1b3014f6fba58f76b54f1e0c8f843788f0fbbb2993d20e0415841bc2200524` |

Windows relative file list (all preset files, including backups):

- `macro_library.json`
- `presets/.active`
- `presets/.active.bak-20260529-pre-v047-sync`
- `presets/default.json`
- `presets/default.json.bak-20260529-pre-v047-sync`
- `presets/EDM Show.json`
- `presets/PTZ.json`
- `presets/test 1.json`
- `presets/v1 Default.json`
- `windows_midi_map.json`
- `windows_receiver_settings.local.json`

Mac relative file list: `presets/EDM Show.json`, `presets/PTZ.json`,
`presets/EDM Show.json.v049.bak`, `presets/PTZ.json.v049.bak`, and
`presets/default.json`. After both full suites, all five source hashes were
re-read and still matched the manifest's `sha256_before` values.

## Preset shapes and Windows-vs-Mac comparison

Command producing every mapping count and comparison below:

```sh
python3 docs/sdwin-w2/analyze.py --fixtures .showready/fixtures --out /tmp/sdwin-w2/preset-analysis.json
```

It decodes UTF-8/BOM JSON, compares `json.dumps(document, sort_keys=True)` and
compares each union of mapping keys by parsed value. Counts include effective
shared plus section mappings; these fixtures have no shared mappings.
Markers are not preset JSON and are excluded from mapping counts.

| Host | Preset | Shape / section names | Selected section | Keys | Counts by mapping type |
| --- | --- | --- | --- | ---: | --- |
| windows-installed | EDM Show.json | flat | flat | 56 | axis_split_cc=2, axis_to_cc=2, cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| windows-installed | PTZ.json | flat | flat | 52 | cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| windows-installed | default.json | flat | flat | 56 | axis_split_cc=2, axis_to_cc=2, cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| windows-installed | default.json.bak-20260529-pre-v047-sync | flat | flat | 62 | cc=3, macro_cc=7, note=44, relative_cc=6, staged_note_macro=2 |
| windows-installed | test 1.json | flat | flat | 63 | axis_to_cc=3, cc=3, macro_cc=7, note=42, relative_cc=6, staged_note_macro=2 |
| windows-installed | v1 Default.json | flat | flat | 61 | axis_split_cc=4, axis_to_cc=5, cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| mac | EDM Show.json | sectioned / macbook, windows | windows | 56 | axis_split_cc=2, axis_to_cc=2, cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| mac | EDM Show.json | sectioned / macbook, windows | macbook | 56 | axis_split_cc=2, axis_to_cc=2, cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| mac | EDM Show.json.v049.bak | flat | flat | 56 | axis_split_cc=2, axis_to_cc=2, cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| mac | PTZ.json | sectioned / macbook, windows | windows | 52 | cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| mac | PTZ.json | sectioned / macbook, windows | macbook | 52 | cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| mac | PTZ.json.v049.bak | flat | flat | 52 | cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |
| mac | default.json | flat | flat | 56 | axis_split_cc=2, axis_to_cc=2, cc=3, macro_cc=7, note=36, relative_cc=4, staged_note_macro=2 |

| Windows preset | Mac comparator | Full sorted-key JSON equal | Differing mapping keys | Other differing top-level keys |
| --- | --- | --- | --- | --- |
| EDM Show | mac-backup | True | `[]` | `[]` |
| EDM Show | mac-windows-section | True | `[]` | `[]` |
| PTZ | mac-backup | True | `[]` | `[]` |
| PTZ | mac-windows-section | True | `[]` | `[]` |

The Windows files and Mac files have different raw byte hashes (formatting),
but the requested full parsed JSON comparisons are equal. Later A/B arms
should use the installed Windows fixtures for the show mappings. This
comparison is configuration evidence; W3/W4 still owe simulated-input MIDI
byte captures and A/B comparison against tag v0.4.9.

## Executed Windows launcher arms

```sh
scripts/showready/win_rail.sh run w2 /tmp/sdwin-w2/arms.ps1 -Label final
```

Exit 0 for the recorder. PowerShell version, measured by `cleanup.ps1` using
`$PSVersionTable.PSVersion.ToString()`: `5.1.26100.9168`.
Launchers run directly from the clone with `-RepoRoot` (source launcher) or
`-InstallRoot` (installed launchers) selecting the temporary arm root.
No launcher was edited; the exact-diff requirement is therefore empty.
The captured launcher SHA256 values match the Mac source after Git's Windows
LF-to-CRLF checkout conversion; raw cross-host hashes differ for line endings.
All nine recorded hashes were checked against those converted bytes.
The executable each parameterized root resolves is an Add-Type-built C#
console stub that only appends its PID, executable path and argv to JSONL,
then exits 0. It imports no Python, receiver or MIDI code. The two installed
launchers call that stub for both their MIDI-port preflight and receiver call.

Each non-absent arm starts with `Copy-Item` from the read-only captured
installed settings. Only the TEMP copy is made writable. Temporary example
and local settings use `listen=127.0.0.1:45282`, `ui_port=7782`, `no_ui=true`,
`midi_port=SDWIN_ARGV_ONLY_NO_MIDI`, and empty `feedback_port`. `Get-NetUDPEndpoint`
and `Get-NetTCPConnection -State Listen` checked those alternate ports free
before each arm. No executable opens a socket or MIDI port. `PYSTRAY_BACKEND`
is `dummy` and `BROWSER` is the W1 no-op command. No argv contains `--tray`.

Arm `missing-key` removes `preset_section`; `grandma` sets only that added key
to `grandma`; `absent-file` never creates local settings. Before/after file
hashes use `Get-FileHash -Algorithm SHA256`. Get-Process checks each child PID
after exit; full receiver/Python inventories before/after each arm are equal
and nonempty. See [raw arms](evidence/arms.json) for all exact argv arrays,
executable paths, saved JSON, inventory identities, exit codes and errors.

| Launcher | Arm | Settings SHA256 before | Settings SHA256 after | Captured argv | Exit | Receiver started |
| --- | --- | --- | --- | --- | ---: | --- |
| start_receiver.ps1 | missing-key | `5e5989f680d216769f43de6cf0921753a569848144d6feeef975c3605e3f5366` | `34837d235dcc2c366f22abe9fa348f012e52494a3d5e9f46fedd69cad38afe46` | A1 below | 0 | No |
| start_receiver.ps1 | grandma | `096bf84cdab2305a52565928265f6c2ec7f129019b4767480ac1a7529a61db8b` | `096bf84cdab2305a52565928265f6c2ec7f129019b4767480ac1a7529a61db8b` | A2 below | 0 | No |
| start_receiver.ps1 | absent-file | `ABSENT` | `ABSENT` | [] | 1 | No |
| start_installed_receiver.ps1 | missing-key | `5e5989f680d216769f43de6cf0921753a569848144d6feeef975c3605e3f5366` | `34837d235dcc2c366f22abe9fa348f012e52494a3d5e9f46fedd69cad38afe46` | A4 below | 0 | No |
| start_installed_receiver.ps1 | grandma | `096bf84cdab2305a52565928265f6c2ec7f129019b4767480ac1a7529a61db8b` | `096bf84cdab2305a52565928265f6c2ec7f129019b4767480ac1a7529a61db8b` | A5 below | 0 | No |
| start_installed_receiver.ps1 | absent-file | `ABSENT` | `ABSENT` | [] | 1 | No |
| start_installed_receiver_v2.ps1 | missing-key | `5e5989f680d216769f43de6cf0921753a569848144d6feeef975c3605e3f5366` | `34837d235dcc2c366f22abe9fa348f012e52494a3d5e9f46fedd69cad38afe46` | A7 below | 0 | No |
| start_installed_receiver_v2.ps1 | grandma | `096bf84cdab2305a52565928265f6c2ec7f129019b4767480ac1a7529a61db8b` | `096bf84cdab2305a52565928265f6c2ec7f129019b4767480ac1a7529a61db8b` | A8 below | 0 | No |
| start_installed_receiver_v2.ps1 | absent-file | `ABSENT` | `ABSENT` | [] | 1 | No |

### Exact captured argv

Each array below is one invocation, in order.

A1: `start_receiver.ps1`, `missing-key`:

```json
[
  [
    "-m",
    "windows.win_recv",
    "--listen",
    "127.0.0.1:45282",
    "--map",
    "C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\w2\\final\\start_receiver-missing-key\\config\\windows_midi_map.json",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI",
    "--timeout",
    "2.0",
    "--preset-section",
    "windows",
    "--verbose"
  ]
]
```

A2: `start_receiver.ps1`, `grandma`:

```json
[
  [
    "-m",
    "windows.win_recv",
    "--listen",
    "127.0.0.1:45282",
    "--map",
    "C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\w2\\final\\start_receiver-grandma\\config\\windows_midi_map.json",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI",
    "--timeout",
    "2.0",
    "--preset-section",
    "grandma",
    "--verbose"
  ]
]
```

A4: `start_installed_receiver.ps1`, `missing-key`:

```json
[
  [
    "--check-midi-port",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI"
  ],
  [
    "--listen",
    "127.0.0.1:45282",
    "--map",
    "C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\w2\\final\\start_installed_receiver-missing-key\\config\\windows_midi_map.json",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI",
    "--timeout",
    "2.0",
    "--preset-section",
    "windows",
    "--verbose"
  ]
]
```

A5: `start_installed_receiver.ps1`, `grandma`:

```json
[
  [
    "--check-midi-port",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI"
  ],
  [
    "--listen",
    "127.0.0.1:45282",
    "--map",
    "C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\w2\\final\\start_installed_receiver-grandma\\config\\windows_midi_map.json",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI",
    "--timeout",
    "2.0",
    "--preset-section",
    "grandma",
    "--verbose"
  ]
]
```

A7: `start_installed_receiver_v2.ps1`, `missing-key`:

```json
[
  [
    "--check-midi-port",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI"
  ],
  [
    "--listen",
    "127.0.0.1:45282",
    "--map",
    "C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\w2\\final\\start_installed_receiver_v2-missing-key\\config\\windows_midi_map.json",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI",
    "--timeout",
    "2.0",
    "--preset-section",
    "windows",
    "--verbose",
    "--no-ui",
    "--ui-port",
    "7782"
  ]
]
```

A8: `start_installed_receiver_v2.ps1`, `grandma`:

```json
[
  [
    "--check-midi-port",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI"
  ],
  [
    "--listen",
    "127.0.0.1:45282",
    "--map",
    "C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\w2\\final\\start_installed_receiver_v2-grandma\\config\\windows_midi_map.json",
    "--midi-port",
    "SDWIN_ARGV_ONLY_NO_MIDI",
    "--timeout",
    "2.0",
    "--preset-section",
    "grandma",
    "--verbose",
    "--no-ui",
    "--ui-port",
    "7782"
  ]
]
```

### Findings and fix decision

- All existing-file missing-key arms write `windows` and pass
  `--preset-section windows`, exit 0. All `grandma` arms pass that value and
  retain the entire file byte-for-byte. No back-fill repair was needed;
  `tests/test_section_launchers.py` and its existing assertions are unchanged.
- All absent-file arms exit 1, leave settings absent, and invoke no stub.
  At `scripts/windows/start_receiver.ps1:35`,
  `scripts/windows/start_installed_receiver.ps1:35`, and
  `scripts/windows/start_installed_receiver_v2.ps1:35`, strict mode rejects
  `.PSObject.Properties.Name` on the empty object initialized at line 30.
  The exception is `PropertyNotFoundStrict`. This is a real first-run defect,
  recorded under W2's instruction to observe arm (c), not to fix it.
  It does not invalidate the executed v0.4.9 existing-file upgrade arms.
  The lane owner should explicitly assign any repair; no successor was added.
- `docs/preset-sections.md` now records the per-launcher execution and this
  absent-file limitation, with a link to this report. R1's report remains an
  accurate historical record of its then-unexecuted proof.

## Verification and detector controls

```sh
python3 docs/sdwin-w2/verify.py --fixtures .showready/fixtures --arms docs/sdwin-w2/evidence/arms.json
python3 docs/sdwin-w2/controls.py --fixtures .showready/fixtures --arms docs/sdwin-w2/evidence/arms.json --scratch /tmp/sdwin-w2
```

Verifier: exit 0; `GREEN: 16 fixture hashes; 9 executed arms; nonempty process/argv controls`.
Controls operate only on new scratch copies. Each planted fault below causes
verifier exit 1; pristine and every restored copy cause exit 0:

- One extra byte in the copied Windows EDM Show fixture.
- Empty arm records.
- Empty argv observations in an otherwise successful arm.
- Wrong saved back-fill section.
- Changed `grandma` settings hash.
- Both process inventories empty.

A separate planted note change to `BTN_A` is reported as exactly that key by
both EDM Show comparison rows. Differences are information, so the analyzer
exits 0 and its JSON is asserted. Restoring the bytes returns the whole
verifier to exit 0. These are fixture/record detector controls, not live MIDI
A/B controls. See [controls](evidence/controls.json).

Full Mac suite, both runs, from the run root:

```sh
TMPDIR=/tmp/sdwin-w2 PYSTRAY_BACKEND=dummy BROWSER=true .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

| Run | Observed summary | Exit |
| --- | --- | ---: |
| Entry | `Ran 828 tests in 11.512s`; `OK (skipped=2)` | Python exit not separately retained by the initial tail wrapper |
| Final | `Ran 828 tests in 12.859s`; `OK (skipped=2)` | 0 |

Windows full suite in the clean clone, using W1's suite script copied to W2:

```sh
scripts/showready/win_rail.sh run w2 /tmp/sdwin-w2/suite.ps1 -Label windows-w2
```

Exact Windows Python command:

```powershell
C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

`Ran 828 tests in 14.635s`; `OK (skipped=5)`; exit 0. Suite PID 268372 was
waited for and Get-Process proved it gone. No `-X utf8` was needed. TEMP/TMP
were the W2 work directory, with dummy pystray and W1's no-op BROWSER.
Skips match W1: Mac skips the actual PowerShell comparison test and the
pre-existing cc_base test; Windows skips the two POSIX Mac-launcher tests,
two POSIX rail tests, and that pre-existing cc_base test. Existing tests run
unchanged. Committed console logs are ASCII-escaped and have trailing
whitespace trimmed; hashes of fixture bytes are never normalized. The absent-settings first-run bug is not covered by this suite;
a green suite does not erase its real red arm.

## Probe errors, retained and classified

A local pre-commit raw launcher SHA check also correctly detected Windows
CRLF versus Mac LF checkout bytes; comparing the exact LF-to-CRLF conversion
matched every recorded hash. The initial diff check found trailing whitespace
in captured console tables, which was trimmed only in evidence text.

The first capture lookup used the image name without `-Tray` and refused
before any copy. A live layout/Win32_Process listing confirmed the real name;
using `STEAMDECK-MIDI-RECEIVER-2*` captured the expected paths successfully.
The first arm recorder hit PowerShell's single-result array unwrapping at its
summary count after proving that first stub PID gone; `@($argv).Count` fixed
that recorder-only error.

The next recorder ran all arms but stalled serializing extended metadata on
`Get-Content -Raw` error strings. An exact Win32_Process command-line identity
check authorized stopping only the owned recorder PID 273344. Its immediate
Get-Process check still saw process teardown in progress; the subsequent
`probe-gone.ps1` proved it and parent 274976 absent. That intentionally stopped
remote command returned 255; SSH continued answering on the pinned route.
No alternative route was attempted. A premature SCP request for the still
unwritten result returned file-not-found, not a transport outage.

The final recorder uses `[IO.File]::ReadAllText` for plain error strings,
retains each completed row immediately, and limits child waits to 30 seconds.
It uses actual installed-settings copies. All final rows and cleanup succeeded.
Only final-arm JSON earns executed-result credit; preliminary stdout does not.

## Final laptop cleanup and guard

`win_rail.sh run w2 /tmp/sdwin-w2/cleanup.ps1` exited 0. It re-read final arm
PIDs, every saved preliminary/final argv PID, suite PID and stopped recorder
PIDs; Get-Process found all absent. A fresh Win32_Process inventory found no
process executable under CLONE or LAPTOP WORK and no other W2 PowerShell/cmd
shell. Get-Process separately rejected unreadable or leaked Python paths.
The clone retained the tested HEAD and empty porcelain. See
[cleanup](evidence/cleanup.txt).

The LAST laptop act was:

```sh
scripts/showready/win_rail.sh run w2 scripts/showready/win_guard.ps1 -Mode compare -Baseline 'C:\Users\Ben\AppData\Local\Temp\sdwin\w2\before.json' -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\w2\after.json'
```

Exit 0: `GUARD GREEN: compare; protected state observed; pythonProcesses=0`.
No laptop act followed, including downloads. `after.json` remains on the
laptop; [guard-final.txt](evidence/guard-final.txt) retains stdout.
The baseline and comparison cover the unchanged installed tray PIDs 5268 and
23640, loopMIDI PID 16020, their start times, port ownership of UDP 45123/TCP
7723, installed file metadata, all user-config hashes, and orphan HEAD/status.
Those identities/counts come from `win_guard.ps1`'s snapshot in
[evidence/guard-before.json](evidence/guard-before.json).

## Handoff to W3/W4 and the gate

Use `.showready/fixtures/windows-installed/presets/EDM Show.json` and `PTZ.json`
(and their adjacent captured dependencies). The identical remote copies live
under the shared laptop fixture root above. They are flat. The Mac user presets
are sectioned with `macbook` and `windows`; their `.v049.bak` copies are flat.
Run the verifier before consuming captured files; never rewrite the originals.
The fixtures are ignored and remain host-local; a git clone does not contain them.

No source repair, installer, dependency change or API route was added. W1's rail
pins, parked mac/ kit, MIDI send path and UI are unchanged. The next link must
start with its own guard snapshot, then fast-forward the clone to this report
commit. W2 pays fixture capture and Windows launcher execution only. The full
show-ready bar still requires A/B MIDI replay, timing with the controller view,
Ben's hardware check and rollback proof in their assigned later work.
