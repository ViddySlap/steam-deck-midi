LAPTOP: not touched by A4 (no ssh, no guard snapshot needed). Base of this link: ef5c20ce8d563bf3913f6c7b85a161a58670662e.

# sdauto A4 - F4 header fix and the 0.5.0 candidate version

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed (Ben's fallback (b)). Scratch: /tmp/sdauto-a4/.
No tag, no GitHub release, no installer build: those are lap sdrc's and Ben's.

## Summary

- F4: one scoped CSS rule, `header select { width: auto; }`, right after the global form-control
  rule. The header is ONE row at 1440x900 in real Chromium (48 px, was 106 px); the widths of all
  28 form controls outside the header are identical before and after.
- 0.5.0 candidate: `VERSION` 0.5.0, `windows/build_fingerprint.py` APP_VERSION 0.5.0 with
  GIT_COMMIT / GIT_COMMIT_SHORT / BUILD_TIME_UTC = `source`, new `GET /api/version`, the version in
  the status bar (`v0.5.0 (source)`; `v0.5.0` when frozen), README / TODO / release checklist.
- Mac suite: `Ran 997 tests ... OK (skipped=2)` (baseline at ef5c20c: `Ran 989 tests ... OK (skipped=2)`).

## 1. F4 change and why it is scoped

Cause (sdcore-gate F4): `windows/static/index.html:357-363`
`input[type="number"], input[type="text"], select, textarea { ... width: 100%; }` also matched the
header's `#sectionSelect` (class `btn`, no width of its own). Inside the wrapping `.hdr-actions`
flex row the 100% select took its own line, pushing the header to three rows.

Change: `windows/static/index.html:364-365`

```css
  /* F4: header controls size to their content so the header stays one row. */
  header select { width: auto; }
```

Why this form: specificity (0,0,2) beats the global `select` (0,0,1) and applies only to a select
inside `<header>` (today only #sectionSelect). The global rule is untouched, so every form field
elsewhere keeps width 100%. Nothing in controller_view.css or the controller view touched the
header (grep `header|hdr` in windows/static/controller/: no header rules); the tab bar is unchanged.

### DOM-free check: tests/ui_version_check.cjs (runs in the suite via tests/test_ui_node.py)

Part 1 parses the real markup (ancestry of each id) and both shipped stylesheets (index.html
`<style>` and the linked controller_view.css, with `@media` max/min-width evaluated at 1440 and
1024), then resolves the `width` cascade (importance, specificity, order, inline style). It fails
on any width rule whose selector it cannot evaluate that could target the element, and on no
matching rule (never a vacuous pass). Assertions at 1440x900 and 1024x768:
`#sectionSelect` = `auto`; `#saveAsInput`, `#macroEditorType`, `#searchInput` = `100%`.
Part 2 runs the shipped script: the boot line calls `/api/version` and renders the label, and
`loadVersion()` renders `v0.5.0 (source)` (frozen false), `v0.5.0` (frozen true), empty on error.

`node tests/ui_version_check.cjs` -> exit 0, `SUMMARY 29/29 PASS`.

Fires (run by hand, and kept permanent in
`tests/test_ui_node.py::test_version_check_fires_on_planted_header_faults`):
- against HEAD ef5c20c's index.html: exit 1, `FAIL 1440x900.sectionSelect width auto ... {"value":"100%","selector":"select"}` (and 1024x768).
- F4 line removed from the current file: exit 1, the same two FAILs, `SUMMARY 25/27 PASS`.
- over-broad fix `select { width: auto; }`: exit 1, `FAIL 1440x900.macroEditorType width 100%` (no-visual-change side).
- restored: exit 0.

### Real-browser measurement (the executor note allows it; the gate re-confirms)

Command (scripts committed under docs/sdauto-a4/scripts/, evidence under docs/sdauto-a4/evidence/):

```
.venv/bin/python docs/sdauto-a4/scripts/header_measure.py --root "$PWD" --revision HEAD     --tag before --out /tmp/sdauto-a4/browser --ui-port 17941 --listen-port 47941
.venv/bin/python docs/sdauto-a4/scripts/header_measure.py --root "$PWD" --revision WORKTREE --tag after  --out /tmp/sdauto-a4/browser --ui-port 17942 --listen-port 47942
```

Each arm copies tracked `windows protocol config` bytes for that revision into scratch, the
verified `.showready/fixtures/mac/presets` (EDM Show active), boots
`windows.win_recv --dry-run --no-engines --no-pulse --no-osc-relay --no-browser` with
PYSTRAY_BACKEND=dummy and BROWSER=/usr/bin/true on free loopback ports, drives
chrome-headless-shell-1208 (playwright-core), then SIGTERMs and proves the bridge pid gone
(`os.kill(pid, 0)` -> ProcessLookupError). `pgrep -fl "chrome-headless-shell|windows.win_recv"`
after every run: exit 1, no lines.

| arm | viewport | header height | centre spread of header items | one row | #sectionSelect width | version label |
|---|---|---|---|---|---|---|
| before (HEAD) | 1440x900 | 106 | 66 px | no | 861 | none (`/api/version` 404 text/html) |
| after | 1440x900 | 48 | 1 px | YES | 160 | `v0.5.0 (source)` |
| before (HEAD) | 1024x768 | 106 | 66 px | no | 861 | none |
| after | 1024x768 | 85 | 1 px | no (see below) | 160 | `v0.5.0 (source)` |

"One row" = header height <= 50 and the vertical centres of the logo, h1 and every visible
`.hdr-actions` child within 4 px. At 1024x768 all controls are on one line (centre spread 1 px);
the header is 85 px because the h1 title wraps inside its `flex: 1` box (h1 box 0-84). That is the
pre-existing "logo text wraps at 1024" note from sdview-gate 2g, not in this item's bar (1440x900).

No visual change elsewhere: every `input, select, textarea` outside `<header>` (28 in both arms,
both viewports), computed width and box width, before vs after: `diff_keys []`. Control arm
(`--plant-old '  header select { width: auto; }' --plant-new '  select { width: auto; }'`):
`diff_keys ['as_curve', 'macroEditorType']` at both viewports, so the diff detects a change.

PNGs: evidence/before-1440x900.png (three-row header, full-width select),
evidence/after-1440x900.png (one row, status bar `v0.5.0 (source)`), evidence/after-1024x768.png.

Controller picture with the shorter header: the pinned `tests/ui_controller_geometry.cjs` cannot
measure the live view (PRE-EXISTING instrument defect, sdlive-gate REPORT line 89 and owed item 392:
`networkidle` never arrives while the Controller holds its EventSource; reproduced here, exit 1
timeout at :118). I ran the sdlive gate's independent `docs/sdlive-gate/scripts/geom_live.cjs`
through the same boot on both arms (`--geometry`): HEAD `SUMMARY 126/126 PASS`, candidate
`SUMMARY 126/126 PASS` (evidence/geom-live-*.log). Its fire side was proven by the sdlive gate;
I did NOT re-run its mutations (UNVERIFIED-BY-EXECUTION in this link).

## 2. Version touchpoints (before -> after, at ef5c20c -> this commit)

| file:line | before | after |
|---|---|---|
| VERSION:1 | `0.4.9` | `0.5.0` |
| windows/build_fingerprint.py:3 | `APP_VERSION = "0.4.9"` | `APP_VERSION = "0.5.0"` |
| windows/build_fingerprint.py:4 | `GIT_COMMIT = "2ae8f4ef55bf16bc621e9bad7916329df86eed8e"` (a stale 0.4.9 build) | `GIT_COMMIT = "source"` |
| windows/build_fingerprint.py:5 | `GIT_COMMIT_SHORT = "2ae8f4ef55bf"` | `GIT_COMMIT_SHORT = "source"` |
| windows/build_fingerprint.py:6 | `BUILD_TIME_UTC = "2026-08-06T20:09:39Z"` | `BUILD_TIME_UTC = "source"` |
| windows/ui_server.py:9, :19 | - | `import sys`; `from windows import build_fingerprint, engine_config_api` |
| windows/ui_server.py:424-432 | - | `GET /api/version` -> `{version, git_commit, build_time_utc, frozen}`; reads the module attributes per request; `frozen = bool(getattr(sys, "frozen", False))` |
| docs/api.md:17 | - | `/api/version` row |
| windows/static/index.html:653 | - | `<span id="appVersion" class="status-text"></span>` in the status bar |
| windows/static/index.html:909-918 | - | `loadVersion()`: `v<version>` plus ` (source)` when not frozen; title `commit <git_commit>, built <build_time_utc>`; empty on error |
| windows/static/index.html:2159 | - | boot `loadVersion();` (before `loadAll();`, so the node checks' `loadAll` strip still works) |
| README.md:12 | `## Current status (v0.4.9)` | `## Current status (0.5.0 candidate)` + README.md:14-16 "candidate on branch chain/steamdeck-20260914, NOT released. The latest release is v0.4.9." |
| TODO.md:4 | `The project is on **v0.4.9**` | TODO.md:4-5 `The latest release is **v0.4.9**; **0.5.0** is a candidate on branch ..., NOT released.` |
| docs/windows-release-checklist.md:12-27 | - | new `## Version Bump` step naming VERSION, build_fingerprint.py, README.md, TODO.md, the .iss fallback, and the `/api/version` post-build check |
| docs/windows-release-checklist.md:34, 39, 41, 44, 49, 55, 64, 65 | `build_exe.ps1`, `dist\STEAMDECK-MIDI-RECEIVER.exe`, `build_installer.ps1`, `STEAMDECK-MIDI-RECEIVER-Setup-<version>.exe` (x3), `STEAMDECK MIDI Receiver` | `build_exe_v2.ps1`, `dist\STEAMDECK-MIDI-RECEIVER-2.exe`, `build_installer_v2.ps1` (notes it rebuilds the EXE), `installer-output\STEAMDECK-MIDI-RECEIVER-2-Setup-<version>.exe` (x3), `STEAMDECK MIDI Receiver 2` |
| scripts/windows/build_exe_v2.ps1:34-41, :86, :98-107 | unchanged | confirmed: reads VERSION, `git -C $RepoRoot rev-parse HEAD`, and rewrites all four fingerprint names; now pinned by a test |
| scripts/windows/build_installer_v2.ps1:25-32, :55, :64 | unchanged | reads VERSION, passes `/DAppVersion=$appVersion`, names `STEAMDECK-MIDI-RECEIVER-2-Setup-{version}.exe` |
| installer/windows/steamdeck-midi-receiver-2.iss:3-5, :28 | unchanged | `#define AppVersion "0.1.0"` is only an `#ifndef` fallback; the v2 installer script always overrides it |
| windows/win_recv.py:227-232 | unchanged | startup log now prints `version=0.5.0 commit=source built_utc=source` from source |

Measured on a live scratch bridge (header_measure.py, `API_VERSION` line): HEAD `GET /api/version`
-> 404 `text/html` (no route); candidate -> 200 `application/json`
`{"build_time_utc": "source", "frozen": false, "git_commit": "source", "version": "0.5.0"}`.

NOT changed, flagged for lap sdrc: `docs/github-release.md:14-21, :60` still names the v1 scripts
and outputs (`build_exe.ps1`, `STEAMDECK-MIDI-RECEIVER-Setup-<version>.exe`). The item scoped the
name correction to the Windows checklist; the release doc needs the same correction before sdrc uses it.

## 3. Tests added (no existing assertion changed)

- `tests/test_ui_server.py::VersionApiTests` (4): patched fingerprint -> exact JSON with
  `frozen: false` (and asserts the suite is not frozen); `sys.frozen=True` -> `frozen: true`; the
  checked-in fingerprint is served; GET only (POST 405).
- `tests/test_ui_server.py::VersionAgreementTests` (3): VERSION == APP_VERSION read from the files
  (ast, not the cached module); the comparison reports a diverged copy; build_exe_v2.ps1 still
  reads VERSION and git and its template writes exactly the four names the module defines
  (CRLF-safe for the Windows clone).
- `tests/test_ui_node.py::test_version_check_fires_on_planted_header_faults`: F4 removed RED,
  over-broad fix RED, restored GREEN.
- `tests/ui_version_check.cjs` (auto-discovered by `test_all_ui_node_checks`).
- Existing api-inventory test and HtmlApiBarTests cover the new route and the UI literal
  (`HTML API bar: 25 paths` -> `26 paths` in the suite output).

Mutant sweep (`.venv/bin/python docs/sdauto-a4/scripts/mutants.py`, scratch copy, evidence/mutants.log):
pristine `Ran 12 tests ... OK`; all 9 `RED-AS-NAMED`: M1 F4 rule removed, M2 route removed, M3
api.md row removed, M4 VERSION diverges, M5 frozen always true, M6 `(source)` marker dropped, M7
build template loses GIT_COMMIT, M8 boot `loadVersion();` removed, M9 route serves the short commit.
`SWEEP PASS`, exit 0.

## 4. Checks

| command | result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` at ef5c20c (baseline) | exit 0, `Ran 989 tests in 18.622s`, `OK (skipped=2)` |
| same, this commit | exit 0, `Ran 997 tests in 18.599s`, `OK (skipped=2)` |
| `node tests/ui_controller_check.cjs`, `ui_controller_macro_check.cjs`, `ui_reload_check.cjs`, `ui_sections_check.cjs`, `ui_version_check.cjs` | exit 0 each (reload and sections checks unchanged) |
| header_measure.py before / after / control / geometry arms | exit 0 each; table above |
| mutants.py | exit 0, SWEEP PASS 9/9 |
| `git status --porcelain` after commit | empty (checked before reporting) |

One RED observed and classified during the link: a suite run at 14:20 failed
`test_showready_rail.ShowreadyPinTests` (2) on `scripts/showready/__pycache__/deck_script.cpython-312.pyc`,
created 14:14:49 by my first header_measure.py run importing `deck_script` without `-B`.
RESIDUE of this link, not a code defect: removed the directory, set `sys.dont_write_bytecode`
in the harness, re-ran: 997 OK.

Bars 1 and 3: not run by this link (Mac suite and node checks only, per the rules). This change
touches no MIDI path (HTML/CSS, one read-only GET route, version strings, docs). OWED TO THE GATE.

## 5. What the gate must confirm in a browser

1. At 1440x900 the header is one row (logo, title, Factory Reset, preset, Section label + select,
   Add/Rename/Delete section, Save & Apply) on Mac Chromium AND on the Windows laptop's browser
   (font metrics differ there; this link measured the Mac only).
2. The Section select is content-sized and still opens and switches sections.
3. The status bar shows `v0.5.0 (source)` from a source run; a frozen build would show `v0.5.0`
   (only checkable after sdrc builds the EXE).
4. No other form field changed width (Global Settings grids, mapping editor, macro editor, dialogs).
5. The controller picture at 1024x768 / 1366x768 / 1440x900 / 1920x1080 (geom_live 126/126 here).
