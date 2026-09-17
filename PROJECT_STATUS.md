# Project Status

## 30-second state

- **Goal:** Read X content through the official X API for local tooling and AI-assisted analysis while preserving a narrow read-only authority boundary.
- **Repository:** `oimus1976/x-context` is public; GitHub remains the implementation/history/share-state authority.
- **Completed foundation:** FR-001 URL parsing, FR-002 official single-Post lookup, FR-005 canonical read JSON, FR-006 read CLI, authenticated-subject binding, FR-003 bookmarks, FR-004 likes, OAuth 2.0 Authorization Code + PKCE acquisition, and public-repository closeout.
- **Active workstream:** Issue #32 / Draft PR #33 — secure credential lifecycle.
- **Current topic branch:** `issue-32-credential-lifecycle`; the exact current head is owned by PR #33 rather than duplicated here.
- **Human decisions:** Ready, merge, destructive cleanup, real-provider refresh/revoke qualification, and any authority expansion remain human-final.

## Credential lifecycle design

Issue #32 introduces a lifecycle-managed user-context credential path while preserving the existing read-only/same-subject authority boundary.

The accepted design is:

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

## Review/remediation state

PR #33 has undergone multiple adversarial passes. The following material findings were remediated:

1. **Refresh-token omission semantics:** carrying the old refresh token forward would operationally rely on undocumented provider reuse semantics. The implementation now fails closed when a refresh response omits the replacement refresh token.
2. **Revoke/logout overclaim:** the contract now describes a bounded single-token revoke plus local delete rather than complete provider logout/token-family invalidation.
3. **Invalid-input ordering regression:** bookmarks/likes local argument validation now runs before lifecycle credential resolution, preventing an invalid command from triggering a refresh request.
4. **Real DPAPI evidence gap:** L2 review found that prior tests used injected fake protect/unprotect functions and therefore did not exercise the actual Windows `CryptProtectData` / `CryptUnprotectData` ctypes boundary. Commit `70c228de88357e53f173549a960247b559ed9f28` adds a Windows-only synthetic integration test for this boundary; non-Windows CI skips it by design.

Ready / merge remain blocked until the new Windows-only DPAPI test is executed successfully at the exact final PR head and the L2 review is closed with no remaining blocker.

## Validation state

Evidence already completed on pre-DPAPI-test head `19763b6e7f7d099f34ac4997ae424f6906808a7d`:

- Windows PowerShell exact-head validation PASS;
- 162 tests passed;
- `git diff --check origin/main...HEAD` passed;
- detached validation worktree stayed clean and was removed normally;
- canonical `main` returned clean and synchronized to `origin/main`;
- durable UTF-8 evidence log: `logs/verification/issue-32-final-exact-head-20260917-212445.log`;
- hosted `project-ci` and `policy-check` passed.

Additional test commit `70c228de88357e53f173549a960247b559ed9f28`:

- hosted `project-ci`: PASS;
- hosted `policy-check`: PASS;
- the real-DPAPI integration test is skipped on non-Windows by design and therefore still requires a Windows exact-head run before Ready consideration.

Later documentation commits update CHANGELOG, PROJECT_STATUS, and TEST_MATRIX traceability, so final Ready consideration requires a new validation log whose tested SHA equals the exact PR head shown by GitHub at that time.

## Authority and safety boundaries

- Official X APIs are the only supported provider boundary.
- No scraping, browser-cookie reuse, unofficial/internal GraphQL fallback, OAuth 1.0a fallback, write scope, or client secret is introduced.
- Actual credentials and private X payloads must not enter the repository, Issues/PRs, CI artifacts, normal logs, or retained validation evidence.
- DPAPI protection is an at-rest/current-user boundary, not isolation from every process running as that same user.
- Corrupt/unreadable/unsupported credential state fails closed and is not auto-deleted.
- Real provider refresh/revoke qualification is separate from synthetic contract tests and remains human-gated.
- Ready and merge are separate human-final gates.

## Recovery / first diagnostic entry points

- Workstream: GitHub Issue #32 and Draft PR #33.
- Requirement and acceptance contract: `docs/specs/0003-credential-lifecycle.md`.
- Storage decision: `docs/adr/0005-dpapi-credential-storage.md`.
- Traceability: `docs/TEST_MATRIX.md`.
- Lifecycle implementation: `x_context/credential_lifecycle.py`.
- Collection integration: `x_context/cli.py`.
- Synthetic lifecycle tests: `tests/test_credential_lifecycle.py` and `tests/test_credential_lifecycle_cli_ordering.py`.
- Real Windows DPAPI boundary test: `tests/test_credential_lifecycle_windows_dpapi.py`.
- Authoritative local validator: `scripts/Invoke-XContextValidation.ps1`.
- Preserve unaccounted local work and fail closed on uncertain credential state, private-data exposure, destructive cleanup, or provider authority.