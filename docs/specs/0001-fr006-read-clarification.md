# SPEC-0001 normative clarification — FR-006 `read` CLI

- **Status:** Proposed
- **Date recorded:** 2026-09-11
- **Related:** SPEC-0001, Issue #9, FR-001, FR-002, FR-005, NFR-003, NFR-005
- **Scope:** FR-006 `read` vertical slice only

This document is a normative clarification of SPEC-0001 for Issue #9. It narrows the first FR-006 implementation slice without changing the broader bookmarks/likes CLI contract already defined in SPEC-0001.

## 1. Command and input

The implemented command for this slice is:

```text
x-context read <x-status-url>
```

The positional input is a supported X/Twitter status URL. The CLI shall delegate URL parsing and Post ID extraction to FR-001, then delegate the provider-compatible Post ID boundary and official single-Post lookup to FR-002.

Direct Post-ID CLI input is not part of this slice and must not be accepted as an undocumented alternate path.

## 2. Credential supply

The FR-006 `read` CLI shall obtain the app-only Bearer Token from the process environment variable:

```text
X_CONTEXT_BEARER_TOKEN
```

The CLI shall not expose a token positional argument or token option in this slice.

A missing, empty, or locally unsafe credential value shall fail as `configuration_error` before provider transport.

Credential material, Authorization headers, credential-shaped values, and raw provider payloads must not appear in stdout, stderr, traceback output, normal diagnostic objects, committed evidence, or normal logs.

Credential storage, keyring integration, config-file design, OAuth user authorization, refresh-token lifecycle, and OAuth 1.0a remain out of scope.

## 3. stdout / stderr contract

On success:

- stdout contains exactly one FR-005 canonical JSON document followed by the normal trailing newline;
- stderr contains non-secret per-command usage diagnostics required by NFR-005.

On handled failure:

- stdout is empty;
- stderr contains the stable error category;
- diagnostics must not require callers to parse provider prose to determine the category.

Provider rate/usage metadata is diagnostic only and must not be added to the canonical JSON schema.

## 4. Exit-code contract

The first `read` slice uses a deliberately small process exit-code surface:

- `0` — success;
- `2` — local invocation, input, parser, or configuration failure, including `invalid_input` and `configuration_error`;
- `3` — official-provider/read failure, including `authentication_failed`, `authorization_failed`, `resource_unavailable`, `rate_limited`, `usage_blocked`, and `provider_error`.

The stable error category on stderr provides the finer distinction. This slice does not allocate one exit code per provider category.

## 5. NFR-005 success-path diagnostics

The existing FR-002 `lookup_post(...) -> CanonicalEnvelope` compatibility contract shall remain valid for existing callers.

FR-006 may add the smallest compatible provider result/diagnostic path needed to retain safe success metadata without contaminating canonical JSON.

For each `read` command execution, diagnostics shall make observable:

- `operation = read`;
- number of provider requests attempted;
- returned item count;
- whether a continuation token was returned;
- safe allow-listed provider rate metadata when available.

For this operation, requested page size is not applicable and must not be fabricated.

Local URL rejection, provider-incompatible extracted IDs, and local credential rejection shall report zero provider requests attempted.

A successful provider read shall report exactly one provider request attempted. A provider failure after an attempted request shall also preserve the attempted-request count while exposing only already-approved safe metadata.

The implementation must not calculate or promise exact monetary cost from hard-coded X prices, rate limits, monthly caps, or Owned Read rules.

## 6. Acceptance criteria for the first FR-006 slice

- **AC-FR006-R01:** `read <x-status-url>` composes FR-001, FR-002, and FR-005 without duplicating their responsibility boundaries.
- **AC-FR006-R02:** direct Post-ID CLI input is not accepted.
- **AC-FR006-R03:** successful stdout contains canonical JSON only; diagnostics are stderr-only.
- **AC-FR006-R04:** success exits `0`; local input/configuration/parser failures exit `2`; provider/read failures exit `3`.
- **AC-FR006-R05:** every handled failure exposes an existing stable error category without provider prose parsing.
- **AC-FR006-R06:** the Bearer Token is obtained only from `X_CONTEXT_BEARER_TOKEN` in this slice; no token CLI argument exists.
- **AC-FR006-R07:** credential values, Authorization headers, raw provider response bodies, and arbitrary provider headers do not appear in stdout/stderr/traceback or normal diagnostic objects.
- **AC-FR006-R08:** invalid URL and provider-incompatible extracted ID fail before provider transport with zero requests attempted.
- **AC-FR006-R09:** missing/empty/unsafe credential fails before provider transport as `configuration_error` with zero requests attempted.
- **AC-FR006-R10:** successful usage diagnostics report operation, request count, returned item count, continuation=false, and safe rate metadata when available without altering canonical JSON.
- **AC-FR006-R11:** provider failures preserve FR-002 stable categories and safe diagnostic boundaries and never invoke unofficial fallback.
- **AC-FR006-R12:** existing FR-001, FR-002, and FR-005 public behavior remains compatible.
- **AC-FR006-R13:** no bookmarks/likes implementation, authenticated-subject work, persistence, optional canonical fields, pricing calculator, browser/scraping/cookie/internal-GraphQL path, or OAuth user flow is added by this slice.

## 7. Evidence order

Implementation for Issue #9 follows:

1. requirement/acceptance clarification;
2. TEST_MATRIX mapping;
3. CLI contract tests;
4. implementation;
5. adversarial review of stdout/stderr, traceback, repr, raw-provider and credential exposure;
6. local regression and exact-head validation;
7. Draft PR;
8. human Ready / merge decision.
