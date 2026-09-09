# Review-0001 — Adversarial review of SPEC-0000 / SPEC-0001

- **Date:** 2026-09-09
- **Related:** Issue #1, PR #2, SPEC-0000, SPEC-0001
- **Review type:** adversarial specification review
- **Scope:** product-scope consistency, MVP safety/operability, traceability, current official X API assumptions

## Summary

The initial specification is directionally sound: the read-only authority boundary, official-API-only rule, private-activity handling, canonical model, and requirement-to-test traceability are coherent.

The review identified two material MVP gaps and two lower-severity gaps. Product code remains unauthorized until the material gaps are reflected in the accepted specification.

## Findings

### F-001 — MAJOR — Pagination has no continuation contract and can become an unbounded-cost behavior

SPEC-0001 requires pagination to be represented, but the CLI contract does not define how a caller requests a subsequent bookmarks/likes page. It also does not prohibit an implementation from interpreting `bookmarks` or `likes` as "fetch every page".

This creates two problems:

1. `next_token` can be returned with no specified way to consume it;
2. an implementation could silently perform many billable reads in one command.

**Disposition:** REMEDIATE in SPEC-0001 before implementation.

Required contract:

- bookmarks/likes are bounded, one-page operations by default;
- no implicit fetch-all behavior in P0;
- continuation is explicit through a page-token CLI option;
- requested page size is finite and user-controllable within a product safety cap;
- `page.complete` has defined semantics and must not claim collection completeness when a next token exists.

### F-002 — MAJOR — Usage/cost observability is non-normative and billing/usage blocking is not a stable error class

NFR-005 currently says the system "should" expose usage metadata, even though API consumption is a material operational risk. The error model distinguishes rate limiting but not credit/spending/monthly-usage blocking.

Current X documentation describes pay-per-resource reads, Owned Read qualification conditions, spending limits, credit exhaustion, and monthly caps. These are external facts and must not be frozen as durable product constants, but the product needs stable behavior when usage is blocked.

**Disposition:** REMEDIATE in SPEC-0001 before implementation.

Required contract:

- usage observability becomes normative (`shall` / `must`);
- safe diagnostics include operation, request count, item count, pagination state, and provider usage/rate metadata when available;
- add a stable `usage_blocked` error category distinct from `rate_limited`, while preserving provider-specific cause/status only as diagnostic metadata;
- do not calculate or promise an exact monetary cost from hard-coded prices unless a later spec defines a verified pricing source and freshness rule.

### F-003 — MODERATE — Canonical output lacks retrieval provenance needed by AI/context consumers

The normalized model includes source and operation, but no retrieval timestamp. For AI/context use, callers need to distinguish source creation time from acquisition time and reason about freshness.

**Disposition:** REMEDIATE in SPEC-0001.

Required contract:

- add `retrieved_at` in UTC RFC 3339 form at the envelope level;
- preserve post `created_at` separately when available.

### F-004 — MINOR — Capability map omits bookmark-folder structure discovered in the current official API

Current official X documentation exposes Bookmark Folders. This is relevant to the user's broader personal-context goal, but current pricing/entitlement treatment should be re-verified when promoted.

**Disposition:** DEFER from P0; add as a P1 candidate in a later product-scope refinement if the owner values folder semantics. It does not block SPEC-0001 acceptance.

## Current external verification notes

As checked on 2026-09-09 against official X documentation:

- X API uses pay-per-usage pricing and read operations are billed per resource returned.
- Owned Reads include own posts, mentions, liked posts, bookmarks, followers/following, blocks/mutes, and several list relationships when the documented ownership/authentication conditions are met.
- prices and endpoint economics are explicitly subject to change;
- Bookmark Folders are present in current official documentation.

These notes are review evidence, not durable implementation constants. SPEC-0000 already requires re-verification of endpoint availability, scopes, pricing, rate limits, and policy constraints when capabilities are promoted.

## Acceptance impact

PR #2 should remain Draft until F-001 through F-003 are reflected in SPEC-0001 and TEST_MATRIX and the resulting diff is reviewed. F-004 is non-blocking.
