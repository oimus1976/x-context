# SPEC-0008 — One-time reconciliation after completed first-create recovery (Issue #65)

Status: **DESIGN / TEST CONTRACT ONLY**. No local owner files or live Drive were accessed while authoring this spec. No registry write, OAuth refresh, recovery re-run, scheduled job, Ready, or merge is authorized by this document.

Base dependency: Draft PR #63 exact source head `f098de73eec2dd75ddfa315a2067835121622387` (2026-10-18). This document lives on a **separate** Issue #65 topic branch, based on that head. The resulting PR should target the #63 topic branch until #63 is merged, then be deliberately rebased/retargeted to actual main. No implementation belongs on #63.

Related authorities: [Issue #62](https://github.com/oimus1976/x-context/issues/62), [Issue #65](https://github.com/oimus1976/x-context/issues/65), `0008-first-create-recovery.md`, `0008-unattended-drive-publisher.md`, ADR-0006, and `google_publish.py`, `google_recovery.py`.

## 1. Current proven boundary

- Owner-approved A: read-only plan PASS; 24 GET attempts (20 Drive + 4 Docs), zero POST.
- Owner-approved B: `resume_first_create` returned COMPLETE on the local Windows host, 1,265 HTTP attempts, 11 POST attempts (5 Drive create, 6 Docs text updates), original registry byte-unchanged and one exclusive recovery sidecar created.
- An independent read-only Drive connector observation found six private native Docs in the original app-created dedicated folder: `SYN-XCTX-C001`, `SYN-XCTX-C002`, `SYN-XCTX-P001`, `SYN-XCTX-P002`, `SYN-XCTX-P003`, and CURRENT. Original C001 preserved its previous Drive ID and now has text. CURRENT was parsed: publication schema 1, status COMPLETE, five active IDs and links to the five corresponding Docs.
- **Not yet proven:** private local sidecar bytes/COMPLETE durability and reconciliation eligibility in the actual Windows store; any ordinary publish after recovery. Prior evidence does not grant reconciliation authority.
- Old v1 `publication-v1.json` still has only the original C001 in `documents`, with exactly `('', 'CREATE_ATTEMPT')`, `(C001_ID, 'CREATED_EMPTY_UNVERIFIED')` in `pending`. Normal `AppBackend` must continue to refuse this unchanged state.

Real X data, bookmarks, tokens, personal/municipal information, wider Google scopes, existing Issue #60 PoC materials, unattended task installation and cleanup are out of scope.

## 2. Minimal desired result

A **single operator-approved atomic replacement of the existing v1 publication registry**, under original private Windows local Google-Drive application directory, with:
- `schema='1'`, `namespace`, `folder`, `parent`, `owner` exactly preserved;
- `documents` equal to **the six distinct, verified role-to-ID bindings from the immutable recovery sidecar COMPLETE manifest**, not search-by-title/adoption, not a fresh new folder;
- `pending=[]` only after exact sidecar history, actual Google objects, CURRENT canonical content and fixture state are verified;
- an exclusive, private, byte-exact original-registry backup made **before** replacement; the original completed recovery sidecar remains byte-for-byte untouched.

The existing registry schema stays v1. No other persistent state is changed. No Google effect occurs in the apply phase; external read verification before apply needs independent owner approval. The reconciler never invokes `publish --apply`, `resume_first_create`, `init-sandbox`, login or refresh implicitly. It does not remove the completed recovery sidecar.

A useful, reviewable implementation is a small injected module (e.g. `google_reconcile.py`) with separate pure/local inspector, live-read planner and owner-gated one-time local commit. A standalone execution caller with private paths/credentials is a **later separately reviewed** scope, not part of this design approval.

## 3. Three explicit authority gates

**Gate S — fake-only development (authorized development scope).** Read existing repository source, specify invariants, write RED then GREEN fake/unit tests, exact-head validation and independent L2. Synthetic paths and invented IDs only. Never load real DPAPI credentials or actual `publication-v1.json` / sidecar, and never call actual Google.

**Gate R — later live read-only qualification (NOT AUTHORIZED by this spec).** An owner-approved caller/transport reads only one specified private application account/folder and six Docs; no OAuth refresh or save; a published strict per-service GET/time budget and exact code/fixture/target hashes; sidecar and registry **read only**. The local-inspection stage should fail on malformed evidence before fetching any credentials. Return a bound non-secret digest/report. Any mismatch blocks.

**Gate W — later owner-approved single local mutation (NOT AUTHORIZED by this spec).** After reviewing Gate R plan/hash, the owner separately authorizes an exact local registry backup path, exact target state and digest, same fixed sidecar and account, and single atomic replace. Re-read and revalidate everything before exclusive backup claim. Nothing remotely is modified. No implicit ordinary publish or retry on ambiguous outcome.

Do not combine R and W solely because a fake test passed or because old recovery returned COMPLETE. Human retains Ready/merge/destructive decision authority.

## 4. Exact local evidence and event-state machine — RCN-01

Inputs must be a **specific existing absolute registry path**, a **specific existing absolute recovery JSONL sidecar path** and compiled `baseline` records; no directory search or arbitrary import. Apply existing path guards; reject symlink, junction, malformed/oversized files, trailing junk, duplicate keys, invalid strings and unsafe Windows aliases. Compute both **raw byte SHA256** and canonical normalized-state digest before any possible effect; keep original bytes for backup. BEGIN records the *canonical state* digest, not the registry's original raw-byte digest. Whitespace-only differences may pass history inspection but must change the fresh plan digest and block any previously approved apply.

The sidecar is an append-only record stream. The existing `google_recovery.Journal.load` validates transport/storage framing, **not** the semantic completeness of an arbitrary event stream. The reconciler must validate meaning as well. For this unique successful baseline incident, expect exactly **29 ordered entries**:

1. `BEGIN` with `schema='first-create-recovery-v1'`, an exact copy of the original v1 registry state, original state digest, baseline fixture digest, the initial C001 revision and a bounded nonsecret approval reference.
2. Original C001: `INTENT(WRITE_TEXT)`, then final `VERIFIED` receipt.
3. Each other source record, in **compiled baseline iteration order** (four roles): `INTENT(CREATE)` -> `CREATED` with new unique ID -> `VERIFIED_EMPTY` receipt -> `INTENT(WRITE_TEXT)` -> final `VERIFIED` receipt.
4. CURRENT last: `INTENT(CREATE)` -> `CREATED` -> `VERIFIED_EMPTY` -> `INTENT(WRITE_TEXT)` -> final `VERIFIED` -> **one final `COMPLETE`** with state/fixture digests and a complete six-role manifest.

Validate exact field sets/types, event role/action, body digests per compiled Markdown/expected CURRENT, before/after revision relationships, CREATE intent's initially unknown ID, immediate matching returned ID, revision transition after text, uniqueness of six IDs, matching receipt chronology and final manifest. No missing, extra, reordered, duplicated, STOPPED, unknown, or trailing event may be accepted. Reject any sidecar that merely contains the word COMPLETE.

Bind `BEGIN.original_state` to actual decoded registry, `BEGIN.state_sha256` and `COMPLETE.state_sha256` to the original normalized-state digest, `BEGIN.fixture_sha256` and `COMPLETE.fixture_sha256` to compiled baseline, and `BEGIN.first_revision` to the original C001 empty revision. The original two `pending` markers and C001 ID must be exact; original `documents` must contain **only** the named C001 role. The final C001 ID must be exactly that same original ID. Do not use title-only lookup.

Never put original IDs, owner principal, namespace, full registry/sidecar bytes, raw token, account address or private paths in stdout, test snapshots, issue comments, CI artifacts or public GitHub docs. Digests for an actual account are operational bindings and should remain in private operator output, not public source files.

## 5. Actual six-document authority and CURRENT — RCN-02

A separately approved read-only Google Transport, with refresh/save disabled, must perform a fresh **stable whole-set** check:

- Exact app-authorized folder ID, owner-only privacy, original parent, native folder MIME, expected title and appProperties namespace/role.
- Complete **APP_VISIBLE** all-MIME inventory of precisely the six IDs from the sidecar, with no duplicate, missing or extra *visible* items; `drive.file` is not a global owner-inventory proof. Require same-account single-writer dedicated-folder assumption.
- For each role, exact document ID, title, `parents=(folder_id,)`, native Docs MIME, appProperties and owner-only permission, stable nonempty revision; exact text matches compiled baseline Markdown for five records; CURRENT body matches `drive._index(baseline_records, verified_docs)` byte-for-byte after provider text normalization.
- Parse CURRENT using the existing index parser; expect status COMPLETE, schema 1, exactly five `active_ids` / `active_links`, all link URLs and hashes bound to the **observed** five IDs/bodies; never trust CURRENT as an authority for adopting unknown IDs.
- Match all final remote revisions and body digests to the six final `VERIFIED`/COMPLETE manifest receipts. Exact revisions are part of the approved frozen plan; changed revision even if body unchanged requires new inspection/plan, never silent acceptance.
- Repeat remote snapshot and original local raw-byte comparisons before completing the read-only plan, and immediately before any later Gate W commit. Reject unstable snapshots, permission expansion, missing metadata, stale journal, pagination disagreement, or any mismatch.

No Google WRITE, scope expansion, token refresh, local registry mutation or backup in this phase.

## 6. Immutable planned projection — RCN-03

Compute the one target registry JSON from the exact original state and the validated six-role sidecar manifest. Preserve every existing v1 identity field and set only `documents` (full map), `pending=[]`. `pub.validate_state(projected)` must PASS and the existing `AppBackend` contract should be provably compatible in fake read-only tests.

Create a deterministic canonical plan digest bound to:
- original **raw registry bytes** SHA256 and logical state SHA256;
- entire **raw sidecar bytes** SHA256 and strict 29-event validation/COMPLETE manifest;
- six verified remote identities, owners/parents/permissions/appProperties, revisions, bodies and CURRENT text;
- compiled baseline SHA256, projected registry canonical bytes SHA256;
- exact reviewed code/caller version/sha, approved private location identities (without showing raw values).

Output statuses are nonsecret. The digest does **not** itself grant permission. Never persist a plan file into the protected live path automatically; any needed private receipt must be explicit and owner-approved.

## 7. Bounded one-time local commit — RCN-04, RCN-05

After a separately approved read plan and independent W authorization:

1. Enforce the expected exact-head/caller/code digest, same Windows user, private path guards and single writer; no source in progress, sidecar/backup/registry path aliases, and no existing claim/backup file. Re-inspect local sidecar + original registry raw bytes and fresh remote plan; require exact equality to the owner-approved plan including revisions and hashes. Do not refresh credentials.
2. **First persistent effect**: make a byte-exact original-registry backup at the sole owner-approved private path derived from the registry's stem: `<registry-stem>.issue65-original-claim.json`, in the same directory with exclusive create (`xb` or `O_EXCL`), flush/fsync, and readback. This backup is simultaneously the one-shot **claim**; any existing backup (even empty/corrupt) blocks all later write attempts. Never overwrite, delete, or use an alternate backup path to evade ambiguity. Keep recovery sidecar untouched.
3. Just before registry replacement recheck that original registry and sidecar raw bytes are still identical to the approved plan, and that the verified remote plan remains unchanged. Do not assume that exclusive backup locks the unrelated original registry; explicitly retain the single-writer assumption.
4. Commit the **complete** projected registry with existing safeguarded `pub.State.save` / `auth.atomic_write` and read back bytes; report COMPLETE only on exact byte equality plus unchanged sidecar/backup and appropriate durable-write evidence. Note that Windows rename + file fsync is not a cross-resource transaction or blanket power-loss guarantee; treat post-commit errors/unknown persistence as `UNCERTAIN_REQUIRES_INSPECTION`.
5. If any failure occurs after backup creation, never auto-repeat or auto-rollback. Operator must read-only compare old and projected registry bytes, immutable backup/sidecar and current remote state; return a safe category. If failure occurs before backup claim, no registry write was authorized/performed.

`pending=[]` is allowed **only** as part of the fully populated, verified six-document replacement. In particular, a simple `state['pending']=[]` operation on the original one-document registry is invalid.

Do not call normal `publish` automatically; user must separately authorize its **read-only dry-run** after successful reconciliation, then any subsequent no-op/edit/withdrawal/restore live test separately. The existing recovery sidecar is a historic audit artifact and must continue to block its special recovery executor; it does not grant new one-shot rights.

## 8. Failure model and operator-facing behavior

- Local proof failure before any effect -> `BLOCKED` with safe category and zero effects.
- Live read mismatch, incomplete APP_VISIBLE inventory, refresh-needed credential -> `BLOCKED` without mutation; no implicit refresh or retry.
- Backup claim/backup readback failure -> stop. If backup may already have been created, **any later attempt is forbidden** without new inspection and owner decision.
- Fail/crash between backup creation, registry atomic replacement, or readback -> `UNCERTAIN_REQUIRES_INSPECTION`. Do not label success based only on a remote CURRENT COMPLETE or local `pending=[]`.
- On proven final state only -> `RECONCILED` (normal publish still NOT_INVOKED). Before that, ordinary `AppBackend` must keep rejecting the incident's original pending.
- Every stop requires safe stdout/stderr without traceback containing private paths/IDs; redaction regression tests should include hostile exceptions, invalid CLI args and file names.
- No automatic retry, rollback, new Google objects, sharing changes, registry truncation, sidecar deletion, hidden credential update, cron/Task Scheduler, or X calls.

## 9. Requirement → AC → RED test contract (freeze before implementation)

| Requirement | Acceptance check / RED scenario |
| --- | --- |
| RCN-01 history | Synthetic exact 29-event successful stream accepted; each event omission/reorder/duplicate/unknown, STOPPED/trailing event, missing COMPLETE/manifest receipt, incorrect C001/BEGIN state, wrong role/returned ID/revision/body/hash rejected with zero local/remote effects. |
| RCN-02 six items | Fake stable six private Docs + CURRENT index approved; distinct ID, appProperties, private owner, parent, MIME, body/revision, visible child set, pagination, snapshot/CURRENT/manifest mismatch each blocks. No global-inventory claim. |
| RCN-03 plan | Deterministic full six-ID `documents` and empty pending projection; preserves v1 identity; binds *raw* old registry + sidecar, revisions and canonical CURRENT/fixture; changed one input invalidates plan. No side effects on plan. |
| RCN-04 operator gate | No W approval -> no backup/registry write; exact approval/hash/folder/path mismatch -> block; exclusively created byte-exact backup and exactly one atomic registry commit only after all checks; sidecar unchanged. |
| RCN-05 crash | Fail immediately before/after every fake backup/atomic-write/readback step; process restart with existing backup claim cannot write again; old blocked state or fully projected state only, never partially registered documents; no false success. |
| RCN-06 ordinary publisher | Original pending rejects `AppBackend`; fully reconciled fake state accepted for later read-only preview, but no normal apply invoked by reconciliation and no X/API mutation. |
| RCN-07 evidence | RED failure must be missing-contract RED, GREEN + Windows full suite, exact-head CI and separate L2. No live/private path, token, IDs or fixture substitution in CI; no Ready/merge/cleanup. |

## 10. Required follow-up sequence

1. Peer-review this specification and freeze AC. The current Issue #65 branch contains **specification only**; no RED/GREEN or real-operation claim.
2. Have Codex create synthetic in-memory/fake tests **RED** for RCN-01..07 in the dependent topic branch, with deterministic fixtures built via the real fake recovery executor rather than hand-invented private state. Keep error reports safe.
3. Implement only the narrow code needed for **GREEN**; validate all tests Windows Python 3.12, full regression, policy check, exact HEAD and separate adversarial L2. Update Draft PR with evidence.
4. Resolve PR #63's human Ready/merge independently; after it is merged, rebase/retarget Issue #65 against actual main without taking a human gate.
5. Only then request separate owner Gate R (live read-only) and later W (one-time local registry write). After proven reconciliation, request distinct authorizations for normal dry-run and publisher scenario qualification.
