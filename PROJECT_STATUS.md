# Project Status

## 30-second state

- **Goal:** Read-only official X API context reader with safe native OAuth user-token acquisition.
- **Current work:** Issue #23, OAuth 2.0 Authorization Code + PKCE user-token acquisition, on `issue-23-oauth-acquisition`.
- **Starting main:** `328aa09f8448630c3798810489d66e838ea4dccb` (PR #22 merge).
- **Last validated implementation head:** `f1205d11625cfa4d15d318067b5615292abe6c62`; authoritative validation passed 139 tests plus diff/workspace/final-state checks before this documentation-only closeout.
- **Completed dependencies:** FR-001/002/003/004/005/006 and authenticated-subject binding are on main.
- **Human decision:** No PR / Ready / merge transition is authorized. Ready / merge remain human-final.
- **Qualification:** No live OAuth, real user token, browser authorization, or private collection read has been performed in Issue #23.

## Issue #23 scope

This workstream adds only the native/public-client OAuth acquisition ceremony:

1. fixed registered IPv4 loopback callback using `http://127.0.0.1:<port>/<path>`;
2. fresh state and PKCE verifier per attempt;
3. S256 challenge only;
4. external system-browser launch after successful listener bind;
5. bounded one-callback handling and exact state/path validation;
6. one official authorization-code token exchange;
7. secret-bearing token result held in memory only.

Secure persistence, automatic refresh, refresh-token rotation assumptions, Windows Credential Manager / DPAPI integration, revoke/logout, and migration away from the existing `X_CONTEXT_USER_ACCESS_TOKEN` collection source remain out of scope.

## Verified external facts

Current X official documentation was re-verified on 2026-09-14 before implementation:

- Native App is a public client and uses PKCE rather than a client secret.
- authorize endpoint is `https://x.com/i/oauth2/authorize`.
- token endpoint is `POST https://api.x.com/2/oauth2/token`.
- callback URLs require exact registration match.
- local callback guidance uses `http://127.0.0.1`, not `localhost`.
- provider supports S256/plain PKCE; product requires S256 only.
- default access-token lifetime is currently documented as two hours.
- `offline.access` causes issuance of a refresh token; without it refresh capability is not established.
- read scope set for current MVP is `tweet.read users.read bookmark.read like.read`, with optional explicit `offline.access`.

Refresh-token rotation/reuse behavior is not sufficiently explicit in current provider documentation and is deliberately not encoded by Issue #23.

## Requirement -> AC -> Test state

Normative clarification:

- `docs/specs/0002-oauth-acquisition-clarification.md`

Canonical traceability:

- `docs/TEST_MATRIX.md`

Contract/security tests:

- `tests/test_oauth_acquisition.py`
- `tests/test_oauth_acquisition_security.py`

OAuth acceptance criteria are integrated into the canonical TEST_MATRIX using the concrete test names from the validated implementation. The temporary OAuth-only mapping file used while the connected write path was blocked is removed during this closeout so traceability has one canonical source.

## Implementation state

New module:

- `x_context/oauth.py`

Current design boundaries:

- `OAuthConfig` accepts non-secret public-client configuration only.
- redirect configuration is constrained to fixed `http://127.0.0.1:<port>/<non-root-path>` with no query/fragment/userinfo.
- `build_authorization_attempt()` generates fresh state/verifier and exact read scopes, adding `offline.access` only when explicitly requested.
- `exchange_callback()` validates callback destination/state/code before one token POST and marks a validated attempt terminal before transport.
- token request carries `client_id` in the form body and no client secret/Basic authorization.
- a provider-returned refresh token is rejected unless refresh-capable acquisition explicitly requested `offline.access`; no unexpected refresh authority is accepted.
- `OAuthTokenResult`, HTTP request/response bodies, state, verifier, and token values are repr-redacted where represented by project objects.
- provider/transport exceptions are normalized without verbatim exception chaining.
- `LoopbackCallbackListener` binds only `127.0.0.1` and suppresses default HTTP request logging so callback query strings are not logged.
- `acquire_user_token()` binds the listener before browser launch and has no automatic browser/token retry loop.
- no persistence/environment/clipboard behavior is introduced.

## Security boundary

The following values must not enter stdout/stderr, durable validation logs, callback response pages, normal repr/debug strings, or controlled traceback chaining:

- access token;
- refresh token;
- authorization code;
- state;
- PKCE verifier;
- Authorization header material;
- raw token response;
- full callback query.

Tests use fake secret-shaped values only. Real OAuth qualification remains human-gated until automated exact-head validation and independent review are complete.

## Validation state

GitHub is the source of truth for committed/shared state. Authoritative Windows exact-head validation on implementation head `f1205d11625cfa4d15d318067b5615292abe6c62` completed successfully on 2026-09-14:

- 139/139 tests passed;
- `git diff --check` passed;
- expected/origin/actual topic heads matched exactly;
- verification worktree was clean and removed normally;
- canonical `main` remained clean and synchronized with `origin/main`;
- durable evidence: `logs/verification/issue-23-oauth-callback-remediation-20260914-093122.log`.

This documentation closeout moves the topic head without changing product behavior. Required remaining sequence:

1. review the final documentation-only diff and canonical TEST_MATRIX integration;
2. run authoritative exact-head validation again on the final documentation head;
3. perform independent L2/adversarial review on that exact head;
4. only then consider an intentional real OAuth qualification and Draft PR.

No live credential may be placed into tests, Issue/PR text, chat logs, or retained validation evidence.
