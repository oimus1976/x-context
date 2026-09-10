# Project Status

> Keep this top block short enough to read in about 30 seconds.

## 30-second state

- **Goal:** Establish a read-only official-X-API context reader with specification-driven traceability and a broader staged personal-context roadmap.
- **Current phase:** P0 implementation, first vertical slice (Issue #3 / FR-001).
- **Last completed:** Issue #1 / PR #2 established and merged the accepted SPEC-0000/SPEC-0001 baseline after adversarial and independent review.
- **Now working on:** FR-001 strict local parsing of supported X/Twitter status URLs with acceptance tests.
- **Next:** Run local FR-001 tests and static diff validation, then review the exact topic head before any Ready decision.
- **Human decision pending:** Ready/merge for the FR-001 implementation PR after evidence review.
- **Main risks:** Specification drift and accidental scope expansion; persistent project facets remain private data, credentials, and X platform dependency, although Issue #3 itself is local deterministic parsing only.
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

Change-specific Issue #3 behavior is local-only parsing and introduces no credential, private-data, external-write, or real-provider access path.

## Validated facts

- Repository: `oimus1976/x-context`.
- Accepted specification baseline merge commit: `2af03c4c9a7ae94158ebe3cfa6fdb4ba131e0991`.
- Issue #1 is closed/completed and PR #2 is merged.
- Active work item: Issue #3, `Implement FR-001 X status URL parsing contract`.
- Active branch: `feat/issue-3-fr001-url-parsing`.
- SPEC-0001 FR-001 accepts only HTTPS X/Twitter status URL families for exact numeric post-ID extraction; query/fragment do not alter the ID.
- Invalid FR-001 input must fail locally before any network/provider access.
- The initial Issue #3 implementation uses only the Python standard library and adds no X API/OAuth behavior.
- GitHub Actions remains unavailable due to exhausted monthly Actions minutes; local/static validation is required and CI success must not be claimed.

## Current implementation scope

Issue #3 is limited to FR-001:

- strict supported-host/scheme/path parsing;
- exact numeric post-ID extraction;
- query/fragment ignoring;
- explicit invalid-input failure;
- no-network behavior for invalid input;
- planned/adversarial automated tests.

Explicitly not authorized in Issue #3:

- FR-002 provider calls;
- OAuth/credentials;
- canonical response-model work beyond FR-001 needs;
- bookmarks/likes;
- persistence;
- pricing/rate-limit logic;
- unofficial acquisition fallback.

## Known limitations / residual risks

- The implementation and tests on the active topic branch are not yet validated by local execution; do not treat the code as passing until local evidence is recorded.
- GitHub Actions is currently unavailable due to exhausted monthly Actions minutes; this is an evidence-availability limitation, not evidence of test failure or success.
- X API pricing, endpoints, OAuth scopes, Owned Read qualification, billing behavior, and rate-limit semantics remain external facts for later work and are not part of FR-001.
- Bookmark Folders remain a non-blocking P1 candidate gap and are unrelated to Issue #3.

## Deferred work

After FR-001, the accepted preferred P0 implementation order remains:

- FR-005 minimal canonical schema needed by `read`;
- FR-002 official post lookup;
- FR-006 `read` CLI;
- FR-003 bookmarks;
- FR-004 likes.

Product-level P1-P3 candidates remain governed by SPEC-0000 and are not implied by Issue #3.

## Recovery / first diagnostic entry points

- For Issue #3, inspect this status record, Issue #3, `docs/specs/0001-mvp.md`, `docs/TEST_MATRIX.md`, `x_context/url_parser.py`, and `tests/test_fr001_url_parser.py`.
- Rollback/recovery entry point: Git history and the accepted specification baseline; do not broaden accepted URL families to make a failing parser convenient.
- No local credential or private X activity data is required or authorized for Issue #3 validation.

## Recent meaningful changes

See `CHANGELOG.md` for semantic history and Git/PRs for implementation detail.
