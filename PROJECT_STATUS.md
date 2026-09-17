# Project Status

## 30-second state

- **Goal:** Read X content through the official X API for local tooling and AI-assisted analysis while preserving a narrow read-only authority boundary.
- **Repository:** `oimus1976/x-context` is public; GitHub remains the implementation/history/share-state authority.
- **Completed foundation:** FR-001 URL parsing, FR-002 official single-Post lookup, FR-005 canonical read JSON, FR-006 read CLI, authenticated-subject binding, FR-003 bookmarks, FR-004 likes, OAuth 2.0 Authorization Code + PKCE acquisition, public-repository closeout, and the credential lifecycle from Issue #32 / PR #33.
- **Credential lifecycle merge:** PR #33 merged to `main` as `d98d04be9c4ea82ababe7cb6b16a85e3b1dc240f`; Issue #32 is closed as completed.
- **Current closeout:** Issue #34 updates post-merge documentation only; it adds no product, credential, provider, or authority behavior.
- **Next product workstream:** not yet selected. After Issue #34 closes, start a new Issue from current `main` before implementation.
- **Human decisions:** Ready, merge, destructive cleanup, real-provider refresh/revoke qualification, and any authority expansion remain human-final.

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

## Review and validation closeout

PR #33 underwent repeated adversarial/L2 review. Material findings were remediated before merge:

1. **Refresh-token omission semantics:** carrying the old refresh token forward would rely on undocumented provider reuse semantics. The merged implementation fails closed when a refresh response omits the replacement refresh token.
2. **Revoke/logout overclaim:** the contract is a bounded single-token revoke plus local delete, not complete provider logout or token-family invalidation.
3. **Invalid-input ordering regression:** bookmarks/likes validate local arguments before lifecycle credential resolution, so invalid input cannot trigger OAuth refresh or X collection traffic.
4. **Real DPAPI evidence gap:** a Windows-only synthetic integration test now exercises the real `CryptProtectData` / `CryptUnprotectData` boundary, verifies round-trip behavior, confirms plaintext token sentinels are absent from the durable protected file, and deletes the temporary credential.

Final PR head before merge:

`54c4e762cc857c159ef6a3d30a11e339f91d8c28`

Authoritative Windows exact-head evidence on that head:

- 163 tests passed;
- `test_CRED_real_windows_dpapi_round_trip_and_plaintext_absent` passed on Windows and was not skipped;
- `git diff --check origin/main...HEAD` passed;
- verification worktree was clean and removed normally;
- canonical checkout returned to `main`, clean, with the then-current `main == origin/main`;
- durable UTF-8 evidence log: `logs/verification/issue-32-final-dpapi-exact-head-20260917-213451.log`;
- `FINAL_RESULT=PASS`.

Post-merge GitHub evidence on merge commit `d98d04be9c4ea82ababe7cb6b16a85e3b1dc240f`:

- PR #33 is merged and closed;
- Issue #32 is closed as completed;
- `main` points to the merge commit;
- hosted `project-ci` passed;
- hosted `policy-check` passed.

Real-provider refresh/revoke qualification was not performed as part of Issue #32 and remains a separate explicit human decision.

## Authority and safety boundaries

- Official X APIs are the only supported provider boundary.
- No scraping, browser-cookie reuse, unofficial/internal GraphQL fallback, OAuth 1.0a fallback, write scope, or client secret is introduced.
- Actual credentials and private X payloads must not enter the repository, Issues/PRs, CI artifacts, normal logs, or retained validation evidence.
- DPAPI protection is an at-rest/current-user boundary, not isolation from every process running as that same user.
- Corrupt/unreadable/unsupported credential state fails closed and is not auto-deleted.
- Real provider refresh/revoke qualification remains human-gated.
- Ready and merge are separate human-final gates.
- Destructive local/remote branch cleanup remains a separate human decision and is not part of Issue #34.

## Recovery / first diagnostic entry points

- Completed lifecycle workstream: GitHub Issue #32 / PR #33.
- Post-merge documentation closeout: Issue #34.
- Requirement and acceptance contract: `docs/specs/0003-credential-lifecycle.md`.
- Storage decision: `docs/adr/0005-dpapi-credential-storage.md`.
- Traceability: `docs/TEST_MATRIX.md`.
- Lifecycle implementation: `x_context/credential_lifecycle.py`.
- Collection integration: `x_context/cli.py`.
- Synthetic lifecycle tests: `tests/test_credential_lifecycle.py` and `tests/test_credential_lifecycle_cli_ordering.py`.
- Real Windows DPAPI boundary test: `tests/test_credential_lifecycle_windows_dpapi.py`.
- Authoritative local validator: `scripts/Invoke-XContextValidation.ps1`.
- Preserve unaccounted local work and fail closed on uncertain credential state, private-data exposure, destructive cleanup, or provider authority.