# Project Status

## 30-second state

- **Goal:** Read-only official X API context reader.
- **Current work:** Issue #21, FR-004 authenticated liked-post lookup with bounded one-page CLI, on `issue-21-fr004-likes`.
- **Starting HEAD:** `28d4cf24e421f802648a72ec6b02ec2c87f95e84`, independently matched to the GitHub topic branch before implementation.
- **Dependency:** FR-003 / PR #20 and the shared authenticated-subject boundary are present; canonical main was observed at `cc0ef49cb452a3431b49cba4f20550314fe334d5`.
- **Implementation:** `likes` now uses the existing bounded collection flow, with canonical subject/page output and aggregate safe diagnostics.
- **Validation:** TEST_MATRIX preceded tests; test commit `cbc020f` preceded product code. The 18 FR-004 tests initially produced 13 failures and 4 missing-behavior errors. Initial implementation passed all 18 targeted and 115 total tests. Final exact-head validation and independent review belong to the durable evidence and task report.
- **Human decision:** No PR or Ready transition is authorized. Ready / merge remain human-final.
- **Qualification:** No live credentials or X account reads; real API behavior remains unverified.

## Authority and risk

GitHub Issue #21 and accepted specifications own scope; Git owns source revisions. `PROJECT_PROFILE.toml` records authority and validation workspace paths; `BASELINE.md` defines governance.

Issue #21 facets: `CREDENTIALS`, `SECURITY_BOUNDARY`, `PRIVATE_DATA`, `PLATFORM_DEPENDENT`. Derived risk: **HIGH_IMPACT**. Final exact-head validation and L2 independent review are required. C2 comprehension covers subject authority, private output handling, bounded requests, conservative failure, and recovery.

## Command and authority boundary

`python -m x_context likes [--max-results 1..100] [--page-token <token>]`

- Only `X_CONTEXT_USER_ACCESS_TOKEN` supplies collection user authority. `X_CONTEXT_BEARER_TOKEN` continues to supply only `read`.
- Every valid invocation resolves official `/2/users/me`, then calls `bind_collection_subject` with that exact ID before one official GET `/2/users/{id}/liked_tweets` request.
- There is no target-user argument, automatic traversal, retry, or redirect following in this collection path. Default page size is 25; accepted range is 1..100. Invalid local inputs stop before transport.
- Canonical stdout contains `operation=likes`, resolved subject ID/optional username, existing Post id/text, and explicit page state. A continuation token means `complete=false`; only absence of continuation supports `complete=true`, regardless of item count.
- Canonical stdout is private activity output, including any continuation token. Default behavior does not save it. Diagnostics on stderr contain no private contents or opaque tokens.

## FR-003 reuse and compatibility

A small private `_lookup_collection` helper holds the existing FR-003 algorithm. A closed mapping selects bookmarks or liked_tweets; it accepts no arbitrary endpoint or target. `lookup_bookmarks` retains its signature and `BookmarksLookupResult` result type; `lookup_likes` adds the corresponding typed entry point. Both result types share diagnostic fields. The existing redirect-refusing transport is reused unchanged.

CLI option construction and diagnostic formatting are shared. Bookmarks retains its canonical operation and `rate_limits.bookmarks` key; likes uses `rate_limits.likes`. Existing FR-003 tests are unchanged. There are no additional canonical Post fields or changes to the authenticated-subject implementation or read flow.

## Failure, diagnostics, and recovery

Request attempts aggregate subject resolution and collection retrieval. Safe rates remain separate under `rate_limits.subject` and `rate_limits.likes`, because the endpoints have distinct budgets. Failures report zero returned items and no returned continuation. Invalid page sizes are not echoed; parser failures report requested size as unknown.

Subject mismatch stops before collection transport. Ambiguous failures (including collection 404 and ambiguous 429), malformed/contradictory success, and transport exceptions fail closed as `provider_error`. Safe subject rates survive subject-payload validation failure. Recovery is to inspect the stable category and safe request/rate facts, correct local input or authorization, and explicitly retry. No unofficial fallback is available.

## Evidence and remaining uncertainty

See `docs/TEST_MATRIX.md`, `tests/test_fr004_likes.py`, and `docs/specs/0001-fr004-likes-clarification.md`. Tests use fake credentials/transports only. Commands:

- `python -m unittest discover -s tests -p test_fr004_likes.py -v`
- `python -m unittest discover -s tests -v`
- `git diff --check`

Authoritative validation uses tracked `scripts/Invoke-XContextValidation.ps1`, the profile-declared canonical repository, disposable worktree root, and durable log directory. Passing unit tests do not establish CI, real API qualification, or human acceptance.

OAuth browser/PKCE, refresh-token persistence, multi-page behavior, mutations, arbitrary targets, scraping, cookies, and internal GraphQL remain out of scope. No default private-data persistence was added. Live smoke is prohibited for this task and remains deferred to a separately authorized action.
