# Review-0002 — Independent review of remediated SPEC-0001

- **Status:** Completed for the current spec-only branch state
- **Date:** 2026-09-09
- **Scope:** SPEC-0000, remediated SPEC-0001, ADR-0003, ADR-0004, TEST_MATRIX
- **Goal:** Determine whether any MAJOR specification defect remains before implementation authorization

## Evidence basis

- GitHub branch `spec/issue-1-mvp-contract`
- SPEC-0000 / SPEC-0001 / ADR-0003 / ADR-0004 / TEST_MATRIX
- Current official X documentation checked during review for pay-per-use/Owned Reads and bookmark/like collection behavior
- GitHub Actions unavailable because monthly Actions minutes are exhausted; no CI success is claimed

## Finding R2-01 — Authenticated collection target was not explicitly bound to the authenticated subject

**Severity:** MAJOR  
**Status:** Remediated

### Problem

SPEC-0001 described bookmarks and likes as the authenticated user's collections, but did not require the user ID used by the provider request to equal the authenticated subject identity.

A conforming-looking implementation could therefore have accepted or configured an arbitrary target user ID while still satisfying the previous acceptance criteria. That would violate the intended personal-context boundary and could also change privacy/cost semantics.

Current X pricing documentation defines Owned Reads conditionally: qualifying own-data endpoints receive Owned Read treatment when the endpoint `{id}` matches the authenticated user and that user owns the developer app. This external pricing rule is not frozen into the product specification, but it confirms that subject identity is materially relevant.

### Remediation

SPEC-0001 now requires:

- official derivation/verification of the authenticated subject identity;
- endpoint target `{id}` to match that subject before collection access;
- fail-closed `subject_mismatch` behavior before issuing the collection request;
- no arbitrary target-user argument for P0 bookmarks/likes;
- canonical collection output to include minimal subject provenance;
- opaque continuation tokens to remain out of diagnostics/committed evidence.

TEST_MATRIX now maps these requirements to automated and real-boundary evidence.

## Independent review result after remediation

No additional **MAJOR** specification defect was identified in this pass.

The remaining uncertainties are intentionally external or implementation-stage matters:

- current X endpoint authentication/scope details must be verified at implementation time rather than frozen as durable constants;
- prices, Owned Read qualification, rate limits, and usage-gate response details remain external platform facts;
- provider continuation tokens are opaque and must not be interpreted by x-context;
- Bookmark Folders remain a P1 candidate omission/non-blocking prioritization matter from Review-0001;
- actual credential-store choice and OAuth implementation remain deferred implementation decisions within ADR-0004's read-only boundary;
- real-boundary smoke cannot be completed until product code and live local credentials exist.

## Gate recommendation

From a specification-contract perspective, the current P0 scope is suitable for **human acceptance review** before implementation begins.

This review does not mark the PR Ready and does not authorize merge or implementation by itself. Ready/merge and acceptance of the specification remain human-final decisions.
