# Project Status

## 30-second state

- **Goal:** Read X content through the official X API for local tooling and AI-assisted analysis while preserving a narrow read-only authority boundary.
- **Repository:** `oimus1976/x-context` is public; GitHub remains the implementation/history/share-state authority.
- **Completed foundation:** FR-001 URL parsing, FR-002 official single-Post lookup, FR-005 canonical read JSON, FR-006 read CLI, authenticated-subject binding, FR-003 bookmarks, FR-004 likes, OAuth 2.0 Authorization Code + PKCE acquisition, public-repository closeout, and the credential lifecycle from Issue #32 / PR #33.
- **Credential lifecycle closeout:** PR #33 merged as `d98d04be9c4ea82ababe7cb6b16a85e3b1dc240f`; Issue #34 / PR #35 then aligned post-merge documentation and PR #35 merged as `4f0bd3151d737b5ea40cb1891ca0a97fa3fa1efc`.
- **Current product workstream:** Issue #36 / Draft PR #37 adds a bounded end-user `auth login` composition for the existing OAuth acquisition + secure lifecycle persistence path before adding P1 data surfaces.
- **Current branch:** `issue-36-oauth-bootstrap-cli`, based on `4f0bd3151d737b5ea40cb1891ca0a97fa3fa1efc`.
- **Current validation:** initial Draft PR branch-head `project-ci` and `policy-check` passed on implementation head `8676b875304ee7e4bf3e5d114a91f4477680401e`; subsequent documentation commits move the head, so final-head validation remains pending.
- **Human decisions:** Ready, merge, destructive cleanup, real-provider login/refresh/revoke qualification, and any authority expansion remain human-final.

## Current Issue #36 — end-user OAuth bootstrap

The remaining P0 usability gap is no longer token acquisition or lifecycle storage in isolation: both exist as tested library boundaries. The gap is a stable user-facing path that composes them without requiring manual access-token injection or direct Python-library use.

Draft PR #37 therefore introduces:

- `python -m x_context auth login` as the only new command surface;
- `X_CONTEXT_OAUTH_CLIENT_ID` as the existing public Client ID source;
- `X_CONTEXT_OAUTH_REDIRECT_URI` as the exact registered fixed loopback redirect configuration;
- reuse of the existing `OAuthConfig` and `acquire_user_token(..., refresh_capable=True)` boundary;
- reuse of the existing `persist_oauth_result(...)` and DPAPI default store;
- bootstrap-specific fail-closed validation requiring both a returned refresh token and positive expiry duration before persistence;
- no import of `X_CONTEXT_USER_ACCESS_TOKEN` into managed storage;
- no X content read as part of login;
- no write, DM, follows, list, block, mute, or other P1 scope expansion.

The normative proposed contract is `docs/specs/0004-oauth-bootstrap-cli.md`. Tests in `tests/test_oauth_bootstrap_cli.py` were committed before the product-code implementation. The first hosted branch-head run passed both required workflows; exact current-head validation and adversarial review remain required before human Ready consideration.

Current X provider facts were re-verified on 2026-09-17 against official documentation: Authorization Code + PKCE remains supported; Native Apps remain public clients; `offline.access` remains the documented refresh-token scope; public-client token requests use Client ID rather than relying on a client secret; redirect URI exact matching remains required. These remain external provider facts and are not treated as immutable product constants.

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

- Current workstream: GitHub Issue #36 / Draft PR #37.
- Current proposed requirement/AC contract: `docs/specs/0004-oauth-bootstrap-cli.md`.
- Current test-first contract: `tests/test_oauth_bootstrap_cli.py`.
- Completed lifecycle workstream: GitHub Issue #32 / PR #33.
- Post-merge lifecycle documentation closeout: Issue #34 / PR #35.
- Lifecycle requirement and acceptance contract: `docs/specs/0003-credential-lifecycle.md`.
- Storage decision: `docs/adr/0005-dpapi-credential-storage.md`.
- Traceability: `docs/TEST_MATRIX.md`.
- OAuth implementation boundary: `x_context/oauth.py`.
- Lifecycle implementation: `x_context/credential_lifecycle.py`.
- CLI composition: `x_context/cli.py`.
- Synthetic lifecycle tests: `tests/test_credential_lifecycle.py` and `tests/test_credential_lifecycle_cli_ordering.py`.
- Real Windows DPAPI boundary test: `tests/test_credential_lifecycle_windows_dpapi.py`.
- Authoritative local validator: `scripts/Invoke-XContextValidation.ps1`.
- Preserve unaccounted local work and fail closed on uncertain credential state, private-data exposure, destructive cleanup, or provider authority.
