# Issue #65 — RED-first fake-only test matrix

Status: **35 synthetic-only methods after F1/F3/F7 remediation and material F6 coverage**. New committed-head Windows/CI evidence belongs to the exact SHA reported on Draft PR #66; independent Claude Code L2 remains required. Depends on `docs/specs/0008-recovery-reconciliation.md` and the exact revision of the Issue #62 one-shot executor in Draft PR #63. Design freeze precedes RED.

## Test harness (no actual Google/DPAPI/owner files)

- Work only inside an isolated temporary fake filesystem and in-memory fake Google Transport. Use fake `State`, `Store`, `Journal`, API clock and completely invented identifiers. All real source data read by tests comes from allowlisted `baseline` fixtures already tracked in this repository.
- To build canonical positive evidence, call the **existing fake** `recovery.resume_first_create` once from `tests/test_shared_context_google_resume.py`'s `incident()` fixture and an in-memory journal. Confirm it produced 11 fake write attempts and an actual `COMPLETE` history, then feed the resulting 29 events, initial state bytes and fake six-document folder to the new reconciler. Do **not** use a real operator's JSONL or ID.
- Corrupt one dimension at a time; confirm failure before any backup or mutation. For tests that need a fake local claim, use a separately guarded temp path, instrument exclusive file-create and `pub.State.save` call counts.
- Independent hostile tripwires must fail if `auth.Store.load/save`, `auth.token_request`, DPAPI, socket/urllib network, X authentication, or any external Google request is invoked during **local-only** inspection. For approved-read fake paths, only injected read-only Transport GET is allowed; POST/create/replace/delete/share must fail.
- Assert nonsecret bounded ordinary API errors on malicious fake filenames, invalid fake provider responses and sentinel exceptions. There is no reconciliation CLI; its future caller's argument/termination reporting is outside this module's tested boundary.

## Actual executable test methods (2026-10-20)

All methods are in `tests/test_shared_context_google_reconcile.py`. Existing
RCN method names describe their bounded checks; F-method rows state the new
adversarial coverage explicitly. Broad requirement labels do not imply exhaustive
fault or interleaving coverage.

| Executable method | Checked boundary |
| --- | --- |
| `test_RCN01_valid_29_event_history_reconstructs_original_incident` | RCN01 valid 29 event history reconstructs original incident |
| `test_RCN01_mutated_order_missing_extra_or_stopped_event_blocks` | RCN01 mutated order missing extra or stopped event blocks |
| `test_RCN01_wrong_created_id_receipt_or_original_state_blocks` | RCN01 wrong created id receipt or original state blocks |
| `test_RCN02_exact_remote_six_docs_and_current_ok` | RCN02 exact remote six docs and current ok |
| `test_RCN02_visible_inventory_permissions_body_and_revision_fail_closed` | RCN02 visible inventory permissions body and revision fail closed |
| `test_RCN03_deterministic_projection_and_raw_bytes_binding` | RCN03 deterministic projection and raw bytes binding |
| `test_RCN03_module_source_change_invalidates_approved_digest` | RCN03 module source change invalidates approved digest |
| `test_RCN04_missing_approval_does_not_create_backup_or_commit` | RCN04 missing approval does not create backup or commit |
| `test_RCN04_alternate_backup_name_cannot_evict_existing_claim` | RCN04 alternate backup name cannot evict existing claim |
| `test_RCN04_exclusive_exact_backup_and_single_atomic_commit` | RCN04 exclusive exact backup and single atomic commit |
| `test_RCN04_wrong_explicit_backup_approval_path_blocks` | RCN04 wrong explicit backup approval path blocks |
| `test_RCN04_preexisting_claim_or_changed_plan_refuses_commit` | RCN04 preexisting claim or changed plan refuses commit |
| `test_RCN05_failure_after_claim_requires_inspection_without_retry` | RCN05 failure after claim requires inspection without retry |
| `test_RCN06_normal_backend_remains_blocked_until_complete_projection` | RCN06 normal backend remains blocked until complete projection |
| `test_RCN01_duplicate_manifest_and_wrong_c001_mapping_block` | RCN01 duplicate manifest and wrong c001 mapping block |
| `test_RCN02_extra_visible_child_and_concurrent_snapshot_block` | RCN02 extra visible child and concurrent snapshot block |
| `test_RCN03_remote_revision_change_invalidates_prior_approved_plan` | RCN03 remote revision change invalidates prior approved plan |
| `test_RCN05_after_commit_uncertainty_never_claims_old_state` | RCN05 after commit uncertainty never claims old state |
| `test_RCN05_changed_remote_snapshot_after_backup_never_commits` | RCN05 changed remote snapshot after backup never commits |
| `test_RCN05_backup_fsync_failure_preserves_old_registry_and_claim` | RCN05 backup fsync failure preserves old registry and claim |
| `test_RCN07_guard_rejects_unsafe_paths_without_creating_files` | RCN07 guard rejects unsafe paths without creating files |
| `test_RCN07_redacted_errors_and_no_authentication_or_network` | RCN07 redacted errors and no authentication or network |
| `test_F1_forged_journal_events_cannot_replace_captured_bytes` | Forged Journal.load returns valid events for unrelated bytes: reject plan/apply before GET, backup or save. |
| `test_F1_canonical_bytes_do_not_consult_overridable_load` | Canonical inspection and plan succeed while Journal.load is a forbidden tripwire. |
| `test_F1_sidecar_change_after_capture_blocks_before_get` | Bounded sidecar read then file changes before equality check: reject before GET; no ABA-proof claim. |
| `test_F3_writer_output_is_accepted_byte_for_byte` | Positive bytes produced by the unchanged actual Journal file writer. |
| `test_F3_equivalent_noncanonical_encodings_block_before_get` | BOM, CR/CRLF, escaped key/value, whitespace, key order, separators, trailing data/blank line and missing LF. |
| `test_F1_F6_malformed_unknown_duplicate_and_oversize_sidecar_blocks` | Malformed JSON, extra/unknown event, duplicate key, NaN and oversize fail before GET. |
| `test_F7_claim_open_and_status_inspection_failure_returns_safe_status` | Failed xb plus hostile status probe: bounded UNCERTAIN, no second exists call or raw path error. |
| `test_F6_duplicate_created_id_colliding_with_c001_blocks_before_get` | Actual CREATED ID equals C001, not merely a changed manifest: zero GET/effects. |
| `test_F6_folder_and_document_metadata_mismatch_blocks_without_backup` | Both folder and C001: appProperties, owner, parent, MIME and isAppAuthorized; BLOCKED before backup. |
| `test_F6_missing_child_and_current_link_tampering_block` | Missing inventory child and canonical CURRENT link mismatch; no backup/registry mutation. |
| `test_F6_local_and_read_paths_have_true_no_auth_network_or_write_tripwires` | Counted fail tripwires for credential load/save, refresh, DPAPI, sockets, urllib, HTTP, X and publisher; local has zero GET; positive fake plan/apply use GET only. |
| `test_F6_backup_open_fsync_readback_replace_and_postread_failures_stop` | Nine targeted boundaries: possible claim, write, flush, backup fsync/readback, state fsync, replace before/after and post-replace readback. Exact BLOCKED reentry, byte preservation, no later effects. |
| `test_F6_keyboard_interrupt_retains_claim_and_exact_reentry_block` | KeyboardInterrupt propagates after claim; fixed claim blocks reentry before GET with bytes preserved. |

### Deliberately untested / future caller boundaries

- No real account/provider/token/store/registry qualification, revision lifetime, provider latency or quota measurement.
- No OS user authentication/lock implementation, arbitrary concurrent ABA exclusion, complete dependency/caller-source verification or authority validation from booleans.
- Targeted local fault injection is not exhaustive instruction-level crash coverage, process-kill/power-loss durability proof, directory-fsync proof, or a multi-resource transaction. KeyboardInterrupt after claim is tested; abrupt process death and OS claim loss are not.
- No reconciliation CLI exists, so no claim of CLI argument redaction. Safe ordinary API error statuses are tested; future caller termination/reporting is separately reviewed.

## Remediation RED / GREEN evidence (2026-10-20)

- Unchanged starting implementation `aab87149a0e926c11e49c2c2471e0b1cbbfa5408` plus new tests: **34 methods, failures=8 (including subtests), errors=2, 3.962s**. F1 forged loader succeeded unexpectedly; F3 seven noncanonical subcases were accepted; F7 raised the sentinel PermissionError. Overridable-load tripwire also failed as intended.
- First minimal GREEN: **34/34 PASS, 3.584s**. Then added bounded capture-drift and strengthened exact success reentry checks: final focused module has **35 methods**. Final Windows full-suite and committed-head evidence is recorded in PR #66 with its exact SHA.
- Pre-commit full Windows regression: **437 PASS in 149.688s**, failure/error/skip=0, all 35 reconciliation methods included. Baseline/policy compilation/diff checks PASS. This is separate from the subsequent committed-head result.
- Initial sandbox temp-directory PermissionError was an environment failure, not the RED proof. Logs remain private local evidence; no full log/private path upload.
- New-head independent L2 remains assigned to Claude Code. Fake results do not authorize Gates R/W or Ready/merge.

## Red/Green evidence requirements

1. Commit the spec as a separate documentation checkpoint; review AC before RED.
2. Introduce a test module such as `tests/test_shared_context_google_reconcile.py`; first RED **must** demonstrate absent/new reconciliation APIs causing failure rather than bad test data. Preserve RED logs outside published credentials.
3. GREEN reuses state validation/atomic writer, injected Transport, core JSON codec and CURRENT construction. Journal is the unchanged format authority; its overridable load is deliberately not the reconciler semantic evidence source. Concurrency/race semantics must remain explicit.
4. Fake suite, full Windows `python -m unittest discover -s tests -v`, policy/lint check, exact-head verification and independent L2. Record test count, SHA and precisely which boundaries were not covered.
5. Never load real `%LOCALAPPDATA%\x-context\google-drive\publication-v1.json`, real recovery sidecar, actual private IDs, saved Google credentials or operator backups in this stage. No real Google requests, no Ready/merge/cleanup.

These tests qualify code *only*. They do not grant the independent live owner Gates R/W or permission to use/clear the actual registry.

## Historical implementation / CI evidence — 2026-10-18

- RED checkpoint `84c4b5a6d8fe414c0e44f91a71ad25bfc5dd0d60`:
  [project-ci failure](https://github.com/oimus1976/x-context/actions/runs/39130312351)
  was the intended missing-contract failure: `ImportError: cannot import name
  'google_reconcile'`. 403 total discovered tests, one import error, one skip.
- Initial GREEN `23474bc9e5f2aa9737cf038e15da27046f63e750`:
  [project-ci passed](https://github.com/oimus1976/x-context/actions/runs/39130474953).
- Broader tests found one *incorrect test assumption*: an appended whitespace
  byte changes original raw state but not the BEGIN canonical-state hash.
  It is valid for local inspection, and instead must invalidate an already
  approved plan. The test was corrected, not removed. Checkpoint
  `38efeff85204bc447f9e3d9c957def2241a03c2e` passed project-ci.
- Expanded fake suite at `f61d0904a1c828a252466f53cc6207cded853e08`:
  [project-ci passed](https://github.com/oimus1976/x-context/actions/runs/39130943391),
  **423 tests, 0 failures/errors, 1 pre-existing skip**. The new file
  `tests/test_shared_context_google_reconcile.py` contains 22 test methods
  spanning RCN-01..07. Policy check, status docs and final branch HEAD need
  separate exact-head confirmation.
- Gates exercised by fake test only: exact 29-event history, six-role positive
  manifest, malformed history, tampered permissions/body/revisions, extra
  APP_VISIBLE child, snapshot races, changed raw bytes and module source,
  pending-only rejection, exact backup authorization, exclusive claim,
  backup fsync, ambiguous after-commit response and failure after claim,
  redacted errors and unsafe path guards.
- No Windows PowerShell exact-head run, independent Codex/L2 review, actual
  Google client/API usage, owner registry/sidecar/DPAPI reads or writes, live
  Gate R/W authorization, normal publish invocation, Ready or merge.
  Existing fake read GET counts are NOT real provider quota evidence.

A logical-state-only BEGIN digest cannot reconstruct original unrecorded raw
JSON bytes. The reconciliation captures their current raw hash and binds it to
the later owner-approved plan; it never asserts that the BEGIN recorded them.

- Additional one-shot claim regression: do not permit a fresh backup filename to bypass an existing original-registry claim. Use only the registry-derived `*.issue65-original-claim.json` path, still requiring exact Gate W path approval.
- Source/test fix at `1febd91bf5a2555bf506fe0490a2904cb3462a4b`: [project-ci](https://github.com/oimus1976/x-context/actions/runs/39131205840) SUCCESS, **424 tests, 0 failures/errors, 1 pre-existing skip**; [policy-check](https://github.com/oimus1976/x-context/actions/runs/39131205803) SUCCESS. Direct Windows/L2/live gates remain pending.
