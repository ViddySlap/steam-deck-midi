# sdview V3: edit in place parity

| List operation | Controller drill-in location | Executed check/assertion | HTTP equivalent |
| --- | --- | --- | --- |
| Set type | Mappings > row Edit > Mapping type; shared DEFAULTS on change | C: all type options and type-change defaults | PUT /api/mappings/<action_id>; POST /api/save |
| Edit note fields | Row form: channel, note, velocity, Apply fields | C: note form commits its own fields | PUT /api/mappings/<action_id>; POST /api/save |
| Edit cc fields | Row form: channel, CC, on/off values | C: cc form commits its fields | PUT /api/mappings/<action_id>; POST /api/save |
| Edit macro_cc fields | Row form: channel, CC, gesture, optional fade | C: macro_cc form commits its fields | PUT /api/mappings/<action_id>; POST /api/save |
| Edit relative_cc fields | Row form: channel, CC, step, repeat interval | C: relative_cc form commits its fields | PUT /api/mappings/<action_id>; POST /api/save |
| Edit staged_note_macro fields | Row form: note, velocity, modifier/trigger channels, refresh list, optional delay/hold | C: staged_note_macro form commits its fields | PUT /api/mappings/<action_id>; POST /api/save |
| Edit axis_to_cc fields | Existing shared axis form: channel, CC, input/output ranges, deadzone, curve | C: axis_to_cc form commits its fields | PUT /api/mappings/<action_id>; POST /api/save |
| Edit axis_split_cc fields | Existing shared split form: channel, positive/negative CC, input max, deadzone, curve | C: axis_split_cc form commits its fields | PUT /api/mappings/<action_id>; POST /api/save |
| Clear | Row Edit > Clear mapping; Advanced null or omitted ID | C: Clear commits null; Advanced explicit null/omitted ID clears | DELETE /api/mappings/<action_id>; POST /api/save |
| Apply library macro | Apply macro... on each row; incompatible options disabled | C: inline merge matches actual List wrapper for each library type; M: persisted parity | GET /api/macros; POST /api/macros/<macro_id>/apply |
| Raw JSON Apply | Card > Advanced > object keyed by all owned Action IDs | C: bad syntax/shape/foreign ID commits nothing; valid mapping commits | GET /api/controller-map/<control_id>; POST /api/save (whole section); PUT/DELETE /api/mappings/<action_id> |
| Copy JSON | Advanced > Copy, including current unapplied text | C: clipboard receives current text | GET /api/controller-map/<control_id> provides saved grouped mappings; clipboard/drafts are local |
| Save and conflict guard | Existing global Save; modal cancel/force; affected open-control rows marked | C: conflict blocks save, cancel writes nothing, force writes exact section JSON, markers clear | POST /api/conflicts; POST /api/save |
| Section switch confirm | Existing section selector, visible in Controller view | C: refuses switch with unapplied row, accepted switch replaces draft; S: original guard | GET /api/mappings?section=name |
| Draft preservation on reload | Inline forms and Advanced; existing notice and Reload | C: no mappings request while typed row is pending, sibling commit/Save and control navigation preserve it, in-flight load rejects; R: original reload behavior | GET /api/state-version; GET /api/mappings; POST /api/reload |
| Factory reset | Existing global Reset button and confirmation, available in Controller view | C: reset request and fresh state/Advanced JSON | POST /api/reset |
| Return to List | Global List button or row Open in list | C: one-click List shows committed Controller edit; original handoff assertions retained | GET /api/mappings; GET /api/controller-map/<control_id> |

No mapping operation is missing. C, M, R and S are the exact commands in the
checks table below, not real-browser observations. API writes persist; browser
Apply operations update the local draft, then use the existing Save path.
Navigation, draft typing and clipboard do not create server state. docs/api.md
lists their existing read/write equivalents. No HTTP route was added or removed.

V3 base: 558793c17b01f5203fe0c2defb63b1895d280d2b (`git rev-parse HEAD` at entry).
V1/V2 reports and launch records were read. Branch: chain/steamdeck-20260914.
Mac build link only; no laptop acts. No changes to receiver MIDI dispatch,
windows/midi.py, parser rules, owned control map, artwork, pinned show-ready
instruments, mac/, or user presets. No live-input behavior was built.

## Shared forms and List compatibility

renderFields(type, spec, container, prefix, applyRow) defaults to the original
List containers and empty prefix. readFields(type, container, prefix) defaults
to the original document field lookup. All existing public functions remain.
The seven field definitions and spec readers, including both axis types, have
one implementation. Labels/IDs (including staged refresh actions) receive a
controller_<Action ID>_ prefix. Shared form labels now use ASCII punctuation.
The existing List call sites keep their original argument lists and behavior.

macroCompatible takes an optional action argument defaulting to selected.
applyMacroToAction contains the unchanged target-preserving merge and commit;
applyMacroToSelected remains the List wrapper with its original navigation,
render and toast behavior. Row selectors call that same merge without leaving
Controller view. Committing the List-selected action from Controller refreshes
the List form, so its one-click entry shows the current committed fields.

Cached inline editor nodes survive card navigation and sibling commits. A commit
replaces only its own action editor, preserving its expanded state. Advanced
keeps typed text until Apply or an accepted load. Both kinds of draft set
formDirty/editRevision; hasUnsavedEdits also checks cached drafts, since a sibling
commit clears the List's global formDirty flag. Accepted loadAll clears caches
only after its existing revision/preserveEdits guards have accepted the response.

Advanced validates the whole parsed object before calling commit per owned ID,
the same state path List applyJson uses. Syntax, top-level shape, foreign keys,
and non-mapping values/unsupported types refuse atomically. A detached render
of every supplied mapping catches malformed field shapes before any commit
(for example, refresh_actions supplied as a string). Full parser rules
still validate on Save, as in List; they were not changed. Numeric form range
errors appear inline and leave state unchanged. Clear/shared fallback semantics
are unchanged from V1. Global Reset and Reload remain the existing handlers.

## Checks and revert proofs

All config-writing checks use temporary copies via TMPDIR=/tmp/sdview-v3.
The fake DOM models input/change bubbling, select defaults, node reparenting,
clipboard and HTTP responses. It executes the shipped page/controller code;
it does not replace rendering, commit, macro, reload or save functions.
No existing test assertion was removed or changed. ui_reload_check.cjs and
ui_sections_check.cjs are unchanged; controller check additions are new assertions.

| ID | Command | Result |
| --- | --- | --- |
| C | TMPDIR=/tmp/sdview-v3 /opt/homebrew/bin/node tests/ui_controller_check.cjs | Exit 0; all existing behavior assertions plus all seven field forms, independent rows, range error, clear, library parity/refusal, Advanced atomic refusal/apply/copy, conflict guard, drafts, section/reset, one-click List, in-flight revision, unique IDs and ASCII |
| M | TMPDIR=/tmp/sdview-v3 /opt/homebrew/bin/node tests/ui_controller_macro_check.cjs | Exit 0; 48 real scratch disk writes match page Save, 72 incompatible writes refuse without byte changes |
| R | TMPDIR=/tmp/sdview-v3 /opt/homebrew/bin/node tests/ui_reload_check.cjs | Exit 0; timer, clean editor/engines, dirty notice, explicit reload, in-flight edits, retry |
| S | TMPDIR=/tmp/sdview-v3 /opt/homebrew/bin/node tests/ui_sections_check.cjs | Exit 0; selection, dirty guard, engine refresh, remote save, shared inheritance, CRUD |
| Mutations | TMPDIR=/tmp/sdview-v3 .venv/bin/python docs/sdview-v3/check_mutations.py /tmp/sdview-v3/mutations | Exit 0; pristine GREEN, seven planted faults RED (exit 1), seven restored GREEN (exit 0) |
| Whitespace | git diff --check | Exit 0 |

| Source mutation in scratch | Named assertion that goes RED |
| --- | --- |
| Apply uses DEFAULTS instead of readFields | note form commits its own fields |
| Remove draft dirty/revision tracking | typed inline field participates in draft listener |
| Remove foreign Action ID refusal | bad Advanced input commits nothing |
| Remove detached form preflight | Advanced shape errors are inline before any commit |
| Remove conflict row class | open control conflicting row marked |
| Remove inline macro application | inline macro merge matches List |
| Clear all editor caches on refresh | sibling commit preserves typed fields |

Reproducible runner: docs/sdview-v3/check_mutations.py. Exact per-run commands,
exit codes, named assertions and logs: mutation-results.json. The first scratch
proof for cache removal raised TypeError on the missing field. The new sibling
assertion now safely reads an absent node and emits its named AssertionError;
the full matrix was rerun. No product source was mutated by these proofs. A new malformed refresh_actions
check first reproduced a partial-commit TypeError (exit 1,
/tmp/sdview-v3/nested-shape-red.log). Detached shared-form preflight fixes it;
removing that preflight now fails the named inline-error assertion.

## Full Mac suite

Ran 865 tests in 12.635s; OK (skipped=2); exit 0.
Command: `TMPDIR=/tmp/sdview-v3 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
Log: /tmp/sdview-v3/mac-suite.log. Existing skips are the anticipated global-color
channel-CC remap and PowerShell guard execution without powershell/pwsh.

## EDM Show MIDI instrument

Executed at HEAD bb619c6f223f9e85a3022f3acf78e54dae0692b4 (both archived
candidate arm commits match). The final evidence commit changes only docs.
The pinned README commands were used with scratch/output paths relocated:

```sh
.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdview-v3/deck-script.json
TMPDIR=/tmp/sdview-v3 .venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdview-v3/deck-script.json --scratch /tmp/sdview-v3/ab-final --out /tmp/sdview-v3/mac-edm-final.json
```

Generator exit 0: script_sha256
9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e;
732 steps, 47039 packets, scripted duration 469.716666743 seconds.
Final replay exit 0, verbatim verdict:

```json
{"comparisons": {"B1": {"different_mappings": [], "totals": {"mappings": 56, "mappings_exercised": 56, "messages_A": 1531, "messages_B": 1531, "steps": 732}, "unexercised_mappings": []}, "B2": {"different_mappings": [], "totals": {"mappings": 56, "mappings_exercised": 56, "messages_A": 1531, "messages_B": 1531, "steps": 732}, "unexercised_mappings": []}}, "error": null, "passed": true, "result": "/tmp/sdview-v3/mac-edm-final.json.gz"}
```

Both B1 (flat) and B2 (sectioned windows) equal A (v0.4.9). Every mapping was
exercised, with no different or unexercised mapping. The same result records
real-rate pacing, exact capture bytes/hashes, coverage, free non-default ports,
no-UI/stub-MIDI argv, quiescence and process cleanup. It is synthetic Deck input
and a controlled receiver clock with real loopback UDP, not hardware/Windows
show readiness. The pinned instrument and MIDI code remain unchanged.

Primary machine-readable evidence: docs/sdview-v3/midi-verdict.json.
Raw capture: /tmp/sdview-v3/mac-edm-final.json.gz, SHA256
a80ad7c8512c7c238f8fd7edcb4a182d1c43f5d9964f952bf071cdc822759bdb.

`.venv/bin/python /tmp/sdview-v3/finish_evidence.py` exited 0, extracted that
artifact, asserted both candidate identities and all comparisons passed, and
independently repeated os.kill(pid, 0) for every recorded arm after the driver's
Popen.wait/kill(pid,0) cleanup. Every PID raised ProcessLookupError. The script
is also committed as docs/sdview-v3/finish_evidence.py. Its earlier_replay entry
retains the same checks for the initial implementation 9d459fc: that preliminary
run also passed and all its processes are gone. Its command used --scratch
/tmp/sdview-v3/ab and --out /tmp/sdview-v3/mac-edm.json with the same other args.
The final-HEAD run above is the primary V3 result.


## OWED TO THE GATE

Real-browser behavior is UNVERIFIED-BY-EXECUTION in V3. At the gate, check the
picture/card layout with expanded forms, field labels and errors, independent
row values, native typing/tabbing/selects, tabs, clipboard, macro options,
conflict marks/modal cancel/force, section confirmation and hot-reload notice
without input/focus loss. Repeat both axis forms in the real browser. Node VM
assertions prove DOM/handler state and requests, not native browser interaction.

The full Windows suite and Windows MIDI comparisons for EDM Show and PTZ remain
OWED TO THE GATE/JUDGE, exactly as scripts/showready/README.md defines. No laptop
or installed tray was touched. No release/deployment or show-ready claim is made.
