# Project Status

## 30-second state

- **Goal:** Read X content through the official X API for local tooling and AI-assisted analysis while preserving a narrow read-only authority boundary.
- **Repository:** `oimus1976/x-context` is public; GitHub remains the implementation/history/share-state authority.
- **Completed product foundation:** FR-001 URL parsing, FR-002 official single-Post lookup, FR-005 canonical read JSON, FR-006 read CLI, authenticated-subject binding, FR-003 bookmarks, FR-004 likes, OAuth 2.0 Authorization Code + PKCE acquisition, credential lifecycle, the end-user OAuth bootstrap CLI, and SPEC-0006 authenticated own-post read (`x-context posts`).
- **OAuth bootstrap closeout:** PR #37 merged as `45d4347fd7caa1d1232cd7a7a306396eb4c5d301`; Issue #36 closed, merge-commit `project-ci` / `policy-check` passed, and canonical local `main` was fast-forwarded cleanly with local closeout PASS.
- **Completed maintenance:** Issue #38 / PR #39 delivered authoritative post-merge closeout. Real PR #39 dogfood exposed a closing-Issue state lookup incompatibility; Issue #40 / PR #41 fixed it and merged as `f6d0335ffefea882e8f3cecf2b7911892ecb1a65`.
- **Completed specification:** Issue #42 / PR #43 specified authenticated own-post read in SPEC-0006 and the test matrix. PR #43 merged as `7ca8549d1622c930986d23c12eca5eb2cd85f778`; this was documentation-only.
- **Implementation status (2026-10-05):** Issue #45 / PR #46 merged as `9cda4bfae282dad52bc58c41773065c5e9f973b4`; `x-context posts` is in `main`. Codex-reported local Windows evidence was 225/225 PASS with no skips (23 own-post, 201 pre-existing, 1 shared refresh-accounting regression). Issue #47 / PR #48 repaired scoped non-destructive closeout and merged as `91a2133b64c71727d34718c5c2b315ec615ec7b2` (current GitHub `main` at this checkpoint). Both issues are closed; real X API qualification remains unperformed.
- **Verified GitHub evidence:** Both PR #46 and #48 were merged after review and hosted PR checks; required merge-commit `push` workflows `project-ci` / `policy-check` succeeded for #46 (37268993842 / 37268993881) and #48 (37279890100 / 37279890006). Operator-supplied Windows transcripts report non-destructive `POST-MERGE CLOSEOUT: PASS` for both and canonical local `LOCAL CLOSEOUT: PASS`, not independently executed by Chat. None of this establishes real X API/provider qualification.
- **Human decisions:** Ready, merge, destructive cleanup, real-provider login/refresh/revoke qualification, and any authority expansion remain human-final.

## Completed Issue #40 — closing-Issue state compatibility

PR #39's first real dogfood failed closed before canonical synchronization because real GitHub CLI `closingIssuesReferences` reports Issue identity but not nested Issue state. Issue #40 / PR #41 corrected the boundary by resolving each referenced Issue's state separately with authenticated `gh issue view <number> -R owner/repo --json number,state`, including final evidence revalidation.

PR #41 merged as `f6d0335ffefea882e8f3cecf2b7911892ecb1a65`. Exact PR head `52d815f8e1a72db3cf30c5e7406e401c6ec67527` had successful hosted `project-ci` and `policy-check`. The repair preserves fail-closed Issue-state validation, ff-only canonical synchronization, separate destructive cleanup, and the existing PR authority boundary. Normative clarification: `docs/specs/0005-closing-issue-state-clarification.md`.

## Completed authenticated own-post read — Issue #45 / PR #46

Issue #42 / PR #43 added normative `docs/specs/0006-own-post-read.md`, updated the SPEC-0001 canonical operation contract, and mapped AC-OWNPOST-001..007 in `docs/TEST_MATRIX.md`. PR #43 merged as `7ca8549d1622c930986d23c12eca5eb2cd85f778` (head `dd28edb9dc32c90a8a51235f7e557648a76645cf`, hosted `project-ci` and `policy-check` passed). This specification PR changed no implementation code or test bodies; Issue #42 is closed as a specification workstream.

SPEC-0006 binds the read to lifecycle-managed or explicitly overridden user-context credentials and the subject returned by official `GET /2/users/me`. Only `GET /2/users/{authenticated-subject-id}/tweets` with `exclude=retweets` is allowed; the subject's replies and quote posts remain eligible. It requires the existing `operation=posts` canonical envelope, page size default 25 / range 5..100, opaque explicit continuation, one tweets page per invocation, early local input rejection, existing errors/accounting, and credential/post-payload redaction and non-persistence boundaries.

Issue #45 / PR #46 added `posts [--max-results n] [--page-token opaque]` through the existing collection, canonical, and credential lifecycle paths. It resolves and binds the authenticated subject, requests exactly one tweets page with `exclude=retweets`, and rejects invalid local input before credential load/refresh. Bookmarks/likes retain 1..100. The shared parser rejects control-bearing provider continuation tokens; shared diagnostics count a failed refresh once rather than twice.

Codex-reported local Windows Python 3.12.14 validation passed all 225 tests with zero failures/errors/skips, including the real-DPAPI synthetic test. The 23 test contracts were preserved with 16 assertion hardenings across two files, and local policy compilation / `verify_repo.py --repository oimus1976/x-context` passed. Published implementation commit `6bd45ed26584994825228265317c1946e1d6cf11` received independent production/test-source review and successful GitHub-hosted `project-ci` (run 37267450298) / `policy-check` (run 37267450322). This hosted evidence is specific to that implementation SHA, separate from the local Windows report. Final PR #46 head `b14f79861eec52200c17abee41afef1c4e95fe11` passed subsequent docs-only exact-head checks and merged as `9cda4bfae282dad52bc58c41773065c5e9f973b4`; the merge-commit push checks passed and Issue #45 closed. Real-provider qualification remains unperformed. Arbitrary user selection, fetch-all, expansions, extra scopes, and unofficial access stay excluded. Ready, merge, and destructive cleanup remain human-final.

## Completed Issue #47 — scoped non-destructive closeout

PR #46's first Windows-local closeout stopped before canonical sync when seven unrelated Administrator-owned worktrees produced Git `dubious ownership`. Issue #47 / PR #48 narrowed **non-destructive** registry inspection to the canonical and relevant PR worktrees, retained strict pre-sync target checks, and left **destructive** cleanup safeguards unchanged. Codex-reported Windows validation for this change was 266/266 tests PASS without skips (225 existing + 41 new), not independently rerun by Chat.

PR #48 merged as `91a2133b64c71727d34718c5c2b315ec615ec7b2`, with Issue #47 closed and both merge-commit push checks successful. Operator-supplied PowerShell evidence then reported `POST-MERGE CLOSEOUT: PASS` for PRs #48 and #46 and `LOCAL CLOSEOUT: PASS`; clean canonical `main` and `origin/main` both matched that SHA. No worktree/branch deletion, ownership change, trust bypass, or live X provider qualification was part of this closeout.

## Completed OAuth bootstrap

Issue #36 / PR #37 closed the P0 usability gap between OAuth acquisition and lifecycle persistence by adding `python -m x_context auth login`.

The merged behavior:

- reads non-secret `X_CONTEXT_OAUTH_CLIENT_ID` and exact registered `X_CONTEXT_OAUTH_REDIRECT_URI`;
- composes the existing `OAuthConfig`, `acquire_user_token(..., refresh_capable=True)`, and lifecycle persistence boundaries;
- requests only `tweet.read users.read bookmark.read like.read offline.access`;
- requires a refresh token and positive expiry duration before persistence;
- never imports `X_CONTEXT_USER_ACCESS_TOKEN` into managed storage;
- performs no X content read during login;
- uses the existing Windows DPAPI `CurrentUser` protected store and atomic whole-record replacement.

Final PR #37 head `71248c4558e5bedd5e15e6549d5cfe55c3057995` passed 175 Windows tests including the real-DPAPI synthetic test, `git diff --check`, clean verification-worktree removal, and `FINAL_RESULT=PASS`. After merge, both required push workflows passed on `45d4347fd7caa1d1232cd7a7a306396eb4c5d301`, Issue #36 closed, and canonical local `main` synchronized cleanly. Real-provider browser/login qualification remains a separate human-gated decision.

## Completed credential lifecycle

Issue #32 introduced a lifecycle-managed user-context credential path while preserving the existing read-only/same-subject authority boundary.

The merged design is:

- Windows DPAPI `CurrentUser` protects one versioned credential envelope stored in a per-user local file;
- the complete protected envelope is the atomic replacement unit;
- OAuth acquisition remains non-persistent by default and persistence is explicit;
- `X_CONTEXT_USER_ACCESS_TOKEN` remains an explicit per-operation compatibility/recovery override and is never auto-imported;
- `X_CONTEXT_BEARER_TOKEN` remains app-only and is never a user-context fallback;
- known expiry uses a 300-second refresh-before-use safety window;
- one resolution performs at most one official refresh request;
- a successful refresh is accepted only when a safe access token and replacement refresh token are both returned;
- refresh-token omission fails closed and preserves the previously committed credential;
- local deletion and provider-side single-token revoke are distinct operations;
- provider revoke prefers the refresh token when present, otherwise the access token, and does not claim complete logout or token-family invalidation;
- collection-local invalid input is rejected before credential resolution so invalid input cannot trigger refresh or collection traffic;
- the first storage slice remains single-process/single-writer by contract.

ADR-0005 records the DPAPI choice. Generic Windows Credential Manager was considered but rejected for this slice because its Generic Credential blob has a documented size ceiling and splitting one logical token envelope across multiple credential records would weaken the desired whole-record atomic replacement model.

## Review and validation closeout for Issue #32

PR #33 underwent repeated adversarial/L2 review. Material findings were remediated before merge:

1. **Refresh-token omission semantics:** carrying the old refresh token forward would rely on undocumented provider reuse semantics. The merged implementation fails closed when a refresh response omits the replacement refresh token.
2. **Revoke/logout overclaim:** the contract is a bounded single-token revoke plus local delete, not complete provider logout or token-family invalidation.
3. **Invalid-input ordering regression:** bookmarks/likes validate local arguments before lifecycle credential resolution, so invalid input cannot trigger OAuth refresh or X collection traffic.
4. **Real DPAPI evidence gap:** a Windows-only synthetic integration test exercises the real `CryptProtectData` / `CryptUnprotectData` boundary, verifies round-trip behavior, confirms plaintext token sentinels are absent from the durable protected file, and deletes the temporary credential.

Final PR #33 head before merge:

`54c4e762cc857c159ef6a3d30a11e339f91d8c28`

Authoritative Windows exact-head evidence on that head:

- 163 tests passed;
- `test_CRED_real_windows_dpapi_round_trip_and_plaintext_absent` passed on Windows and was not skipped;
- `git diff --check origin/main...HEAD` passed;
- verification worktree was clean and removed normally;
- canonical checkout returned to `main`, clean, with the then-current `main == origin/main`;
- durable UTF-8 evidence log: `logs/verification/issue-32-final-dpapi-exact-head-20260917-213451.log`;
- `FINAL_RESULT=PASS`.

Post-merge GitHub evidence on PR #33 merge commit `d98d04be9c4ea82ababe7cb6b16a85e3b1dc240f` and documentation closeout merge `4f0bd3151d737b5ea40cb1891ca0a97fa3fa1efc` passed the hosted `project-ci` and `policy-check` workflows. Canonical local `main` was subsequently fast-forwarded to `4f0bd3151d737b5ea40cb1891ca0a97fa3fa1efc` with a clean working tree and `FINAL_RESULT=PASS` in the transient closeout log.

Real-provider login/refresh/revoke qualification was not performed as part of the lifecycle closeout and remains a separate explicit human decision.

## Authority and safety boundaries

- Official X APIs are the only supported provider boundary.
- No scraping, browser-cookie reuse, unofficial/internal GraphQL fallback, OAuth 1.0a fallback, write scope, or client secret is introduced.
- Actual credentials and private X payloads must not enter the repository, Issues/PRs, CI artifacts, normal logs, or retained validation evidence.
- DPAPI protection is an at-rest/current-user boundary, not isolation from every process running as that same user.
- Corrupt/unreadable/unsupported credential state fails closed and is not auto-deleted.
- Real-provider login/refresh/revoke qualification remains human-gated.
- Ready and merge are separate human-final gates.
- Destructive local/remote branch cleanup remains a separate human decision.

## Recovery / first diagnostic entry points

- Current workstream: docs-only Issue #49 restores status/changelog/test-matrix consistency after merged #46 and #48. No open product-implementation PR at this checkpoint. Next proposed practical work after documentation closeout is a separately human-authorized, minimal real-X-API smoke check; not executed by this documentation work.
- Normative own-post requirement/AC: `docs/specs/0006-own-post-read.md` and `docs/TEST_MATRIX.md`.
- Implementation entry points to inspect: `x_context/canonical.py`, `x_context/x_api.py`, `x_context/cli.py`, authenticated-subject binding, and existing bookmarks/likes collection tests.
- Completed closing-Issue compatibility: Issue #40 / PR #41; `docs/specs/0005-closing-issue-state-clarification.md` and `tests/test_post_merge_closeout_command.py`.
- Existing non-destructive merge closeout command: `scripts/post_merge_closeout.py`.
- Existing non-destructive verifier: `scripts/verify_local_closeout.py`.
- Separate destructive cleanup boundary: `scripts/post_merge_cleanup.py`.
- Shared Git/worktree state helpers: `scripts/closeout_state.py`.
- Completed OAuth bootstrap: Issue #36 / PR #37; normative contract `docs/specs/0004-oauth-bootstrap-cli.md`.
- Lifecycle requirement and acceptance contract: `docs/specs/0003-credential-lifecycle.md`.
- Storage decision: `docs/adr/0005-dpapi-credential-storage.md`.
- Traceability: `docs/TEST_MATRIX.md`.
- Authoritative exact-head validator: `scripts/Invoke-XContextValidation.ps1`.
- Preserve unaccounted local work and fail closed on uncertain GitHub evidence, native-command failure, credential/private-data exposure, or destructive cleanup.
