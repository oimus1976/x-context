# SPEC-0002 — OAuth user-token acquisition clarification

- **Status:** Proposed implementation clarification
- **Date recorded:** 2026-09-14
- **Related:** SPEC-0001, ADR-0004, Issue #23

## Purpose

Define the first native/desktop OAuth acquisition slice that can obtain X OAuth 2.0 user-context credentials for the existing authenticated collection boundary without yet introducing credential persistence or automatic refresh behavior.

This specification narrows Issue #23 into a testable protocol and security contract. It does not replace the existing `X_CONTEXT_USER_ACCESS_TOKEN` runtime source used by `bookmarks` and `likes`; migration to a secure persistent credential provider belongs to a later lifecycle workstream.

## Verified provider boundary

As re-verified against current X documentation on 2026-09-14:

- X API v2 user authorization supports OAuth 2.0 Authorization Code with PKCE.
- Native App is a public client and cannot safely hold a client secret.
- Public-client token requests include `client_id` in the form body.
- authorization endpoint: `https://x.com/i/oauth2/authorize`.
- token endpoint: `POST https://api.x.com/2/oauth2/token`.
- token exchange uses `application/x-www-form-urlencoded`.
- redirect URI must exactly match an allowed callback URL configured for the App.
- X currently directs local development to `http://127.0.0.1`, not `localhost`.
- authorization requests carry `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`, `code_challenge`, and `code_challenge_method`.
- X currently accepts PKCE `S256` and `plain`; x-context requires `S256` only.
- authorization codes are currently documented as short-lived and must be exchanged promptly.
- access tokens issued through this flow are currently documented as valid for two hours unless `offline.access` is requested.
- requesting `offline.access` causes a refresh token to be issued; omitting it does not establish refresh capability.

Provider lifetimes and refresh semantics are external facts. They may be observed and validated for interoperability but must not be treated as immutable product constants.

## Product scope and authority

The acquisition slice requests only the read scopes needed by the accepted MVP:

- `tweet.read`
- `users.read`
- `bookmark.read`
- `like.read`

`offline.access` is optional and is requested only when the caller explicitly asks for refresh-capable acquisition.

No write scope is requested. Broader scopes available from X do not expand x-context product authority.

The acquisition slice exposes no mutation command and performs no collection read as part of the OAuth ceremony.

## Native/public-client contract

x-context treats the X Native App configuration as a public client.

The implementation must therefore:

- require a Client ID;
- never require, load, log, transmit, or persist a client secret;
- use PKCE for every authorization attempt;
- use only the external system browser for user authorization;
- keep the browser boundary separate from callback and token transport logic so tests can use fakes without a real browser.

Embedded web views, browser automation, browser-cookie reuse, and unofficial authentication paths are forbidden.

## PKCE contract

Each authorization attempt generates a fresh cryptographically random `code_verifier`.

The corresponding challenge is:

1. SHA-256 over the verifier bytes;
2. base64url encoding of the digest;
3. padding removed;
4. authorization request includes `code_challenge_method=S256`.

`plain` must never be emitted as a fallback. Failure to generate a valid verifier/challenge is a local terminal failure before browser launch.

The verifier is secret material for the active ceremony and must not enter normal diagnostics, exception text controlled by this slice, durable validation logs, repr/debug strings, or committed fixtures.

## State / CSRF contract

Each authorization attempt generates a fresh cryptographically random `state` value independent of the PKCE verifier.

The active attempt accepts only a callback carrying the exact expected state. Missing state, duplicate state parameters, malformed state, or any unequal value fails closed before token exchange.

`state` is treated as sensitive ceremony material and must not be emitted in normal diagnostics, callback response pages, durable logs, repr/debug strings, or controlled traceback chaining.

## Redirect URI and loopback listener

The configured redirect URI has the form:

`http://127.0.0.1:<fixed-registered-port>/<fixed-callback-path>`

The following invariants apply:

- bind only IPv4 loopback `127.0.0.1`;
- do not bind `0.0.0.0`, a LAN address, IPv6 wildcard, or `localhost` hostname;
- the authorize request and token exchange use the exact same configured redirect URI;
- the redirect URI must match the callback URL registered with X;
- this slice does not assume dynamic-port registration semantics;
- if the configured port cannot be bound, fail locally before browser launch rather than select another port or redirect URI;
- listener lifetime is bounded to one active authorization attempt;
- only the configured callback path is eligible to terminate the attempt;
- unrelated paths do not expose secret query data and do not cause token exchange.

## Browser launch ordering

The callback listener must successfully bind before the system browser is launched.

This ordering prevents a user from completing authorization for a redirect URI that the process cannot receive.

The implementation launches at most one browser authorization URL per acquisition invocation. There is no automatic relaunch or retry loop after a terminal failure.

## Callback handling

A valid callback may contain either an authorization success or an OAuth provider error.

For a success callback:

- exactly one usable authorization `code` is required;
- exact expected `state` is required;
- callback path must exactly match the configured path;
- token exchange is attempted at most once.

For provider-denied/error callbacks, malformed callbacks, wrong path, missing/duplicate code, missing/wrong/duplicate state, timeout, or callbacks arriving after terminal completion, fail closed without accepting credential material.

The full callback query string and authorization code are sensitive and must not be logged or reflected in the browser response page.

A callback response page may contain a generic local success/failure message only; it must not include the code, state, token response, verifier, or private X data.

## Token exchange contract

The authorization code is exchanged only with:

`POST https://api.x.com/2/oauth2/token`

The request uses `application/x-www-form-urlencoded` and includes the values required for a public-client authorization-code exchange:

- `grant_type=authorization_code`;
- authorization `code`;
- exact configured `redirect_uri`;
- `client_id`;
- original `code_verifier`.

This slice does not use HTTP Basic client-secret authentication and does not send a client secret.

Redirect following is not an authorization mechanism. Unexpected redirects or an unexpected token endpoint destination fail closed.

## Token-result boundary

A successful provider token response is normalized into an in-memory secret-bearing result object.

The minimum result may contain:

- required access token;
- token type when safely present;
- provider expiry metadata when safely present and valid;
- granted scope information when safely present and valid;
- optional refresh token only when the provider returns one.

The result object itself is sensitive. Its normal `repr` / diagnostic representation must redact credential values.

Malformed or contradictory successful responses fail closed. At minimum, missing/empty/unsafe access token material is not accepted. A refresh token is never fabricated merely because `offline.access` was requested.

Whether a returned granted-scope set is sufficient for later operations must be representable without logging token material. Scope validation must not silently add authority beyond the requested set.

## Refresh-capable acquisition boundary

When refresh capability is explicitly requested, the authorization request includes `offline.access` in addition to the four read scopes.

When refresh capability is not requested, `offline.access` is omitted and x-context must not claim that a refresh token is available.

The provider may still return unexpected or malformed token fields; product behavior remains fail-closed rather than assuming undocumented semantics.

This specification does not define refresh-token rotation, reuse, storage, replacement, or automatic refresh behavior. Current X documentation shows how to submit a refresh token but does not establish a sufficiently explicit rotation/reuse contract for x-context to encode one safely.

## Secret and diagnostic boundary

The following must not appear in normal stdout, stderr, durable validation logs, normal exception text/chaining controlled by this slice, repr/debug strings, committed fixtures, or callback response pages:

- access token;
- refresh token;
- authorization code;
- PKCE `code_verifier`;
- `state`;
- Authorization header material;
- raw provider token response;
- full callback query string.

Safe diagnostics may include only non-secret facts needed for troubleshooting, such as:

- operation name;
- stable error category;
- browser launch attempted boolean;
- callback received boolean;
- token exchange attempted boolean;
- refresh token present boolean;
- selected scope names;
- configured loopback host/port/path when that configuration itself is not sensitive;
- safe HTTP status class or allow-listed metadata.

Transport exception text is not trusted and must not be passed through verbatim when it may contain request/response values.

## Failure behavior

Local configuration or construction failures occur before browser launch where possible. Provider or transport failures remain conservative.

The slice must distinguish at least:

- invalid local OAuth configuration / unsafe Client ID or redirect configuration;
- loopback bind failure;
- browser-launch failure;
- callback timeout or invalid callback;
- state mismatch;
- provider authorization denial;
- token endpoint authentication/authorization/provider failure when safely distinguishable;
- malformed successful token response;
- conservative provider/transport failure.

Exact stable category names may reuse existing categories where semantics fit or add the smallest OAuth-specific categories necessary before implementation. Tests must not require parsing raw provider prose.

## Bounded effects

One acquisition invocation has these maximum intended side effects:

- one loopback listener bind;
- one external browser launch;
- one terminal callback acceptance;
- one authorization-code token exchange.

There is no automatic retry loop, alternate OAuth flow, OAuth 1.0a fallback, browser-cookie fallback, scraping fallback, or repeated token exchange.

## Persistence boundary

This slice has no credential persistence side effect.

It must not:

- write access or refresh tokens to files;
- write tokens to Windows Credential Manager;
- write DPAPI blobs;
- write tokens to environment variables;
- print tokens for copy/paste;
- copy tokens to the clipboard;
- modify the parent shell environment;
- change the current `X_CONTEXT_USER_ACCESS_TOKEN` lookup behavior used by collection commands.

Secure persistence, credential lookup integration, atomic refresh replacement, revoke/logout, and deletion/recovery belong to a separate lifecycle issue.

## Real-boundary qualification

Unit and contract tests use fake OAuth values and fake browser/listener/transport boundaries only.

After exact-head automated validation and independent/adversarial review, one intentional real OAuth qualification may be performed only by explicit human decision. Retained evidence must contain non-secret protocol facts only. Credential, code, verifier, state, raw callback, and raw token response material must never be committed or pasted into project evidence.

## Official sources re-verified 2026-09-14

- X documentation: OAuth 2.0 Authorization Code Flow with PKCE
- X documentation: Apps / OAuth 2.0 app types and callback URL requirements

If provider behavior materially changes, re-verify these external facts before changing the implementation contract.
