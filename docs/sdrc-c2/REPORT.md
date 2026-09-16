GUARD COMPARE (last laptop act, 2026-09-16T09:26:09Z): `GUARD GREEN: compare; protected state observed; pythonProcesses=0`, rail exit 0 (evidence/L05-guard-compare.txt). Snapshot (first laptop act, 09:21:32Z): `GUARD GREEN: snapshot; protected state observed; pythonProcesses=0`, rail exit 0 (evidence/L00-guard-snapshot.txt).

# sdrc C2 - bar 5, rollback ready on the laptop

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed. CANDIDATE 2e4292a75f08674fdf5c78358485b27c2d3bd913 (from docs/sdrc-c1/REPORT.md line 1); entry HEAD 853a272 (C1's report commit). Mac scratch /tmp/sdrc-c2/. Laptop work dir `C:\Users\Ben\AppData\Local\Temp\sdwin\sdrc-c2\`. Every laptop act went through `scripts/showready/win_rail.sh`; ssh answered every call. The v0.4.9 installer was downloaded and verified and NEVER run. Nothing was installed, stopped or started on the laptop apart from one curl.exe (pid recorded, exited 0, gone). No tag, release, merge or main push. No product code, test or script committed.

ROLLBACK = `C:\Users\Ben\Documents\steamdeck-midi-showready\rollback-v0.4.9\` (created by this link; it did not exist at 09:21:59Z, L01).

## Result in plain words

| Step | Result |
| --- | --- |
| 1 v0.4.9 installer | GREEN: GitHub API re-read (HTTP 200), laptop `curl.exe` ONE attempt, exit 0 in 5.2 s, 43881072 bytes, sha256 equal to the GitHub digest. Not run |
| 2 Program byte copy | GREEN: 44 files, 46535321 bytes; before-read = after-read = copy for all 44; 0 locked files; 0 copy errors |
| 3 Config byte copy | GREEN: 38 files, 99046 bytes; before = after = copy for all 38; byte-identical to `installed-program\config\` (38/38); logs 4 files, 3777200 bytes (< 50 MB) copied, 4/4 equal |
| 4 ROLLBACK-STEPS.txt | Written, plain ASCII (non-ASCII grep count 0), sha256 4d57354a...d83 equal on Mac, laptop and the fetched copy. Inline below |
| 5 Dry verification | GREEN: fresh re-read of every manifest (44/44, 38/38, 4/4 ok, 0 extra, 0 missing); ROLLBACK under `C:\Users\Ben\Documents\`, not Temp, not OneDrive, no reparse point on any of the three levels; Mac recompute of the fetched manifests agrees |
| 6 Leftovers | curl pid 354368 alive=False; python total 0; lane-path processes 0; processes running from ROLLBACK 0; browsers 0 in any session; guard compare GREEN |

## 1. The v0.4.9 installer asset

`curl -sS https://api.github.com/repos/ViddySlap/steam-deck-midi/releases/tags/v0.4.9` from the Mac, unauthenticated: HTTP 200 (evidence/api-v0.4.9.json). Release name `v0.4.9: dual control surfaces (OSC relay), gyro indicator fix, autopilot fallback clock + column advance`, published 2026-08-15T21:41:30Z, target_commitish `main`. One asset:

| Field | Value |
| --- | --- |
| Asset name | STEAMDECK-MIDI-RECEIVER-2-Setup-0.4.9.exe |
| GitHub size | 43881072 |
| GitHub digest | sha256:05a46159b762f33a757218817830666beaa07a629d121a89b75debaa6de351a5 |
| browser_download_url | https://github.com/ViddySlap/steam-deck-midi/releases/download/v0.4.9/STEAMDECK-MIDI-RECEIVER-2-Setup-0.4.9.exe |
| Laptop command | `C:\Windows\system32\curl.exe -L --fail --max-time 120 -sS -o C:\Users\Ben\Documents\steamdeck-midi-showready\rollback-v0.4.9\installer\STEAMDECK-MIDI-RECEIVER-2-Setup-0.4.9.exe <browser_download_url>` via Start-Process -PassThru, pid 354368, started 09:22:26.08Z |
| curl exit / elapsed / stderr | 0 / 5.2 s / empty; pid alive after: False |
| Laptop size (Get-Item) | 43881072, equal True |
| Laptop sha256 (Get-FileHash) | 05a46159b762f33a757218817830666beaa07a629d121a89b75debaa6de351a5, equal True |
| Re-read in step 5 (.NET SHA256) | same length and sha256, equal True |

The Mac fallback route was not needed (the one laptop attempt succeeded). Manifest: MANIFEST-installer.sha256.tsv.

## 2 and 3. Program, config and logs copies

Method (evidence/L03-copy.txt): for each tree, (a) BEFORE: every file under the source (`Get-ChildItem -Recurse -Force -File`) opened with `[IO.File]::Open(path, Open, Read, ReadWrite|Delete)`, read to memory, SHA256 + length; (b) directories created under the destination, then `Copy-Item -LiteralPath <source file> -Destination <copy file> -Force` PER FILE, so a locked file is named individually (the destination did not exist; `-Force` only lets the copy of a hidden file land, it never writes the source; no robocopy); (c) AFTER: the source read again the same way; (d) COPY: the copy read the same way. Each manifest row carries all three reads. The config inside the program copy was then compared with the separate config copy.

| Tree | Source | Copy | Files before / after / copy | EQUAL | Bytes | Locked or unreadable | Copy errors | Manifest |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| installed program | `C:\Program Files\STEAMDECK MIDI Receiver 2` | `ROLLBACK\installed-program` | 44 / 44 / 44 | 44 | 46535321 | 0 | 0 | MANIFEST-installed-program.sha256.tsv |
| user config | `C:\Program Files\STEAMDECK MIDI Receiver 2\config` | `ROLLBACK\config` | 38 / 38 / 38 | 38 | 99046 | 0 | 0 | MANIFEST-config.sha256.tsv |
| LOCALAPPDATA (logs) | `C:\Users\Ben\AppData\Local\STEAMDECK MIDI Receiver 2` | `ROLLBACK\localappdata` | 4 / 4 / 4 | 4 | 3777200 | 0 | 0 | MANIFEST-localappdata.sha256.tsv |
| config cross-check | `ROLLBACK\installed-program\config` vs `ROLLBACK\config` | - | 38 vs 38 | 38 | - | - | - | mismatches 0 |

- Timestamps (the config as of now): program before-read 09:23:20.39Z, copy done 09:23:20.91Z; config before-read 09:23:22.25Z, copy done 09:23:22.29Z; logs 09:23:22.36Z to 09:23:22.38Z. The steps tell Ben this is his config as of 2026-09-16 09:23 UTC and to take a fresh copy if he edits before Friday.
- The running tray did not lock anything: both onefile exes (the tray runs STEAMDECK-MIDI-RECEIVER-2-Tray.exe as pids 5268 and 23640) read with share ReadWrite. The live log `logs\bridge.log` did not change during the 22 ms window (before = after), so the live-append prefix rule the script carried was never needed (LIVE_APPEND_PREFIX_OK 0).
- Program top level in the manifest: STEAMDECK-MIDI-RECEIVER-2.exe, STEAMDECK-MIDI-RECEIVER-2-Tray.exe, receiver.ico, unins000.dat, unins000.exe, config\, scripts\.
- Independent Mac recompute from the fetched manifests (python, every row: length and sha256 before = after = copy): installed-program 44 rows True, config 38 rows True, localappdata 4 rows True, program-copy config == config copy True. The config sha256s agree with the sdwin gate's independent record: presets\EDM Show.json 90b2d19e, presets\PTZ.json 450f2edf, windows_midi_map.json f55c0509, presets\.active cc768739.
- The manifests carry relative paths, lengths and hashes only. `grep -c "OneDrive\|Resolume Arena"` over every committed .tsv and ROLLBACK-STEPS.txt: 0 in each. The osc_preset_path value was never printed (step 5 prints only its shape).

## 5. Dry verification (evidence/L04-verify.txt)

| Check | Result |
| --- | --- |
| ROLLBACK-STEPS.txt copied into ROLLBACK | sha256 4d57354adf99a3dc0c377d1c73c0668035da022b32192e5389f73a369d046d83 = the Mac file; the fetched docs/sdrc-c2/ROLLBACK-STEPS.txt hashes the same |
| Recursive listing | 107 entries, 92 files, 94321324 bytes (evidence/rollback-listing.tsv: 44 + 38 + 4 copies, the installer, 4 manifests, the steps) |
| Fresh re-read per manifest (length + sha256 vs the copy column, verdict EQUAL, no extra files) | installed-program 44 ok 0 bad 0 extra; config 38 ok 0 bad 0 extra; localappdata 4 ok 0 bad 0 extra |
| Installer re-read | 43881072, 05a46159...51a5, equal True |
| Location | `C:\Users\Ben\Documents\steamdeck-midi-showready\rollback-v0.4.9`; under_C_Users_Ben_Documents True, under_Temp False, under_OneDrive False; ReparsePoint False for `C:\Users\Ben\Documents`, the showready folder and ROLLBACK. (L01: Explorer's MyDocuments known folder is `C:\Users\Ben\OneDrive\Documents`; `C:\Users\Ben\Documents` attributes `Directory` only. Same as the master's 17:08 reading) |
| Installed program unchanged | guard compare GREEN (file count, metadata digest incl. LastWriteTimeUtc, 38 config sha256s, tray + loopMIDI identities, UDP 45123 / TCP 7723 owners, orphan HEAD/status) |
| C: free | 612621750272 bytes before the copy (L01) |

## What the steps rely on, verified

### The OSC Sync override (step B of the steps, install-time, Ben's act)

- The installer copies `config\engines.factory\*.json` with `ignoreversion` (installer/windows/steamdeck-midi-receiver-2.iss:62) and `config\engines\` gets only `README.md` with `onlyifdoesntexist` (:61), so a file Ben puts in `config\engines\` survives an install.
- The merge is WHOLE STANZA PER TYPE, not per key, in both versions: user `engines\*.json` stanzas win and a factory stanza is merged only for a type absent from the user dir (windows/engines/registry.py:350-362 at CANDIDATE; e66ff44 registry.py:266-275). So a minimal user file replaces the whole factory stanza, and every key it leaves out takes the ENGINE CODE default.
- Code defaults, identical in both versions for every key the factory file carries (windows/engines/osc_sync.py:106-147 at CANDIDATE; e66ff44 osc_sync.py:94-136): inputs.channel 14, inputs.cc_sync 90, epsilon_float 0.001, inter_message_delay_ms 50, mask_with_master true, sync_indicator_path `/composition/video/effects/oscsync/effect/sync/sync`, rest.base_url `http://127.0.0.1:8080`, rest.timeout_seconds 1.5, osc.host 127.0.0.1, osc.port 7000; `enabled` defaults true (windows/engines/base.py:68) and `name` defaults to the type (registry.py load loop), which is why the minimal JSON keeps `name`.
- The laptop proof (L04, value never printed): the backed-up installed `engines.factory\osc_sync.json` keys are the candidate factory keys plus exactly `osc_preset_path`; every other key's value equals the candidate factory value (`other_keys_equal_to_candidate=True`); the path starts `C:/Users/`, ends `.xml`, has no backslash, no double quote, and is not the USERNAME placeholder. So pasting it between quotes as-is is valid JSON. The factory values above equal the code defaults, so `{name, type, enabled, osc_preset_path}` is equivalent to the full file on both versions. `config\engines\osc_sync.json` is ABSENT today (L01, L04).

### What a 0.5.0 install overwrites, against Ben's installed config today (L01, hashes only)

| Installed file (installer flag) | vs CANDIDATE clone file |
| --- | --- |
| windows_midi_map.json (ignoreversion, .iss:55) | byte-equal (f55c0509) |
| actions.yaml (ignoreversion, :63) | byte-equal (a1cc2809) |
| engines.factory\ autopilot_ptz, global_color, l_stick_layer, ptz_visca, stageflow_bridge (:62) | byte-equal |
| engines.factory\ audio_opacity, autopilot, bumper_blast, chaser_stack_dispatcher, flash_blast, gyro_feedback, nestdrop, steam_input_layer_tracker (:62) | equal after CRLF -> LF only |
| engines.factory\osc_sync.json (:62) | differs: the installed file has `osc_preset_path` (Ben's real path), the candidate has no such key (the OSC override above) |
| windows_receiver_settings.example.json (ignoreversion, :56) | differs: the candidate adds `"preset_section": "windows"` (git diff e66ff44 HEAD). An example file; the tray is started by the Run key / shortcuts with explicit args (.iss:49, 66-67, 70), not from it |
| windows_receiver_settings.local.json, presets\default.json, macro_library.json, engines\README.md (onlyifdoesntexist, :57, :59-61) | all present today, so not written |

So the only config CONTENT a 0.5.0 install changes on this laptop is the OSC Sync preset path and the example file. `git diff e66ff44 HEAD -- installer/` is empty (0 lines): the v0.4.9 and candidate installer scripts are identical, so both install the same file names.

### Version identification (step A)

`/api/version` exists at CANDIDATE (windows/ui_server.py:424) and the status bar shows `v<version>` (windows/static/index.html:653, 909-913). At e66ff44 `git grep api/version` finds nothing and the route table has no catch-all (e66ff44 ui_server.py route list 211-456), so v0.4.9 answers Flask's 404. The v0.4.9 tray menu item is `Open Web UI` / `Quit` (e66ff44 tray.py:379-382). UNVERIFIED-BY-EXECUTION on the laptop: this link did not request 127.0.0.1:7723 (the tray's port; no act against the protected process).

### What a rollback leaves behind, and why v0.4.9 does not care (read from the v0.4.9 loader)

| Left behind | Written by | v0.4.9 reads it? |
| --- | --- | --- |
| `config\engines\osc_sync.json` | Ben, step B | YES, as intended: v0.4.9 loads `<map dir>/engines/*.json` (e66ff44 win_recv.py:283, registry.py:480) and the stanza gives the same settings (defaults above). Harmless |
| `config\state\autopilot_channels.local.json` | 0.5.0 autopilot persistence: state dir = `config\state` (registry.py:365-366, autopilot_state.py:34) | NO: v0.4.9 has no state-dir code (`git grep "state_dir\|STATE_DIR" e66ff44 -- windows` outside tests: 0 hits; the only "state" hits are layer-publisher attributes in receiver.py:332-334), and its engine globs are non-recursive `*.json` in `engines\` and `engines.factory\` (e66ff44 registry.py:480, 512). Harmless |
| `config\bridge.local.json` | 0.5.0 only when the preset section is changed in the UI; on Windows startup does not create it (win_recv.py:48 is darwin-only; :58 save_if_missing runs only when the section changed) | NO: `git grep bridge.local e66ff44 -- windows`: 0 hits. Harmless |
| dot-prefixed `.tmp` files from an interrupted atomic write (`.preset-`, `.bridge-`, `.osc_relay-`) | 0.5.0 writers | NO: not `*.json`. Harmless |
| A NEW preset or engine file created through the 0.5.0 UI | ui_server.py `_write_preset`; engine_config_api.py writes into `registry.user_dir` (:111-131) | YES: v0.4.9 lists every `presets\*.json` (e66ff44 ui_server.py:161) and loads every `engines\*.json`; v0.4.9 has no `sections` support (e66ff44 config.py `"sections"`: 0 hits). NOT unconditionally harmless: the steps tell Ben to move extra engine files out and not select a 0.5.0-made preset. `presets\.active` is restored by the config copy |
| Program files | installer | nothing extra: identical .iss |

## ROLLBACK-STEPS.txt (inline, byte-identical to docs/sdrc-c2/ROLLBACK-STEPS.txt and the laptop copy, sha256 4d57354a...6d83)

```
STEAMDECK MIDI Receiver 2 - rollback steps (v0.5.0 back to v0.4.9)
Written 2026-09-16 by an agent (sdrc C2). For Ben at the laptop, no agent needed.

This folder: C:\Users\Ben\Documents\steamdeck-midi-showready\rollback-v0.4.9\
  installer\STEAMDECK-MIDI-RECEIVER-2-Setup-0.4.9.exe   the v0.4.9 installer from GitHub (43881072 bytes, sha256 05a46159b762f33a757218817830666beaa07a629d121a89b75debaa6de351a5)
  installed-program\   byte copy of C:\Program Files\STEAMDECK MIDI Receiver 2\ (44 files, includes config\)
  config\              byte copy of C:\Program Files\STEAMDECK MIDI Receiver 2\config\ (38 files)
  localappdata\        byte copy of C:\Users\Ben\AppData\Local\STEAMDECK MIDI Receiver 2\ (logs only)
  MANIFEST-*.sha256.tsv  path, size and sha256 of every file

IMPORTANT: the config backup is your config as of 2026-09-16 09:23 UTC (03:23 Mountain).
If you change presets, macros or settings before you install 0.5.0, this backup does NOT have
those changes. In that case copy C:\Program Files\STEAMDECK MIDI Receiver 2\config\ again to a new
folder here (for example config-2026-09-18\) right before installing, and use that folder
wherever these steps say ROLLBACK\config.

ROLLBACK below means C:\Users\Ben\Documents\steamdeck-midi-showready\rollback-v0.4.9
PROGRAM below means C:\Program Files\STEAMDECK MIDI Receiver 2

A. WHICH VERSION IS RUNNING
1. Open http://127.0.0.1:7723/ (tray icon menu: Open Web UI).
2. v0.5.0 shows "v0.5.0" in the status bar at the bottom right. v0.4.9 shows no version there.
3. To be sure, open http://127.0.0.1:7723/api/version
   v0.5.0 answers {"version":"0.5.0", ...}. v0.4.9 answers "404 Not Found" (it has no such page).

B. BEFORE THE 0.5.0 INSTALLER RUNS (one time, while still on v0.4.9)
The installer REPLACES PROGRAM\config\engines.factory\osc_sync.json. Today that file holds your
real Resolume OSC preset path in the key "osc_preset_path". The 0.5.0 file has no such key, so
OSC Sync would fall back to a default path. The installer never touches PROGRAM\config\engines\,
so put the path there first:
1. Open PROGRAM\config\engines.factory\osc_sync.json in Notepad. Copy the text inside the quotes
   after "osc_preset_path": (it starts with C:/Users/ and ends with .xml). Close without saving.
   (The same file is also in ROLLBACK\config\engines.factory\osc_sync.json.)
2. Create a new file PROGRAM\config\engines\osc_sync.json with exactly this, pasting the path
   between the quotes (keep the forward slashes):
   {
     "name": "OSC Sync",
     "type": "osc_sync",
     "enabled": true,
     "osc_preset_path": "PASTE THE PATH HERE"
   }
3. Save. (Every other OSC Sync setting in the factory file equals the program's built-in default in
   both v0.4.9 and v0.5.0, so this short file behaves the same as the full one. v0.4.9 also reads
   it, so it is safe to leave in place.)
Then installing 0.5.0 is your call: quit the tray from its menu and run
C:\Users\Ben\Documents\steamdeck-midi-showready\candidate-2e4292a\STEAMDECK-MIDI-RECEIVER-2-Setup-0.5.0.exe

C. ROLL BACK TO v0.4.9 (after a 0.5.0 install)
1. Right-click the STEAMDECK tray icon (notification area) and choose Quit. Wait until it is gone.
2. Run ROLLBACK\installer\STEAMDECK-MIDI-RECEIVER-2-Setup-0.4.9.exe (Windows asks for admin).
   Keep the same install folder. Untick "Launch" on the last page.
3. Copy everything in ROLLBACK\config\ over PROGRAM\config\ and choose "Replace the files".
   Why this is still needed: the installer overwrites windows_midi_map.json, actions.yaml,
   windows_receiver_settings.example.json and every engines.factory\*.json with its own copies
   (its engines.factory\osc_sync.json may not have your real path). It does NOT overwrite
   windows_receiver_settings.local.json, presets\default.json, macro_library.json or
   engines\README.md if they exist, and never touches your other presets, presets\.active,
   osc_relay.json or engines\*.json. But 0.5.0 may have changed those files while it ran
   (saved presets, macros, active preset, OSC relay, engine settings). The copy puts all 38 back.
4. Start the tray from the Start menu: STEAMDECK MIDI Receiver 2.
5. Check A: http://127.0.0.1:7723/api/version must say 404 Not Found.
6. In loopMIDI, DECK_IN is listed. Press a Deck button you know; the loopMIDI data counter
   moves and the matching control reacts in Resolume.

D. IF THE v0.4.9 INSTALLER MISBEHAVES (fallback)
1. Quit the tray from its menu (as in C1). Check Task Manager: no STEAMDECK-MIDI-RECEIVER-2 process.
2. Copy everything in ROLLBACK\installed-program\ over PROGRAM\ and choose "Replace the files"
   (Windows asks for admin). This restores the v0.4.9 exes, scripts, uninstaller and config\.
3. Start the tray from the Start menu, then do C5 and C6.

E. WHAT A ROLLBACK LEAVES BEHIND
- PROGRAM\config\engines\osc_sync.json (from B): v0.4.9 reads it and gets the same settings.
- PROGRAM\config\state\ (0.5.0 autopilot memory): v0.4.9 never reads it.
- PROGRAM\config\bridge.local.json (only if you changed the preset section in 0.5.0): v0.4.9
  never reads it.
- Leftover .tmp files starting with a dot in config\: never read.
- Anything NEW you created in 0.5.0 stays: a new preset in config\presets\ or a new engine file in
  config\engines\. v0.4.9 lists every preset and loads every engines\*.json. If you made any,
  compare PROGRAM\config\engines\ with ROLLBACK\config\engines\ and move any extra file (other than
  osc_sync.json) out to a folder here. Do not select a preset that was created in 0.5.0.
- The program files themselves: nothing extra. The installer script is byte-identical in v0.4.9
  and 0.5.0, so both write the same file names.
```

## Process, port and browser rows (L04 at 09:25:54Z, read-only, then the guard compare)

| Row | Value |
| --- | --- |
| Recorded pids (this link started exactly one process) | curl.exe 354368: alive False |
| python.exe / pythonw.exe, machine-wide | PYTHON_TOTAL 0 |
| Lane-path processes (exe or command line under `...\steam-deck-midi-rc\` or `...\Temp\sdwin\`, excluding the verify script's own powershell) | 0 |
| Processes running from ROLLBACK | 0 |
| PROCESS-CLASS ORDER | nothing was stopped by this link and nothing needed stopping: (i) PROTECTED tray 5268, tray 23640, loopMIDI 16020, none recorded; (ii) RECORDED alive 0; (iii) LANE_PATH_UNRECORDED 0 |
| Protected, untouched | tray 5268 (06:29:37.4311374Z) and 23640 (06:29:37.8390240Z), loopMIDI 16020 (06:29:31.9633505Z), all session 1, created 2026-08-16; identical in L01 and L04; guard compare GREEN on UDP 45123 / TCP 7723 owner 23640 |
| Browsers, Win32_Process chrome.exe / msedge.exe / firefox.exe with SessionId + CreationDate | BROWSER_COUNT 0 in L01 (09:21:59Z) and in L04 (09:25:54Z): none in any session, so no NEEDS-MASTER browser line |
| Orphan checkout | not read by this link except through the guard (`git --no-optional-locks`); guard compare GREEN on its HEAD and status |
| Clone | not touched (no bundle, no pull: C2 changes no code on the laptop). L01 read its config files for hashes only |

## Findings

- **F1 (for the evidence report and bar 4, QUALIFIED rollback identity).** Route C (the v0.4.9 installer) puts back the PUBLISHED v0.4.9 build, not byte-for-byte the build running today. The installed exes came from the orphan checkout d136787, which differs from tag e66ff44 in exactly three blobs by a username substitution (sdwin gate Step 4c: osc_sync.json factory path, osc_sync.py default path, stageflow_bridge.py comp_path default). Whether the GitHub asset's exes equal the installed exes is UNVERIFIED-BY-EXECUTION (running or extracting the installer is outside this link). Consequence after route C: the OSC Sync path comes from the restored config and the step B override, not from the code default, so it is covered; stageflow_bridge's `comp_path` code default would be the tag's, which the gate's source read says is never read after assignment (UNVERIFIED-BY-EXECUTION there). Route D (copy `installed-program\` back) restores the exact bytes running today (44/44 sha256 in the manifest). The steps offer D as the fallback; the evidence-report link may want to tell Ben that D is also the exact-bytes route.
- **F2 (note, not a defect).** The installer's `CloseApplicationsFilter=STEAMDECK-MIDI-RECEIVER-2.exe` (.iss:36) names only the console exe, not the running Tray exe, so the steps have Ben quit the tray from its menu before either installer runs.
- **F3 (my instrument, disclosed).** The first preflight run (L01) died at its hash-compare section because a helper named `H` collides with PowerShell's `h` alias for Get-History; everything before it was read-only listing. Renamed to Get-Sha and the whole read-only script rerun; evidence/L01-preflight.txt holds the rerun (exit 0), which repeats every line of the first. The .ps1 bodies this link ran are not committed (docs only), as in C1.

## For the next links

- CG / the evidence report: bar 5 is GREEN on the laptop as of 2026-09-16T09:23Z: ROLLBACK holds the verified v0.4.9 installer (43881072, sha256 05a46159...51a5 = GitHub digest), a 44-file byte copy of the installed program, a 38-file byte copy of Ben's config, the 4 log files, 4 manifests and ROLLBACK-STEPS.txt. Quote F1 with the sdwin gate's d136787-vs-e66ff44 result.
- For Ben through the master: step B (the OSC Sync override in `config\engines\osc_sync.json`) must happen BEFORE the 0.5.0 installer runs, or OSC Sync falls back to the 0.5.0 code default path. The config backup is dated; re-copy if he edits before Friday.
- `C:\Users\Ben\Documents\steamdeck-midi-showready\` now holds `candidate-2e4292a\` (C1) and `rollback-v0.4.9\` (C2). Nothing in either was run.
- UNVERIFIED-BY-EXECUTION here: the installers (never run, by rule); the steps' UI facts on the laptop (A1-A3 are source reads; no request to the tray's port 7723); the Explorer copy dialogs and admin prompts named in the steps (Windows behaviour, not executed). No Mac suite was run: this link changed no code.
- Laptop leftovers of this link: `sdwin\sdrc-c2\` holds the guard JSONs (before.json, after.json), the scripts, curl.out/err, owned-pids.txt, rollback-listing.tsv and the uploaded ROLLBACK-STEPS.txt. No processes.
