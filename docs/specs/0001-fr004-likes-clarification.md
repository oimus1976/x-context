# SPEC-0001 FR-004 liked-post clarification

- **Status:** Proposed implementation clarification
- **Date recorded:** 2026-09-13
- **Related:** SPEC-0001, Issue #21, Issue #11 / PR #18, Issue #19 / PR #20

## Purpose

Clarify the first FR-004 implementation slice for authenticated liked-post reads without expanding the accepted P0 product boundary.

## Provider boundary

The collection request uses only the official endpoint:

`GET https://api.x.com/2/users/{id}/liked_tweets`

For the P0 `likes` command, x-context deliberately uses the existing user-context authority and authenticated-subject boundary even though the provider may support broader authentication modes for this endpoint. Provider capability does not expand product scope.

The user-context credential source is `X_CONTEXT_USER_ACCESS_TOKEN`. The app-only `X_CONTEXT_BEARER_TOKEN` must not be treated as fallback collection authority.

OAuth 2.0 user-context scopes currently required by the provider are:

- `tweet.read`
- `users.read`
- `like.read`

These provider facts must be re-verified when materially changed; they are not immutable product constants.

## Subject binding

Each valid invocation resolves the current subject through the existing official `/2/users/me` boundary, then applies the shared same-subject binding guard before issuing the liked-post request.

The `{id}` path component must exactly equal the resolved authenticated subject ID. P0 exposes no caller-controlled target-user argument.

## Bounded pagination

One invocation performs at most one liked-post collection request.

- omitted `--max-results` means 25;
- accepted product range is 1..100;
- `--page-token`, when supplied, is forwarded to that single request only;
- there is no implicit fetch-all, retry loop, or page traversal;
- provider continuation maps to canonical `page.next_token`;
- whenever a continuation token exists, `page.complete` is false;
- absence of provider continuation is the only signal this slice may use to mark that returned point complete;
- item count alone never proves completeness.

Opaque continuation values must not enter normal diagnostics or retained verification evidence.

## Canonical output

Successful output uses the existing canonical schema with:

- `operation = "likes"`;
- authenticated subject provenance;
- the minimum currently supported Post representation (`id`, `text`);
- explicit page metadata.

This slice does not introduce optional author/media/reference expansions.

## Private-data and persistence boundary

Like history is private user activity data. Default behavior is process-and-return only. No payload persistence is introduced.

Diagnostics and normal exceptions must not expose:

- access tokens or Authorization headers;
- raw provider bodies;
- arbitrary provider headers;
- liked-post text/content;
- opaque page-token values;
- transport exception text.

## Diagnostics

NFR-005 accounting aggregates the two provider attempts that may occur in a normal successful invocation:

1. authenticated-subject resolution;
2. liked-post collection request.

Safe diagnostics may include:

- operation name;
- total provider requests attempted;
- returned item count;
- requested page size;
- whether continuation was returned;
- allow-listed safe rate metadata per provider endpoint.

Rate metadata from different endpoints must not be combined into a fabricated single provider budget.

## Failure behavior

Existing stable categories remain authoritative. Fail closed when the provider response is malformed, contradictory, or ambiguous.

Safely distinguish authentication, authorization, rate-limit, and usage-blocked failures when supported by provider facts. Otherwise use conservative `provider_error` rather than infer unsupported semantics.

A same-subject mismatch fails before collection transport.

## Explicitly out of scope

- OAuth browser/PKCE ceremony;
- refresh-token persistence;
- multi-page/fetch-all behavior;
- like/unlike mutation;
- arbitrary target-user support;
- private like-history persistence;
- write scopes;
- scraping, browser cookies, internal GraphQL, mirrors, or other unofficial fallback.
