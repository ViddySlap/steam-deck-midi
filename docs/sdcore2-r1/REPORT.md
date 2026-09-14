# sdcore2 R1: git-pull boot and first-run section repair

R1 repairs F1 from docs/sdcore-gate/REPORT.md on branch
`chain/steamdeck-20260914`, starting at
`f809be11fb6c5c19cb9b557f2a03496c07e47690`. The S1, SG, and SJ launch records
were fetched from the engine. All are done; SJ held the lap for F1 and F3.
Only F1 is this link's item. F3 belongs to the next repair link. F2 (SIGINT/CPU)
and F4 (header wrap) remain Ben's backlog choices.

## Default preset and platform rule

Compared parsed `git show 5d778eb:config/presets/default.json` with S1's
`sections.windows`: equal. Restored the exact v0.4.9 bytes, not a reserialization.
The tracked default now has 56 flat mappings and applies to every bridge.

| Document | Bytes | SHA256 |
| --- | ---: | --- |
| Before: sectioned default at f809be1 | 18161 | 2f7f3cf6943609c92068c7943801e2b948e6001de872a59eb099414605d7055c |
| After: flat default, identical to 5d778eb | 7388 | 5ebcf1e85dc3881d59e1658103ec17a0a3add438571679b3fca4f30b0f9a52a1 |

`windows/win_recv.py:37` defines `load_startup_config`, the same socket-free
loader called by `main` at line 281. The only platform choice is in that
function, with an injected platform argument; main supplies `sys.platform`.
A missing local file and absent argv selection on darwin chooses macbook only
if the active preset contains that section. The entire candidate mapping must
validate before the local file is created. Flat presets create no local file.
Other platforms, or no macbook section, retain the existing named error.
An existing local file (including null or an unavailable section) and explicit
argv selections retain their prior semantics. Reload behavior is unchanged.

`windows/bridge_settings.py:41` adds `save_if_missing`. It writes a complete
sibling temporary file and publishes it atomically with a hard link, which
cannot replace an existing destination. If another launcher wins the race, its
selection is loaded and used. Temporary files are removed on success and error.
The existing public `save` method still atomically replaces the file for an
intentional settings edit and still returns None. Startup logs one creation
line naming bridge.local.json (`windows/win_recv.py:59`).

`scripts/mac/run_receiver.command:45` uses the same BridgeSettings creation
method to initialize an absent file to macbook and then passes its selection
as one argv element. An existing file is left byte-identical. The direct Python
entry point also handles first run, so lap 2's Mac host need not supply a flag.
No separate Mac host implementation exists in this checkout yet.

All 36 config files were hashed before and after: only the tracked default
changed. PTZ.json, EDM Show.json, their backups, .active, bridge.local.json,
engine configs, and launcher-local settings were not modified. Evidence:
[evidence/config-preservation.json](evidence/config-preservation.json).
No runtime dependency was added. Every existing public function remains.

## Windows back-fill finding

The three existing launchers already back-fill a v0.4.9 local file that lacks
preset_section. No PowerShell change was needed. In each file, the example is
loaded at line 25, all missing properties are added at lines 34-40, and the
updated local file is saved at lines 42-44. The example defines
`"preset_section": "windows"` at
`config/windows_receiver_settings.example.json:6`.

| Launcher | Read back-filled value | Existing bridge.local.json override | Pass flag |
| --- | --- | --- | --- |
| scripts/windows/start_receiver.ps1 | 67 | 68-74 | 75-77 |
| scripts/windows/start_installed_receiver.ps1 | 64 | 65-71 | 72-74 |
| scripts/windows/start_installed_receiver_v2.ps1 | 64 | 65-71 | 72-74 |

UNVERIFIED-BY-EXECUTION: pwsh is absent on this Mac. The existing source contract
test passes, but actual PowerShell execution remains OWED TO BEN'S WINDOWS BOX.

## Verification

Commands ran from `/Users/viddyslap/Documents/project-workspaces/steam-deck-midi`.
All scratch trees and temporary fixtures were under `/tmp/sdcore-r1/`.
Full suite command, before and after:

```sh
TMPDIR=/tmp/sdcore-r1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

| Control | Result |
| --- | --- |
| Baseline at f809be1 | Ran 795 tests in 10.226s; OK (skipped=1); exit 0 |
| Repaired suite | Ran 807 tests in 10.716s; OK (skipped=1); exit 0 |
| Focused startup/launcher controls | 19 tests OK before the two additional atomic-publication tests; all 21 included in the final suite |
| bash -n scripts/mac/run_receiver.command | Exit 0 |
| Extract and execute actual Mac section-resolution snippet in a temp tree | Missing file created with macbook; existing sentinel bytes preserved |
| Whole Mac launcher with captured argv | Missing file yields --preset-section macbook; section with spaces remains one argument |
| git diff --cached --check | Exit 0 |

Twelve new tests in `tests/test_upgrade_boot.py` observe parsed MIDI mappings,
active paths, local-file JSON and bytes, publication races, and cleanup after a
write failure. The upgrade test copies the checkout's tracked default, rather
than an inline legacy fixture, into a temp config tree with no marker or local
file and calls the exact loader used by main. It covers darwin, win32, and
linux without globally patching sys.platform.

Before the default restoration, this control failed on all three platforms:
darwin incorrectly required local initialization, and win32/linux raised the
named missing-section error. The gate's exact pre-repair exit-2 scenario was
also reproduced in a real child below.

Two existing tests were deliberately adapted to the changed contract:

- `test_missing_selection_on_sectioned_startup_names_sections` now supplies an
  existing file with null selection instead of deleting it. All original exit-2
  and available-section assertions are unchanged. An absent file on darwin is
  now the successful first-run case tested separately.
- `test_local_section_is_passed_as_one_argument_and_missing_file_still_works`
  replaces the assertion that absent-file argv omits --preset-section with
  assertions for macbook argv and persisted JSON. All existing-file, argv-prefix,
  exit-code, and space-preservation assertions remain.

An AST comparison confirms no other existing test body changed. Full suite
captures are in evidence/suite-before.log and evidence/suite-after.log.
Non-ASCII characters in captured test output are backslash-escaped to comply
with the lane's ASCII rule; original captures remain in scratch.

## Mutation controls

```sh
.venv/bin/python -B docs/sdcore2-r1/scripts/mutate.py
```

All eight mutants are RED; their pristine and restored controls are GREEN,
with restored SHA256 equal. The script uses a git-exported scratch tree and
copies only scoped candidate files when run before commit. Bytecode writing is
disabled. Evidence: [evidence/mutations.log](evidence/mutations.log).

| Reverted behavior | World asserted by the failing test |
| --- | --- |
| Restore S1's sectioned tracked default | Platform-independent upgrade mapping and absence of local file |
| Disable macOS first-run default | Macbook mapping and persisted identity |
| Default on every platform | Named refusal and no local file on win32/linux |
| Remove macbook availability check | Original named missing-selection error |
| Replace an existing identity during initialization | Existing sentinel bytes and selected windows identity |
| Omit identity persistence | Local JSON and selected mapping |
| Ignore argv override | Windows mapping with no local file created |
| Restore old Mac launcher snippet | Missing local file must be created |

A preliminary mutation removed only the startup file-existence guard. That
mutation was behavior-neutral because save_if_missing still honored the
existing file; it was replaced with the actual overwrite regression above.

## Real gate upgrade controls

The staged candidate tree was exported by git, with no ignored local files:
`6d816b9de27ef2e765c622e68a21a20884261de5`. It contains the exact product and test
blobs being committed; only this report and evidence were added afterward.

```sh
.venv/bin/python -B docs/sdcore2-r1/scripts/verify_boot.py --revision 6d816b9de27ef2e765c622e68a21a20884261de5
```

The script also supports `--revision HEAD` after commit. Each arm uses
`git archive` in its own temp tree. The bridge command in every arm is:

```sh
<run-root>/.venv/bin/python -B -u -m windows.win_recv \
  --map config/windows_midi_map.json --listen 127.0.0.1:45199 \
  --dry-run --no-ui --no-engines --no-pulse --no-osc-relay
```

| Export and local state | Observed result |
| --- | --- |
| 5d778eb, no marker/local file | Boots; PID 65205 owns UDP 45199 |
| f809be1, no marker/local file | Exit 2, preset section None unavailable: macbook, windows |
| f809be1, local macbook, no marker | Boots; PID 65376 owns UDP 45199 |
| Repaired candidate, no marker/local file | Boots; PID 65387 owns UDP 45199; local file stays absent |
| Repaired candidate, sectioned show active, no local file | Boots; PID 65406 owns UDP 45199; local JSON now macbook |

Socket ownership was observed with lsof restricted to the exact child PID,
not inferred from the listening log. Every booting child was stopped with
SIGTERM and reaped with return code -15. UDP 45199 was successfully rebound
before and after every arm, proving release. No live run-root bridge was started
or stopped. There is no sandbox bind debt for R1. Evidence:
[evidence/boot-controls.log](evidence/boot-controls.log) and the five
`evidence/upgrade-boot-*.log` captures.

## Handoff

R1 is ready for the gate to repeat the same controls on committed HEAD. The next
repair link owns F3, the bridge tray Quit HTTP route. Preserve the flat default
and both first-run paths. Stop any bridge with SIGTERM. Do not fold F2 or F4 into
this lap. Windows launcher execution remains owed as stated above. No deployment,
physical Deck, or Windows-host proof is claimed by this source repair.

This report and its evidence are included in the scoped R1 commit. After commit,
the link must push with the mandated SSH transport override, verify the remote
branch equals local HEAD, verify empty porcelain, and only then send its one
terminal envelope. The engine owns advancing the next link.
