# Project Status

## 30-second state

- **Goal:** Read-only official X API context reader.
- **Current work:** Issue #19, FR-003 authenticated bookmarks with bounded one-page CLI, on `issue-19-fr003-bookmarks`.
- **Starting HEAD:** `bfeb8a020f54c1638e63a3cd3945c57926692b9c`, independently matched to the GitHub topic branch before implementation.
- **Dependency:** Issue #11 / PR #18 authenticated-subject boundary is available; GitHub main was independently observed at `d36a8cab3263d662eb5706e563aadd55a05b0c6e`.
- **Implementation:** One-page bookmarks provider and CLI, canonical subject/page integration, and safe aggregate diagnostics added locally.
- **Validation:** Contract tests were added before product code and failed (10 failures, 4 missing-behavior errors); initial implementation passed 14 FR-003 and 97 total tests. Independent review found a transport-error category leak; regression and remediation added. Final exact-head validation/review evidence belongs to the final task report and durable validation log.
- **Human decision:** No PR or Ready transition is authorized in this task. Ready / merge remain human-final.
- **Qualification:** No live credentials or X account reads; real API behavior remains unverified.

## Authority and risk

GitHub Issues and accepted specifications own scope; Git owns source revisions. `PROJECT_PROFILE.toml` records authority and validation workspace paths; `BASELINE.md` defines governance.

Issue #19 facets: `CREDENTIALS`, `SECURITY_BOUNDARY`, `PRIVATE_DATA`, `PLATFORM_DEPENDENT`. Derived risk: **HIGH_IMPACT**. Independent review and exact-head evidence are required before any human final action. Required comprehension is C2: the owner should understand subject authority, private output handling, bounded requests, conservative failure, and recovery.

## Command and authority boundary

`python -m x_context bookmarks [--max-results 1..100] [--page-token <token>]`

- Only `X_CONTEXT_USER_ACCESS_TOKEN` supplies user-context authority. `X_CONTEXT_BEARER_TOKEN` continues to supply only the existing `read` command.
- Every valid invocation resolves the official `/2/users/me` subject anew, then calls `bind_collection_subject` with that exact ID before one official GET `/2/users/{id}/bookmarks` request.
- There is no target-user argument, automatic traversal, retry, or redirect following in this collection path. Default page size is 25, cap is 100; invalid local inputs stop before transport.
- Successful stdout contains canonical JSON: `operation=bookmarks`, resolved subject ID/optional username, existing Post id/text, and explicit page state. Only absence of provider continuation supports `complete=true`; item count alone does not.
- Canonical stdout is private activity output, including its continuation token. Default behavior does not save it. Diagnostics on stderr contain no private contents or opaque tokens.

## Failure and diagnostics

Request attempts include subject lookup and the bookmark request. Safe rate metadata is reported separately under `rate_limits.subject` and `rate_limits.bookmarks` because these are distinct provider budgets. Failures report zero returned items and no returned continuation; an invalid page size is not echoed. Parser failure reports requested size as unknown.

Existing stable categories remain in force. Subject mismatch stops before collection transport. Ambiguous failures (including bookmark 404 and ambiguous 429), malformed/contradictory success, and transport exceptions fail closed as `provider_error`. Available safe subject rates are retained even if subject payload validation fails. Recovery is to inspect the category and safe request/rate facts, correct local input or authorization, and explicitly retry; no unofficial fallback is available.

## Evidence and remaining work

See `docs/TEST_MATRIX.md`, `tests/test_fr003_bookmarks.py`, and `docs/specs/0001-fr003-bookmarks-clarification.md`. Unit/contract evidence uses fake credentials/transports only. Full regression command: `python -m unittest discover -s tests -v`.

Authoritative exact-head validation uses tracked `scripts/Invoke-XContextValidation.ps1` and the profile-declared canonical repository, disposable worktree root, and durable log directory. A local passing suite alone is not a claim of authoritative validation, CI, real-boundary qualification, or acceptance.

OAuth browser/PKCE, refresh-token persistence, FR-004 likes, multi-page behavior, mutation, arbitrary targets, scraping, cookies, and internal GraphQL remain out of scope. No default bookmark persistence was added. No live smoke is permitted in this task; that qualification remains deferred to a separately authorized action.
