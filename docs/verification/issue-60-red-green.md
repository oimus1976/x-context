# Issue #60 — Requirement / AC / RED / GREEN evidence

Base: merged PR #59 `327bee86e917be250f19cb5a77127d6c8f5eaa05`.
Branch: `codex/issue-60-synthetic-drive-connector`.
Risk HIGH_IMPACT: EXTERNAL_WRITE, SECURITY_BOUNDARY, PLATFORM_DEPENDENT.

## Authority and closeout

Read authenticated Issue #60 and comments 6133391331 / 6133413233.
Ran owner-requested `python scripts/post_merge_closeout.py --pr 59
--repository oimus1976/x-context`. Initial sandbox network attempt failed
before effects; a network-enabled ordinary user retry returned
POST-MERGE CLOSEOUT: PASS, merge-push CI PASS, closing Issues PASS and fresh
GitHub revalidation PASS. Canonical main fast-forwarded to the exact merge SHA,
clean; topic/other worktrees preserved. IsUserAnAdmin=False directly observed.
Network sandbox escape did not elevate to Windows Administrator.

## Requirement and tests before implementation

CW-1..6 and AC-D1..D7 mapping precede implementation in the connected workflow
spec and TEST_MATRIX. Initial connector test file ran RED: one import error
because the new connector module did not exist. No product tests weakened.

After implementation, fake transport tests established empty-create→verified
move→text sequence, complete-inventory/owner-only checks, immutable sentinel,
root-failure ID preservation/no blind retry, CRLF-only faithful canonicalization,
actual portable-directory verification, stable identity, no-op repeat, intended
edit/withdrawal writes and CURRENT-last. Added adversarial permission-expansion,
sentinel-change-during-move, revision-conflict and arbitrary-body rejection tests.
Final new subset: 13 PASS. Earlier complete regression: 335 PASS, no skips
(before five extra adversarial tests); baseline PASS. Final exact-head full
regression and independent L2 are separate PR evidence, never inferred here.

Sandbox-only tests also encountered Windows temporary-directory ACL errors in
new and existing tests; ordinary non-admin execution avoided those errors.
Runtime: Windows 11 10.0.26300, Python 3.12.10, IsUserAnAdmin=False.

## Actual external boundary and limitations

Connected tools freshly read exact sandbox/PoC parent, shared=false and one
owner-only permission; sentinel ID/title/parent/body remain as in the prior
smoke. Observations are read-only; no new cloud objects or content writes.
list_folder provides a bounded scan; raw-parent legacy search returned a
results-only response, with no completeness receipt. Typed paginated search
does not cover arbitrary child types. This is insufficient for CW-2.
No supported callable authenticated Python transport is available.

AC-D1/D2: prior connected-tool smoke and fresh readback only.
AC-D3/D4 live: NOT_RUN_UNSUPPORTED_INVENTORY_AND_BRIDGE.
AC-D5/D6: PENDING human generated-view/offline-origin UAT.
AC-D7: X/OAuth requests and actual private transfers zero.
No new credentials/services, product-store reads, cloud sharing changes,
Ready/merge, branch/worktree removal or destructive cleanup.

The adapter contract is trusted injected transport code, not validation of
user-submitted metadata receipts. No cross-file transaction or full erasure
guarantee; a journal failure/provider timeout can leave a root orphan. Stop
and reconcile the durable journal/recent creations before constructing another
adapter instance. Independent transport/native-body/cloud qualification remains
necessary before claiming real publishing.
