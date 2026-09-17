# SPEC-0004 — End-user OAuth bootstrap CLI

- **Status:** Proposed implementation clarification
- **Date recorded:** 2026-09-17
- **Related:** SPEC-0000, SPEC-0002, SPEC-0003, Issue #36
- **Base:** `4f0bd3151d737b5ea40cb1891ca0a97fa3fa1efc`

## Purpose

Define the smallest end-user command that makes the already-implemented P0 personal-collection path usable without manually injecting an access token or calling Python library APIs directly.

This slice composes the existing OAuth 2.0 Authorization Code + PKCE acquisition boundary with the existing DPAPI-backed credential lifecycle. It does not add a new X data capability or broaden product authority.

## Current provider facts

Re-verified against X documentation on 2026-09-17:

- OAuth 2.0 Authorization Code with PKCE remains supported for X API v2.
- Native Apps are public clients and must not rely on a client secret.
- `offline.access` is the documented scope that causes X to issue a refresh token.
- current P0 read scopes remain `tweet.read`, `users.read`, `bookmark.read`, and `like.read`.
- callback URLs require exact-match configuration in the X App.
- provider token lifetimes, response details, pricing, and refresh semantics remain external facts rather than product constants.

Authoritative provider references:

- <https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code>
- <https://docs.x.com/x-api/getting-started/about-x-api>

## Command contract

The first end-user bootstrap command is:

```text
python -m x_context auth login
```

No token, authorization code, verifier, state, client secret, or scope override is accepted as a command-line argument.

A successful invocation means only that one lifecycle-managed credential was acquired and committed to the configured local lifecycle store. It does not read X content and does not claim a broader provider login/session guarantee.

## Configuration contract

The command requires these non-secret local configuration values:

- `X_CONTEXT_OAUTH_CLIENT_ID` — existing public Client ID configuration;
- `X_CONTEXT_OAUTH_REDIRECT_URI` — exact registered loopback redirect URI.

The redirect URI must continue to satisfy SPEC-0002:

```text
http://127.0.0.1:<fixed-registered-port>/<fixed-callback-path>
```

The command must not silently substitute `localhost`, select a different port, alter the callback path, or otherwise repair an invalid redirect URI.

The default managed credential store remains the SPEC-0003 Windows DPAPI `CurrentUser` store. Unsupported platforms or unavailable default-store configuration fail closed; no plaintext fallback is introduced.

## Requested authority

`auth login` always requests a refresh-capable managed credential because persistence for later bounded collection reads is the purpose of this command.

The authorization request scope set is exactly:

- `tweet.read`
- `users.read`
- `bookmark.read`
- `like.read`
- `offline.access`

No write, DM, follows, list, mute, block, or other additional scope is accepted or inferred.

Invoking `auth login` is the user's explicit request for this managed persistent credential. The command does not silently upgrade an unrelated one-shot OAuth acquisition.

## Composition boundary

The command reuses the existing implementation boundaries rather than duplicating them:

1. build `OAuthConfig` from the two required non-secret configuration values;
2. call `acquire_user_token(..., refresh_capable=True)`;
3. perform bootstrap-specific pre-commit validation described below;
4. call `persist_oauth_result(...)` with the existing lifecycle store;
5. emit only safe status/diagnostic output.

The CLI must not implement its own PKCE, callback parsing, token exchange, DPAPI, credential serialization, refresh, or atomic replacement logic.

## Bootstrap pre-commit validation

A token result suitable for this managed bootstrap must contain enough information for the already-defined lifecycle policy to operate safely.

Before persistence, `auth login` therefore requires:

- a refresh token to be present;
- a positive provider expiry duration to be present;
- any returned granted-scope set to remain accepted by the existing OAuth normalization boundary.

If `offline.access` was requested but the normalized result lacks a refresh token or expiry duration, the command fails closed and does not persist the result. It must not fabricate a refresh token, infer a fixed provider lifetime, or silently downgrade the managed credential to a non-refreshable token.

This validation does not change the more general SPEC-0002 acquisition result contract, which may represent optional provider fields for library callers.

## Existing credential preservation

A failed bootstrap must not destroy or partially replace a previously committed credential.

- configuration failure: no acquisition or store mutation;
- listener/browser/callback/token-exchange failure: no store mutation;
- bootstrap pre-commit validation failure: no store mutation;
- persistence failure before atomic replacement: previous committed credential remains authoritative;
- successful persistence: the complete protected envelope is atomically replaced using the existing SPEC-0003 store contract.

`X_CONTEXT_USER_ACCESS_TOKEN` remains an unmanaged per-operation compatibility/recovery override. `auth login` must never import, persist, refresh, or otherwise transform that environment value.

## Output and diagnostic boundary

On success, stdout contains one small JSON status object with no credential material. It may report only bounded facts such as:

- `operation = "auth_login"`;
- success status;
- `credential_persisted = true`;
- `refresh_capable = true`.

On handled failure, stdout is empty and stderr contains one stable JSON diagnostic with a non-secret error category and only allow-listed effect metadata.

Controlled stdout, stderr, exception text, callback response pages, durable validation logs, and committed fixtures must not contain:

- access token;
- refresh token;
- authorization code;
- PKCE verifier;
- OAuth state;
- full callback query string;
- raw token response;
- Authorization header material;
- protected credential bytes.

Provider/transport exception prose remains untrusted and must not be passed through verbatim.

## Bounded effects

One invocation may perform at most:

- one loopback listener bind;
- one browser launch;
- one terminal callback acceptance;
- one authorization-code token exchange;
- one lifecycle credential replacement after successful validation.

It performs zero X content reads and zero X content/relationship mutations.

There is no automatic retry, browser relaunch, alternate redirect URI, plaintext persistence fallback, or token import fallback.

## Acceptance criteria

1. `auth login` with missing/invalid Client ID or redirect URI exits locally before browser launch and before store mutation.
2. Valid execution composes `OAuthConfig`, `acquire_user_token(..., refresh_capable=True)`, bootstrap pre-commit validation, and `persist_oauth_result(...)`.
3. The requested scopes are exactly the four accepted P0 read scopes plus `offline.access`.
4. A normalized result without a refresh token is not persisted.
5. A normalized result without a positive expiry duration is not persisted.
6. Acquisition or validation failure leaves any pre-existing credential unchanged.
7. Successful persistence uses the existing DPAPI whole-record atomic replacement path.
8. `X_CONTEXT_USER_ACCESS_TOKEN` is never imported into managed storage.
9. Successful output and all handled-error diagnostics exclude secret-bearing values.
10. Unsupported default-store environments fail closed with no plaintext fallback.
11. After successful synthetic login, existing `bookmarks` / `likes` resolution can consume the persisted credential without `X_CONTEXT_USER_ACCESS_TOKEN`.
12. No provider revoke, local credential delete/status command, packaging work, P1 endpoint, or broader scope is introduced.

## Test plan before implementation

Tests are written before product-code changes and cover at least:

- parser/dispatch for `auth login`;
- invalid/missing Client ID -> zero acquisition/store effects;
- invalid/missing redirect URI -> zero acquisition/store effects;
- successful fake acquisition -> exactly one persistence path;
- acquisition invoked with `refresh_capable=True`;
- requested scope set remains the accepted P0 set plus `offline.access`;
- missing refresh token -> no persistence;
- missing expiry duration -> no persistence;
- acquisition failure -> no persistence and existing credential preserved;
- persistence failure -> safe error and previous committed credential preserved by the store contract;
- unmanaged environment access-token override is ignored by login and never imported;
- stdout/stderr secret-sentinel redaction;
- unsupported default store -> fail closed;
- synthetic post-login `bookmarks` / `likes` credential resolution through the persisted lifecycle store.

## Human gates and real-provider qualification

Ready and merge remain human-final.

Real-provider authorization qualification is an explicit human decision. Synthetic tests must not require real credentials, private X payloads, browser cookies, live callback secrets, or CI-stored user tokens.

## Out of scope

- `auth status` or credential inspection UX;
- local delete/logout CLI;
- provider revoke CLI or complete-logout/token-family claims;
- package installer or installed console script;
- P1 own posts, mentions, follows, lists, blocks, or mutes;
- changes to the credential envelope, DPAPI choice, refresh-before-use policy, or provider revoke semantics.

## Work order

This slice follows:

**Requirement -> Acceptance Criteria -> Tests -> Implementation**

This specification and Issue #36 establish the Requirement/AC boundary. Tests are the next repository change; implementation follows only after the test contract is present.