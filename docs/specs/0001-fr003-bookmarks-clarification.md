# SPEC-0001 clarification — FR-003 authenticated bookmarks

- **Status:** Normative clarification for Issue #19
- **Base specification:** `docs/specs/0001-mvp.md`
- **Scope:** Authenticated bookmarks, bounded one-page retrieval and CLI integration
- **Base main:** `d36a8cab3263d662eb5706e563aadd55a05b0c6e`

## 1. Purpose

FR-003 implements the first private activity collection in x-context: reading one bounded page of the currently authenticated X user's bookmarks through the official X API.

The slice reuses the authenticated-subject boundary completed in Issue #11 / PR #18. It must not duplicate or weaken that identity boundary, introduce arbitrary target-user reads, or expand into OAuth browser flow, persistence, write operations, multi-page traversal, likes, scraping, browser-cookie reuse, or internal GraphQL.

## 2. Current external-provider facts

Re-verified on 2026-09-13 from the current X public API workspace:

- endpoint: `GET https://api.x.com/2/users/{id}/bookmarks`;
- authorization: OAuth 2.0 user context;
- read scopes: `tweet.read users.read bookmark.read`;
- `max_results`: accepted provider range 1 through 100;
- `pagination_token`: caller-supplied token obtained from the previous response;
- bookmark lookup is for the authenticated/requesting user's bookmarks.

These are external platform facts, not immutable product constants. Current numeric rate limits, pricing, billing semantics, provider defaults, and Owned Read treatment must not become correctness constants.

## 3. Credential and subject boundary

The collection command uses the distinct user-context credential source `X_CONTEXT_USER_ACCESS_TOKEN` at the caller/CLI boundary.

- No fallback to app-only `X_CONTEXT_BEARER_TOKEN` is permitted.
- Missing, empty, or CR/LF-bearing user-context credentials fail locally as `configuration_error` before provider transport.
- The authenticated subject is resolved through the existing official `/2/users/me` boundary.
- The collection target path ID must pass `bind_collection_subject(...)` and exactly equal the resolved subject ID before the bookmark request is issued.
- The CLI exposes no user-ID option or positional argument.

## 4. One-page product bound

One `bookmarks` invocation retrieves at most one bookmark provider page.

- omitted `--max-results` means 25;
- accepted product range is 1 through 100;
- invalid page size fails locally before bookmark transport;
- an optional `--page-token` is forwarded to exactly one bookmark request;
- there is no `--all` and no implicit pagination loop.

Provider limits may reduce the effective response size, but implementation must never increase the caller/product request above the accepted cap.

## 5. Canonical result

Successful output uses the canonical schema with:

- `schema_version = "1"`;
- `source = "x"`;
- `operation = "bookmarks"`;
- authenticated `subject` containing the resolved user ID and optional safely resolved username;
- normalized Post items;
- explicit page metadata.

When the provider returns a continuation token:

- canonical `page.next_token` contains that provider token;
- `page.complete = false`.

When no continuation token is returned, the returned point may be marked complete. Requested page-size boundaries alone must never be used to infer completeness.

This slice requests/normalizes only fields that have explicit requirement/test coverage. It must not silently broaden the canonical Post contract merely because additional provider fields are available.

## 6. Failure contract

Existing stable categories are reused:

- `configuration_error` — missing/unsafe local user-context credential;
- `invalid_input` — invalid page size or other invalid local collection input;
- `authentication_failed` — safely established provider authentication failure;
- `authorization_failed` — safely established provider authorization/scope failure;
- `subject_mismatch` — target identity differs from authenticated subject before collection transport;
- `rate_limited` — safely identified provider rate limit;
- `usage_blocked` — safely identified usage/credit/spending gate;
- `provider_error` — malformed/contradictory success, ambiguous provider failure, transport failure, or unexpected response.

No failure triggers an unofficial acquisition path.

## 7. Privacy and diagnostic boundary

Bookmarks are private activity data for this project even when referenced Posts are public.

Default behavior is process-and-return, not persist.

Normal diagnostics/evidence must not contain:

- access tokens or Authorization headers;
- raw provider bodies;
- arbitrary provider headers;
- private bookmark contents;
- opaque continuation/page token values;
- underlying transport exception text.

NFR-005 diagnostics may expose only non-secret structured facts such as operation, provider request count, returned item count, requested page size, continuation-present boolean, and allow-listed safe rate metadata.

Subject resolution and bookmark retrieval are separate provider attempts and must be counted truthfully.

## 8. CLI contract

Logical interface:

```text
x-context bookmarks [--page-token <token>] [--max-results <n>]
```

The command has no target-user argument and no token argument.

Successful stdout is canonical JSON only. Human-readable diagnostics go to stderr.

## 9. Acceptance criteria

Issue #19 owns AC-FR003-01..16. This clarification is authoritative for their interpretation together with SPEC-0001.

## 10. Required test mapping before implementation

Before product code, `docs/TEST_MATRIX.md` must replace the generic FR-003 placeholder with concrete automated evidence names covering at least:

- exact official bookmark endpoint/method;
- user-context credential only / no app-only fallback;
- default 25 and explicit 1/100 bounds;
- invalid max-results => zero bookmark transport;
- subject resolution followed by exact-subject bookmark request;
- mismatch => no bookmark transport;
- page token forwarded once and not logged;
- no continuation => complete page; continuation => incomplete page;
- no automatic second bookmark request;
- canonical bookmarks envelope with subject provenance;
- malformed/contradictory success fail-closed;
- authentication/authorization/rate-limit/usage/provider failure mapping;
- private payload/token/header/transport exception redaction;
- aggregate provider request accounting;
- no persistence side effect;
- no target-user CLI argument;
- full regression.

## 11. Real-boundary qualification

After authoritative exact-head local validation, at most one intentional real bookmark-page smoke may be performed if a suitable user-context token is intentionally available.

The smoke retains only non-secret protocol/diagnostic facts. Private bookmark payloads, credentials, Authorization headers, and opaque continuation tokens must not be committed, pasted into Issues/PRs, or retained in CI artifacts.

A live smoke is qualification evidence, not a substitute for contract tests.

## 12. Governance

Required order:

1. normative clarification;
2. TEST_MATRIX concrete mapping;
3. tests;
4. minimal implementation;
5. adversarial review;
6. authoritative exact-head validation;
7. optional intentional real-boundary smoke;
8. Draft PR;
9. human Ready / merge.
