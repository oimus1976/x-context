# SPEC-0006: Authenticated own-post read capability

## Status

Draft

## Purpose

Provide a read-only capability to retrieve posts authored by the authenticated X user.

This capability extends x-context's authenticated user context while preserving:

- official API only boundary;
- authenticated subject binding;
- read-only authorization;
- private credential/data protection.

## Scope

Included:

- authenticated subject resolution;
- own-post retrieval;
- canonical read output;
- safe pagination handling.

Excluded:

- arbitrary user timeline retrieval;
- mentions;
- followers/following;
- list relationships;
- blocks;
- mutes;
- quote expansion;
- reply chain reconstruction;
- media expansion;
- AI indexing.

Fetch-all, date filtering, since/until filtering, optional fields/expansions, and new P1 capabilities are also out of scope. This draft fixes the MVP contract before implementation; it does not establish implemented behavior or authorize implementation in this specification-only revision.

## CLI contract

Logical interface:

```text
x-context posts [--max-results <n>] [--page-token <opaque-token>]
```

Examples:

```text
x-context posts
x-context posts --max-results 50
x-context posts --page-token <opaque-token>
```

The command operates only on the authenticated subject.

The command MUST NOT accept arbitrary user identifiers.

No user-ID option or positional argument is introduced. Additional post scopes require a separate specification.

## Requirements

### R-OWNPOST-001 Subject resolution

The system MUST resolve the authenticated subject before retrieving posts.

Credential resolution MUST reuse SPEC-0003's existing lifecycle boundary. Required sequence:

```text
credential lifecycle (SPEC-0003)
  |
  v
user-context access token
  |
  v
GET /2/users/me
  |
  v
authenticated subject ID
  |
  v
GET /2/users/{subject-id}/tweets
```

If no user-context credential is available, resolution MUST fail locally with zero provider requests, including no `/2/users/me` request. Subject resolution and same-subject binding reuse the existing authenticated-subject contract; malformed or failed subject resolution MUST prevent the tweets request.

`X_CONTEXT_USER_ACCESS_TOKEN` retains its existing explicit per-operation compatibility/recovery override, including fail-closed handling of an invalid override and no automatic import. `X_CONTEXT_BEARER_TOKEN` MUST NOT be used as user authority. OAuth acquisition and credential persistence/refresh/revoke remain governed by their existing specifications; SPEC-0006 defines no new acquisition, storage, refresh, or revoke mechanism.

The caller MUST NOT provide an arbitrary target user ID.

### R-OWNPOST-002 Own post retrieval

Own posts means posts authored by the authenticated subject. The system MUST request posts only for the resolved authenticated subject.

The system MUST use the official X API endpoint:

```text
GET /2/users/{authenticated-subject-id}/tweets
exclude=retweets
```

The path ID MUST be obtained only from `/2/users/me` and pass the existing same-subject binding boundary.

Normal posts, the subject's own replies, and the subject's own quote posts are included. Retweets/reposts are excluded by `exclude=retweets`; replies MUST NOT be excluded. The MVP does not introduce an "original posts only" concept.

The request MUST NOT add optional fields or expansions. Quote-target expansion, reply-chain reconstruction, and media expansion are not performed.

The initial implementation is read-only.

### R-OWNPOST-003 Canonical representation

The output MUST reuse the existing SPEC-0001 canonical envelope with `schema_version = "1"`, `source = "x"`, `operation = "posts"`, UTC `retrieved_at`, authenticated `subject` (resolved `id` and optional safely resolved `username`), `items`, and `page`. No separate own-post envelope is introduced.

Initial post item fields:

- id
- text

Canonical validation MUST continue to reject missing/malformed authenticated subjects and unsupported/unknown operations. Collection response handling MUST reuse the existing fail-closed contract: malformed items or metadata, contradictory provider errors, invalid continuation, and results exceeding the requested page size are `provider_error`, not successful output. Existing stable error categories and SPEC-0001 NFR-005 / collection diagnostics apply to `posts`; no separate error model or diagnostic schema is introduced. Request-attempt accounting MUST include credential refresh, `/2/users/me`, and tweets requests actually attempted, on both success and failure.

The following require separate capability specifications:

- media expansion;
- quote expansion;
- reply chain reconstruction;
- conversation context.

### R-OWNPOST-004 Pagination

The system MUST use the existing P0 bounded one-page collection model:

- omitted `--max-results` means 25; accepted posts range is 5..100 inclusive;
- page size is sent as provider parameter `max_results`;
- explicit continuation uses CLI `--page-token`, forwarded as provider `pagination_token`;
- one invocation retrieves at most one tweets provider page, with no automatic fetch-all or page traversal;
- supplied page tokens reuse existing collection local validation: a non-empty string containing no control characters (U+0000..U+001F or U+007F); invalid input is rejected as `invalid_input` before credential load/refresh or provider traffic;
- continuation tokens remain opaque: no decoding, interpretation, modification, or normalization of accepted token values;
- provider `meta.next_token` maps to canonical `page.next_token`;
- when `next_token` exists, `page.complete = false`;
- when no `next_token` exists, `page.next_token = null` and `page.complete = true` for the returned point, without claiming historical completeness;
- item count or requested page size alone never determines completeness.

The posts minimum of 5 does not change the existing bookmarks/likes range of 1..100. Invalid local collection input MUST be rejected before credential resolution, preserving SPEC-0003's ordering so invalid input cannot trigger refresh or collection traffic. The one-page bound applies to the tweets collection request, not the separate subject lookup or lifecycle refresh allowed by SPEC-0003.

### R-OWNPOST-005 Privacy boundary

The system MUST reuse the existing collection privacy/redaction contract, SPEC-0003's credential protection, and TEST_MATRIX's Evidence rules. Access/refresh tokens and Authorization headers MUST NOT enter stdout, stderr, diagnostics, controlled exceptions, or retained evidence. Raw provider responses and provider/transport exception prose MUST NOT be passed through; post contents and input/output page-token values MUST NOT enter diagnostics, controlled exceptions, or retained evidence, including CI artifacts and durable validation logs. Canonical post output and continuation remain available to the caller as specified above.

Own-post payload handling MUST remain process-and-return, with no default payload persistence. This restriction does not prohibit SPEC-0003's legitimate secure credential persistence or atomic replacement during refresh; credential storage and own-post payload storage are separate boundaries.

## Acceptance Criteria

### AC-OWNPOST-001

When neither an explicit user-context override nor a lifecycle-managed credential is available under SPEC-0003, the command fails locally with zero provider requests, including zero `/2/users/me` and tweets requests. No app-only bearer fallback or credential acquisition is attempted.

### AC-OWNPOST-002

The tweets endpoint path ID is exactly the authenticated subject ID returned by `/2/users/me`, after existing same-subject binding. A malformed or failed subject response produces no tweets request; identity is not inferred from token contents or configuration.

### AC-OWNPOST-003

No caller-supplied arbitrary user ID is accepted as an option or positional argument. Such input is rejected locally and cannot select a tweets target.

### AC-OWNPOST-004

Successful output satisfies the existing SPEC-0001 envelope contract: `schema_version = "1"`, `source = "x"`, `operation = "posts"`, UTC `retrieved_at`, resolved authenticated `subject`, `items` containing only the minimum `id`/`text` Post representation, and explicit `page`. No new envelope or optional item fields are introduced.

Canonical validation rejects missing/malformed subjects and unsupported/unknown operations. Malformed items or metadata, contradictory provider errors, invalid continuation, and provider results exceeding the requested page size fail closed as `provider_error` without emitting successful canonical output. Authentication and authorization failures map to `authentication_failed` and `authorization_failed`; safely identified rate-limit and usage gates map to `rate_limited` and `usage_blocked`; ambiguous provider or transport failures remain `provider_error`, using the existing collection error contract.

### AC-OWNPOST-005

Omitted page size sends `max_results=25`; explicit values 5 and 100 are accepted and values outside 5..100 are rejected before credential resolution or provider traffic. `--page-token` is forwarded unchanged as `pagination_token` to at most one tweets request. A returned `meta.next_token` becomes `page.next_token` with `page.complete = false`; absent continuation becomes null with `page.complete = true`. Tokens are not decoded/interpreted and no automatic second page is fetched.

Supplied page tokens must be non-empty strings without U+0000..U+001F or U+007F control characters; empty, non-string, or control-bearing inputs fail as `invalid_input` before credential load/refresh or provider traffic. Accepted tokens are not modified or normalized, and no provider-specific internal token format is interpreted. Invalid provider continuation fails closed under AC-OWNPOST-004. Existing NFR-005 / collection diagnostics account for every attempted credential refresh, `/2/users/me`, and tweets request on success and failure; no separate diagnostic schema is introduced.

### AC-OWNPOST-006

The tweets request sends `exclude=retweets` and no optional fields or expansions. The subject's normal posts, replies, and quote posts remain eligible; replies are not implicitly excluded. Retweets/reposts are excluded. Quote-target expansion, reply-chain reconstruction, and media expansion are not performed.

### AC-OWNPOST-007

The entire `x-context posts` operation, including explicit page-size and continuation options, remains authenticated-subject-only. The CLI exposes neither arbitrary target-user selection nor fetch-all, date/since/until filters, or additional post scopes.

It also preserves R-OWNPOST-005 and the existing credential/private-data contract: access/refresh tokens and Authorization headers are absent from stdout, stderr, diagnostics, controlled exceptions, and retained evidence; input/output page tokens and post contents are absent from diagnostics, controlled exceptions, and retained evidence; raw provider responses and provider/transport exception prose are not passed through. Post payloads do not enter CI artifacts or durable validation logs and are not persisted by default. Tests distinguish this payload restriction from the legitimate secure credential load/persistence/refresh behavior governed by SPEC-0003.

## Test-first plan

Tests MUST cover:

- subject resolution;
- missing credential behavior;
- malformed `/2/users/me` responses;
- correct endpoint targeting;
- arbitrary user rejection;
- canonical output;
- pagination handling;
- credential/private-data exclusion.

## Work order

Requirement
  |
  v
Acceptance Criteria
  |
  v
Test
  |
  v
Implementation

Ready / merge remain human-final.
