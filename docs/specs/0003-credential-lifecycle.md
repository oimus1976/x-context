# SPEC-0003 — Credential lifecycle

- **Status:** Proposed implementation clarification
- **Date recorded:** 2026-09-16
- **Related:** SPEC-0002, ADR-0004, ADR-0005, Issue #32

## Purpose

Define the secure lifecycle for OAuth 2.0 user-context credentials after acquisition: explicit persistence, runtime resolution, refresh-before-use, atomic replacement, local deletion, provider-side revoke, recovery, and collection integration.

This specification does not expand x-context authority. The product remains read-only and official-X-only.

## Verified provider boundary

Re-verified against current X documentation on 2026-09-16:

- `offline.access` causes a refresh token to be issued; omitting it does not establish refresh capability.
- Public-client refresh uses `POST https://api.x.com/2/oauth2/token` with `application/x-www-form-urlencoded`, `grant_type=refresh_token`, `refresh_token`, and `client_id`.
- Provider-side revoke uses `POST https://api.x.com/2/oauth2/revoke` with `application/x-www-form-urlencoded`, `token`, and `client_id` for a public client.
- X documents revoke as invalidating an access token or refresh token and as supporting a client logout feature.

Current X documentation does not establish a sufficiently explicit contract for x-context to assume refresh-token rotation, reuse, one-time-use, immediate invalidation of the previous refresh token, or token-family-wide invalidation after revoking one token.

These provider behaviors remain external facts rather than immutable product constants.

## Authority boundary

Lifecycle-managed credentials may contain only the authority granted by the accepted product scope:

- `tweet.read`
- `users.read`
- `bookmark.read`
- `like.read`
- optional `offline.access` only when refresh capability was explicitly requested.

No write scope, OAuth 1.0a fallback, browser-cookie reuse, scraping fallback, unofficial endpoint, app-only bearer fallback, or client secret is introduced.

## Storage decision

ADR-0005 selects a versioned credential envelope protected with Windows DPAPI `CurrentUser` and stored as one local per-user file.

The whole serialized envelope is protected before durable storage. Durable plaintext token material is forbidden.

A storage interface separates lifecycle policy from the concrete Windows backend so automated tests use deterministic fakes.

## Persisted schema

Schema version 1 contains only fields needed for lifecycle decisions:

- `schema_version`: integer `1`;
- `provider`: exact string `x`;
- `access_token`: required secret string;
- `refresh_token`: optional secret string;
- `token_type`: optional safe string;
- `expires_at`: optional integer UTC Unix timestamp;
- `scopes`: optional normalized unique list of granted scope names.

Raw provider responses, authorization codes, callback URLs, PKCE verifier/state, request headers, client secrets, and arbitrary provider metadata are not persisted.

`expires_at` is derived locally when persistence/refresh receives a valid positive `expires_in`; provider-relative lifetime values are not treated as permanent product constants.

The first lifecycle slice does not persist authenticated-subject identity. Existing `/2/users/me` resolution and same-subject binding remain mandatory for collection reads and therefore continue to prevent credential/target mismatch.

## Explicit persistence

OAuth acquisition remains in-memory by default. Acquisition alone must not write a credential.

Persistence occurs only through an explicit lifecycle operation that accepts a normalized OAuth token result and commits it to the configured store.

Environment-provided credentials are never copied into lifecycle storage automatically.

## Credential source resolution

For backwards compatibility and recovery, `X_CONTEXT_USER_ACCESS_TOKEN` remains an explicit environment override.

Resolution order for bookmarks/likes is:

1. if `X_CONTEXT_USER_ACCESS_TOKEN` is present, validate and use that value for the current operation only;
2. otherwise resolve the lifecycle-managed persisted credential;
3. never fall back to `X_CONTEXT_BEARER_TOKEN` as user authority.

If the environment override is present but malformed/unsafe, fail closed. Do not silently ignore it and fall back to persisted state.

Environment credentials are unmanaged for lifecycle purposes: x-context must not refresh, persist, replace, or revoke them automatically.

For CLI collection execution, the public OAuth Client ID needed only when a persisted credential must be refreshed is read from `X_CONTEXT_OAUTH_CLIENT_ID`. It is non-secret configuration. Its absence does not block use of a persisted access token that is not due for refresh, but a due/expired refresh-capable credential fails locally if the Client ID is unavailable or unsafe.

## Expiry and refresh-before-use policy

Lifecycle code uses an injectable UTC clock.

For a persisted credential:

- if `expires_at` is absent, the access token may be used without proactive refresh; expiry is not fabricated;
- if `expires_at` is present and more than 300 seconds in the future, use the current access token;
- if `expires_at` is within 300 seconds and a refresh token exists, attempt one refresh before use;
- if `expires_at` is within 300 seconds but no refresh token exists and the token is still unexpired, use the current token until actual expiry;
- if the token is expired and no refresh token exists, fail locally without collection transport;
- if the token is expired and a refresh token exists, attempt one refresh before use.

The 300-second refresh window is a product safety/skew policy, not a provider lifetime assumption.

One resolution invocation performs at most one refresh request.

## Refresh request contract

Refresh uses only the official token endpoint:

`POST https://api.x.com/2/oauth2/token`

The public-client form body contains exactly the lifecycle-required values:

- `grant_type=refresh_token`;
- current persisted `refresh_token`;
- configured `client_id`.

No client secret or Basic authentication is used.

Unexpected redirects are not an authorization mechanism and fail closed.

Transport/provider exception text is not trusted and is never passed through verbatim.

## Refresh success and replacement

A successful refresh response must contain a safe non-empty access token. Optional token type, positive expiry metadata, granted scopes, and optional refresh token are normalized conservatively.

The response is treated as new provider-controlled credential material.

Because X does not document a stable rotation/reuse contract, x-context does not test or reuse the old refresh token after success.

Replacement rule:

- if the successful response contains a refresh token, persist that returned refresh token;
- if the successful response omits a refresh token, retain the previously persisted refresh token for the new envelope rather than guessing that refresh capability was revoked;
- replace access token and any newly supplied lifecycle metadata with the successful response values;
- preserve only metadata whose carry-forward semantics are explicitly defined here;
- commit the complete new envelope atomically.

This omission rule is an x-context storage rule, not a claim about provider rotation/reuse behavior. A later provider clarification may revise it through a new specification change.

The refreshed access token must not be returned to a collection caller until the replacement commit succeeds. This prevents runtime use of credential state that was not durably committed.

## Refresh failure

A failed transport, non-success provider response, malformed success response, scope expansion, or persistence replacement failure does not intentionally destroy the last committed credential state.

When refresh was triggered only by the 300-second safety window and the old access token is still unexpired, x-context **still fails the current resolution** rather than proceeding after a failed refresh attempt. This keeps behavior deterministic and avoids silently consuming a token the policy already judged due for refresh.

When refresh was required because the access token was expired, failure also stops before collection transport.

No automatic second refresh, alternate token, OAuth flow, or env fallback is attempted.

## Scope validation on refresh

If the provider returns granted scopes, the set must equal the stored expected scope set for the lifecycle-managed credential. Silent authority expansion or contraction fails closed.

A refresh response does not authorize new scopes merely because X can return them.

If the provider omits scope metadata, the previously persisted scope set may be retained because the refresh request itself did not request new authority.

## Atomic storage contract

The concrete DPAPI backend encrypts the complete schema envelope first, then writes a temporary file in the target directory and replaces the target atomically.

The implementation must not truncate the committed target before the replacement blob is ready.

Injected failure before final replacement must leave the prior committed credential readable.

A missing target is `credential_missing`. A decrypt failure, unsupported schema, invalid JSON/schema content, unsafe token field, or partial/corrupt protected blob is a fail-closed `credential_storage_error`.

Stable lifecycle error categories may be mapped by the CLI to existing local/provider exit-code classes; callers must not parse OS/provider prose.

## Concurrency boundary

The first lifecycle slice is single-process/single-writer by contract. It does not claim cross-process locking or compare-and-swap semantics.

Atomic file replacement prevents partial durable state, but concurrent independent writers are outside this slice and must not be described as safely serialized.

A future need for concurrent writers requires a separate design change.

## Local delete/logout

Local deletion removes only lifecycle-managed persisted credential state.

It is idempotent: deleting an already-missing local credential succeeds as a no-op.

Local deletion does not claim provider-side invalidation and must not be labeled `revoke`.

Environment credentials are not modified by local deletion.

## Provider revoke/logout

Provider revoke is a distinct explicit operation and remains human-gated for real-account qualification.

It uses only:

`POST https://api.x.com/2/oauth2/revoke`

For a lifecycle-managed refresh-capable credential, x-context revokes the **refresh token** when one is present because that is the credential that enables future access-token renewal. If no refresh token exists, it revokes the access token.

This choice does not assume that revoking one token invalidates every token in a provider token family.

Provider revoke and local deletion are ordered as:

1. load the lifecycle-managed credential;
2. perform at most one provider revoke request;
3. only after provider revoke succeeds, delete the local lifecycle-managed credential.

If provider revoke fails, local state is retained so the user can retry or explicitly choose local-only deletion.

If provider revoke succeeds but local deletion fails, report a safe local storage error and retain no claim that local logout completed; a subsequent local-only delete may recover the machine state.

Provider success must not cause raw token/provider response logging.

## Recovery behavior

- missing persisted credential: fail locally unless an explicit env override exists;
- unsupported/corrupt schema or DPAPI failure: fail closed; do not auto-delete;
- expired token without refresh capability: fail locally and require re-authorization or explicit env override;
- provider rejects refresh/revoke: retain local state unless the explicit operation contract says otherwise;
- machine/profile migration that makes DPAPI data unreadable: re-authorization or explicit local deletion is the recovery path.

No recovery path prints or exports secret material to plaintext, clipboard, stdout, stderr, validation logs, or committed evidence.

## Secret and diagnostic boundary

The following must not appear in normal stdout, stderr, normal exception strings/chaining controlled by this slice, repr/debug strings, durable validation logs, committed fixtures, or retained evidence:

- access token;
- refresh token;
- DPAPI plaintext envelope;
- authorization code;
- PKCE verifier/state;
- Authorization headers;
- raw token/revoke responses;
- raw protected-blob bytes where retaining them would create unnecessary credential material.

Safe diagnostics may contain operation name, source kind (`environment` or `persisted`), stable category, refresh attempted boolean, revoke attempted boolean, credential present boolean, expiry-known boolean, and non-secret scope names.

## Acceptance criteria

### AC-CRED-01 — DPAPI protected persistence

An explicitly committed lifecycle credential round-trips through the storage interface; the durable concrete Windows representation contains only a DPAPI-protected envelope and no plaintext token material.

### AC-CRED-02 — acquisition remains non-persistent by default

Calling the existing OAuth acquisition boundary alone does not create or modify lifecycle storage.

### AC-CRED-03 — deterministic source resolution

A present valid `X_CONTEXT_USER_ACCESS_TOKEN` is the explicit per-operation override; persisted state is used only when that variable is absent. A present invalid env value fails closed without persisted fallback.

### AC-CRED-04 — no app-only fallback or auto-import

`X_CONTEXT_BEARER_TOKEN` is never used for bookmarks/likes user authority, and environment user tokens are never automatically persisted, refreshed, replaced, or revoked.

### AC-CRED-05 — expiry policy

Known expiry uses the 300-second safety window exactly as specified; unknown expiry is not fabricated. Expired credentials without a refresh token fail before collection transport.

### AC-CRED-06 — bounded official refresh

One credential resolution performs at most one official public-client refresh request and never uses a client secret, Basic auth, alternate OAuth flow, redirect fallback, or retry loop.

### AC-CRED-07 — conservative refresh normalization

Malformed successful refresh responses, unsafe secret fields, invalid expiry metadata, or returned scope mismatch fail closed without replacing committed state.

### AC-CRED-08 — atomic successful replacement

A valid refresh result is converted into one complete new envelope and durably replaced atomically before its access token is returned for use.

### AC-CRED-09 — refresh-token omission/rotation neutrality

A returned refresh token replaces the old one. If a successful refresh omits a refresh token, the old refresh token is retained by explicit product rule. No test or implementation claims that the old provider token is reusable after a response that replaced it.

### AC-CRED-10 — failed refresh preserves committed state

Transport/provider/normalization/storage failures do not intentionally destroy or partially overwrite the last committed credential, and the current collection operation does not continue with the old token after a refresh attempt fails.

### AC-CRED-11 — authenticated subject boundary preserved

After env resolution or persisted load/refresh, bookmarks/likes still perform the existing authenticated-subject resolution and same-subject binding before collection retrieval.

### AC-CRED-12 — local delete semantics

Local lifecycle deletion is idempotent, affects only persisted lifecycle state, does not modify environment variables, and does not claim provider revocation.

### AC-CRED-13 — official revoke semantics

Explicit provider revoke uses only `POST https://api.x.com/2/oauth2/revoke` with the public-client form contract. It chooses refresh token when present, otherwise access token, performs at most one revoke request, and deletes local state only after provider success.

### AC-CRED-14 — recovery and corruption fail closed

Missing, unreadable, corrupt, unsupported-version, or unsafe persisted state produces stable non-secret lifecycle errors without auto-deleting or exporting credential material.

### AC-CRED-15 — secret redaction

Credential values, DPAPI plaintext, raw provider responses, protected-blob bytes, and transport exception text never enter normal diagnostics, repr/debug strings, controlled traceback chaining, fixtures, or retained validation evidence.

### AC-CRED-16 — authority remains read-only

Stored/refreshed scopes never expand beyond `tweet.read`, `users.read`, `bookmark.read`, `like.read`, plus explicitly acquired `offline.access`; no write authority or client secret is introduced.

### AC-CRED-17 — concurrency claim remains bounded

Tests prove atomic replacement and single-process behavior only. Documentation and implementation make no unsupported claim that concurrent writers are serialized.

### AC-CRED-18 — regression

The full existing test suite passes, including OAuth acquisition, authenticated-subject binding, bookmarks/likes, app-only read, secret-redaction, and public-policy regressions.

## Test boundary

Automated tests use fake token values, fake clocks, fake lifecycle storage, fake DPAPI protection where appropriate, and fake OAuth transport. No live credential is required.

Concrete DPAPI integration tests may run only on Windows and must use synthetic credentials and temporary paths. They must delete their test state and never commit generated protected blobs.

Any real provider refresh/revoke qualification remains an explicit human decision. Retained evidence records only non-secret facts such as endpoint class, success boolean, refresh-token-present boolean, and scope names.
