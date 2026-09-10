# Project Status

> Keep this top block short enough to read in about 30 seconds.

## 30-second state

- **Goal:** Establish a read-only official-X-API context reader with specification-driven traceability and a broader staged personal-context roadmap.
- **Current phase:** P0 implementation, second slice (Issue #5 / FR-005 minimal canonical `read` schema).
- **Last completed:** Issue #3 / PR #4 (FR-001 URL parsing) merged to `main` at `be3715cfb8a54059fe6d740498e9092c9c9f56a4`; FR-001 local tests 6/6 passed and adversarial review found no MAJOR/MODERATE defect.
- **Now working on:** Local-only canonical JSON envelope/item model for successful `read` output, with no provider/network/auth behavior.
- **Next:** Validate the exact Issue #5 branch head with FR-001 + FR-005 tests and static diff checks, then adversarially review schema leakage/unknown semantics before opening or advancing a Draft PR.
- **Human decision pending:** Ready/merge only after exact-head validation and review evidence; no protected decision is currently implied.
- **Main risks:** Specification drift and accidentally letting provider-specific/raw/secret data become public schema; persistent project facets remain private data, credentials, and X platform dependency, although Issue #5 itself is local deterministic modeling only.
- **Required comprehension level:** C1

## Current authority summary

See `PROJECT_PROFILE.toml`; baseline rules live only in `BASELINE.md`.

- Planning: GitHub Issues and accepted specs/ADRs
- Execution: Git topic branches and pull requests
- Source code: Git
- Private/actual data: Local runtime only; not repository/PR/CI artifacts by default
- CI evidence: GitHub Actions when available; currently unavailable because the monthly Actions-minute quota is exhausted. Do not infer CI success from queued/unstarted runs.
- Production/deployed state: N/A during experimental MVP

## Current risk facets

Persistent project facets:

- PRIVATE_DATA
- CREDENTIALS
- PLATFORM_DEPENDENT

Default project risk level: `ELEVATED`.

Change-specific Issue #5 behavior is local-only canonical modeling and introduces no credential loading, private-data access, external write, network request, OAuth flow, or real-provider access path.

## Validated facts

- Repository: `oimus1976/x-context`.
- Accepted specification baseline merge commit: `2af03c4c9a7ae94158ebe3cfa6fdb4ba131e0991`.
- Issue #1 is closed/completed and PR #2 is merged.
- Issue #3 is closed/completed and PR #4 is merged.
- Current `main`: `be3715cfb8a54059fe6d740498e9092c9c9f56a4`.
- PR #4 exact head: `8b3d0a2f771ce1a31fc205d7ab3b6af4194e78e3`.
- Active work item: Issue #5, `Implement FR-005 minimal canonical schema for read`.
- Active branch: `feat/issue-5-fr005-canonical-schema`.
- No FR-002 provider call, OAuth, bookmark, like, persistence, pricing, rate-limit, or unofficial-provider behavior is authorized in Issue #5.
- The current FR-005 slice uses `schema_version = "1"`, `source = "x"`, `operation = "read"`, `subject = null`, a UTC `retrieved_at`, and a complete/no-token page envelope.
- The minimum current post item is normalized `id` + `text`; unrequested/unresolved optional expansion-backed fields are omitted rather than fabricated as known-empty.
- `page.complete = true` with a non-null continuation token is rejected by the shared page model.
- A local mirror run of the proposed branch content passed 14 tests total (6 FR-001 regressions + 8 FR-005 tests). This is development evidence only; exact Git branch-head validation in the operator checkout is still required before Ready.
- GitHub Actions remains unavailable due to exhausted monthly Actions minutes; local/static validation is required and CI success must not be claimed.

## Current implementation scope

Issue #5 is limited to the minimal canonical schema needed by `read`:

- canonical `read` envelope constants and shape;
- UTC/RFC3339 acquisition timestamp normalization;
- `subject = null` for arbitrary post read;
- minimum post item representation using normalized numeric `id` and `text`;
- no raw/provider response passthrough fields;
- explicit shared `next_token` / `complete` invariant;
- deterministic unit tests and TEST_MATRIX traceability.

Explicitly not authorized in Issue #5:

- FR-002 provider calls;
- FR-006 CLI wiring;
- OAuth/credentials/scopes;
- authenticated-subject resolution;
- bookmarks/likes;
- persistence;
- pricing/rate-limit/Owned Read logic;
- unofficial acquisition fallback.

## Known limitations / residual risks

- The GitHub branch has not yet been validated in the operator's canonical local checkout; the 14-test pass currently comes from a reconstructed local mirror of the relevant package/tests.
- FR-005 is not complete for collection operations. Authenticated `subject` provenance and collection-specific optional/known-empty semantics remain deferred to later workstreams.
- Optional author/created-at/canonical-URL/reference/media/link fields are intentionally not yet introduced. Their provider-backed shape must be verified against official X API behavior before they become canonical public fields.
- GitHub Actions is currently unavailable due to exhausted monthly Actions minutes; this is an evidence-availability limitation, not evidence of test failure or success.
- X API pricing, endpoints, OAuth scopes, Owned Read qualification, billing behavior, and rate-limit semantics remain external facts for FR-002 or later and must be re-verified against official information before implementation.
- Bookmark Folders remain a non-blocking P1 candidate gap and are unrelated to Issue #5.

## Deferred work

After Issue #5, the accepted preferred P0 implementation order remains:

- FR-002 official post lookup;
- FR-006 `read` CLI;
- authenticated-subject resolution/binding contract for collections;
- FR-003 bookmarks;
- FR-004 likes.

Product-level P1-P3 candidates remain governed by SPEC-0000 and are not implied by Issue #5.

## Recovery / first diagnostic entry points

- For Issue #5, inspect this status record, Issue #5, `docs/specs/0001-mvp.md`, `docs/TEST_MATRIX.md`, `x_context/canonical.py`, `tests/test_fr005_canonical.py`, and `x_context/__init__.py`.
- Rollback/recovery entry point: Git history and the accepted specification baseline; do not add provider/raw fields merely to mirror a later X response conveniently.
- No local credential, private X activity data, or live X API access is required or authorized for Issue #5 validation.

## Recent meaningful changes

See `CHANGELOG.md` for semantic history and Git/PRs for implementation detail.
