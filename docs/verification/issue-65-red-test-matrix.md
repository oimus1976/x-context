# Issue #65 — RED-first fake-only test matrix

Status: **22 fake-only tests implemented and Linux CI verified**; direct Windows and independent L2 remain pending. Depends on `docs/specs/0008-recovery-reconciliation.md` and the exact revision of the Issue #62 one-shot executor in Draft PR #63. Design freeze precedes RED.

## Test harness (no actual Google/DPAPI/owner files)

- Work only inside an isolated temporary fake filesystem and in-memory fake Google Transport. Use fake `State`, `Store`, `Journal`, API clock and completely invented identifiers. All real source data read by tests comes from allowlisted `baseline` fixtures already tracked in this repository.
- To build canonical positive evidence, call the **existing fake** `recovery.resume_first_create` once from `tests/test_shared_context_google_resume.py`'s `incident()` fixture and an in-memory journal. Confirm it produced 11 fake write attempts and an actual `COMPLETE` history, then feed the resulting 29 events, initial state bytes and fake six-document folder to the new reconciler. Do **not** use a real operator's JSONL or ID.
- Corrupt one dimension at a time; confirm failure before any backup or mutation. For tests that need a fake local claim, use a separately guarded temp path, instrument exclusive file-create and `pub.State.save` call counts.
- Independent hostile tripwires must fail if `auth.Store.load/save`, `auth.token_request`, DPAPI, socket/urllib network, X authentication, or any external Google request is invoked during **local-only** inspection. For approved-read fake paths, only injected read-only Transport GET is allowed; POST/create/replace/delete/share must fail.
- Assert nonsecret, bounded output and no exception chain leakage, even on malformed CLI args, malicious fake filenames, invalid fake provider responses and errors containing sentinel tokens/IDs.

## Test contracts, in execution order

| Proposed test | Expected RED behavior / target |
| --- | --- |
| `test_RCN01_valid_29_event_history_reconstructs_original_incident` | Parse one exactly complete fake sidecar and old two-pending-event C001 state; reconstruct event roles and six receipts without any mutation. |
| `test_RCN01_mutated_order_missing_extra_or_stopped_event_blocks` | Omit/reorder/duplicate/append any of 29 events, or add STOPPED after COMPLETE; every case BLOCKED. |
| `test_RCN01_bad_created_id_or_duplicate_manifest_blocks` | Fake create ID missing/duplicate/collides with folder/parent, untracked role, changed C001 ID, forged final manifest; BLOCKED. |
| `test_RCN01_digest_revision_and_state_mismatch_blocks` | Wrong BEGIN old state/fixture/revision, wrong before revision/body SHA or final receipt, wrong old raw or normalized bytes; BLOCKED. |
| `test_RCN02_exact_remote_six_docs_and_current_ok` | Six stable, private, exact-ID, same-parent Docs; correct canonical CURRENT/active IDs/links/hashes; read-only plan can be built. |
| `test_RCN02_visible_inventory_and_permissions_fail_closed` | Missing/extra/duplicate app-visible children, nonnative MIME, changed appProperties/owner/parent, shared or inaccessible file, incomplete page; BLOCKED. |
| `test_RCN02_remote_revision_body_current_or_concurrent_change_blocks` | Each revision/body mismatch, malformed CURRENT, URL/hash mislink, changed snapshot on second pass; BLOCKED. |
| `test_RCN03_plan_contains_exact_six_ids_and_clears_pending_only_together` | Deterministic v1 registry six roles + pending empty; same namespace/folder/owner; existing validator PASS. |
| `test_RCN03_old_registry_sidecar_or_remote_one_byte_change_invalidates_digest` | Any raw byte, sidecar event, revision, identity, CURRENT byte, baseline or code binding change invalidates approved plan. |
| `test_RCN04_unapproved_apply_has_zero_effects` | No approved one-shot W gate -> zero backup and registry mutations, even with perfect fake evidence. |
| `test_RCN04_backup_is_exclusive_byte_exact_and_registry_commit_once` | First fake W: approved plan exact; one `xb` backup with fsync/readback equals old bytes, then one full atomic state replacement and readback; original sidecar byte-identical. |
| `test_RCN04_preexisting_claim_or_changed_plan_stops_before_write` | Existing empty/corrupt/COMPLETE backup or changed state/sidecar/remote/plan prevents registry commit; never alternate backup path. |
| `test_RCN05_fault_injection_at_every_backup_and_commit_boundary` | Before/after exclusive claim, fsync, readback, before/after atomic replace and final readback: no false success, never repeated commit; registry either full old or full new. |
| `test_RCN05_reentry_after_uncertainty_never_retries` | Restart with any existing backup claim blocks even if old pending remains; manual inspection required. |
| `test_RCN06_original_pending_blocks_normal_backend_and_projection_works` | Unmodified `AppBackend` refuses old registry; projected fake state accepts a read-only preview, no automatic normal publish. |
| `test_RCN07_redaction_and_no_live_capabilities` | Secret/ID/remote exception redacted; local-only never reaches credential/HTTP APIs; faux read-only rejects POST; X untouched. |

## Red/Green evidence requirements

1. Commit the spec as a separate documentation checkpoint; review AC before RED.
2. Introduce a test module such as `tests/test_shared_context_google_reconcile.py`; first RED **must** demonstrate absent/new reconciliation APIs causing failure rather than bad test data. Preserve RED logs outside published credentials.
3. GREEN implementation should reuse `pub.validate_state`, `pub.State`, `auth.atomic_write`, `google_recovery.Journal`, `google_api.Transport`, and `drive._index/parse_index` rather than a duplicate publisher implementation. Concurrency/race semantics must remain explicit.
4. Fake suite, full Windows `python -m unittest discover -s tests -v`, policy/lint check, exact-head verification and independent L2. Record test count, SHA and precisely which boundaries were not covered.
5. Never load real `%LOCALAPPDATA%\x-context\google-drive\publication-v1.json`, real recovery sidecar, actual private IDs, saved Google credentials or operator backups in this stage. No real Google requests, no Ready/merge/cleanup.

These tests qualify code *only*. They do not grant the independent live owner Gates R/W or permission to use/clear the actual registry.

## Implementation / CI evidence — 2026-10-18

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
