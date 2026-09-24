# Project Status

## 30-second state

- **Goal:** Read X content through the official X API for local tooling and AI-assisted analysis while preserving a narrow read-only authority boundary.
- **Repository:** `oimus1976/x-context` is public; GitHub remains the implementation/history/share-state authority.
- **Completed product foundation:** FR-001 URL parsing, FR-002 official single-Post lookup, FR-005 canonical read JSON, FR-006 read CLI, authenticated-subject binding, FR-003 bookmarks, FR-004 likes, OAuth 2.0 Authorization Code + PKCE acquisition, credential lifecycle, and the end-user OAuth bootstrap CLI.
- **OAuth bootstrap closeout:** PR #37 merged as `45d4347fd7caa1d1232cd7a7a306396eb4c5d301`; Issue #36 closed, merge-commit `project-ci` / `policy-check` passed, and canonical local `main` was fast-forwarded cleanly with local closeout PASS.
- **Current maintenance workstream:** Issue #38 / Draft PR #39 replaces manually transcribed post-merge SHAs and chat-only closeout snippets with a tracked authoritative post-merge closeout command.
- **Current branch:** `issue-38-post-merge-closeout`, based on `45d4347fd7caa1d1232cd7a7a306396eb4c5d301`.
- **Current validation:** exact head `9d4d50cb9eaaa9d9ff16b9aec68971a2b15f92ca` passed hosted `project-ci` / `policy-check`; project CI passed 196 tests on Ubuntu with only the expected Windows-only real-DPAPI test skipped. A docs-only status update moves the head once more, so hosted CI must confirm the new head and Windows exact-head validation remains required before the human Ready gate.
- **Human decisions:** Ready, merge, destructive cleanup, real-provider login/refresh/revoke qualification, and any authority expansion remain human-final.

## Current Issue #38 — authoritative post-merge closeout

PR #37 exposed a maintenance-process defect rather than a product defect: an ad hoc closeout command still contained the literal placeholder `<PR #37 merge commit SHA>`, which reached Git and correctly failed with a non-zero exit before canonical `main` was mutated. The corrected retry then completed safely, but the event showed that authoritative GitHub merge evidence should not be manually copied into executable snippets.

Draft PR #39 introduces:

- `python scripts/post_merge_closeout.py --pr <number> --repository owner/repo`;
- PR number as the only operator-supplied PR identity;
- repository identity binding against the configured GitHub remote before effects;
- authenticated GitHub reads for merged PR state, exact PR head, exact merge commit, closing Issues, and merge-commit `push` CI;
- required exact-SHA `project-ci` / `policy-check` success before canonical synchronization;
- canonical remote refresh plus merge-commit containment proof;
- canonical synchronization by `git merge --ff-only` only;
- native diagnostic retention with process exit code as the authority;
- HTTPS GitHub remote userinfo redaction in surfaced native diagnostics;
- reuse of the existing `verify_local_closeout.py` boundary;
- final GitHub evidence revalidation before PASS;
- PR worktree inventory without deletion or switching;
- no reset/rebase/stash/force fallback and no Issue/branch/ref/worktree/file mutation beyond the bounded canonical fast-forward.

The normative contract is `docs/specs/0005-post-merge-closeout-command.md`. The contract tests were committed before implementation. `scripts/post_merge_cleanup.py` remains a separate explicit destructive authority boundary.

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

- Current workstream: GitHub Issue #38 / Draft PR #39.
- Current requirement/AC contract: `docs/specs/0005-post-merge-closeout-command.md`.
- Current test-first contract: `tests/test_post_merge_closeout_command.py`.
- Current implementation: `scripts/post_merge_closeout.py`.
- Existing non-destructive verifier: `scripts/verify_local_closeout.py`.
- Separate destructive cleanup boundary: `scripts/post_merge_cleanup.py`.
- Shared Git/worktree state helpers: `scripts/closeout_state.py`.
- Completed OAuth bootstrap: Issue #36 / PR #37; normative contract `docs/specs/0004-oauth-bootstrap-cli.md`.
- Lifecycle requirement and acceptance contract: `docs/specs/0003-credential-lifecycle.md`.
- Storage decision: `docs/adr/0005-dpapi-credential-storage.md`.
- Traceability: `docs/TEST_MATRIX.md`.
- Authoritative exact-head validator: `scripts/Invoke-XContextValidation.ps1`.
- Preserve unaccounted local work and fail closed on uncertain GitHub evidence, native-command failure, credential/private-data exposure, or destructive cleanup.
