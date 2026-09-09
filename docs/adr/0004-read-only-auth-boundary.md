# ADR-0004 — Keep MVP authentication and product authority read-only

- **Status:** Proposed
- **Date recorded:** 2026-09-09
- **Decision owners:** Project owner
- **Related:** Issue #1, SPEC-0001, Review-0002

## Context

The MVP needs authenticated access to user-specific X activity such as bookmarks and liked posts. OAuth credentials may be granted broader capabilities than the application actually needs. If the application requests or exposes mutation authority unnecessarily, a credential compromise or implementation defect could cause external writes to the user's X account.

A second authority risk is target expansion: even with read-only credentials, implementation convenience must not silently convert "read my bookmarks/likes" into arbitrary-user activity targeting where the provider can technically accept a user ID.

The project therefore needs a narrow authorization contract independent of whatever broader authority a supplied credential might technically possess.

## Decision

The MVP will request only read-capable scopes/permissions required for the accepted read operations.

Product behavior will expose no X mutation operations. Even if a supplied credential possesses broader write authority, x-context will not surface posting, deleting, liking, bookmarking, following, messaging, or equivalent mutation commands in the MVP.

For authenticated personal collections, x-context will derive or verify the currently authenticated subject using an official authenticated-user mechanism and bind the provider target to that subject. P0 will not expose an arbitrary target-user argument for bookmarks or liked-post reads. If target identity cannot be established as the authenticated subject, the collection request fails closed.

Credential material must remain outside repository content and normal logs/output.

## Alternatives considered

### Request broad scopes now for future convenience

Rejected because unused write authority increases blast radius without helping the accepted MVP.

### Accept any credential and expose writes only when requested later

Rejected as an authority-by-accident model. Future mutation features require explicit specification, risk review, and authorization design.

### Allow arbitrary user-ID targets for read-only convenience

Rejected for P0 because it changes the personal-context authority boundary, weakens provenance, and can alter privacy/cost semantics. Broader public/third-party activity targeting, if ever useful and officially supported, requires a separate capability decision.

### App-only authentication for all operations

Insufficient because authenticated-user bookmarks require user-context authorization, and personal collection semantics must remain bound to the authenticated subject. The project may use the least-authority official flow appropriate to each operation, but the product boundary remains read-only and subject-explicit.

## Consequences

### Positive

- Reduced external-write risk.
- Prevents accidental expansion from personal reads to arbitrary-user activity targeting.
- Easier human comprehension of the application's authority and provenance.
- Clear negative requirements for tests and reviews.
- Future write or broader-target support cannot arrive silently as incidental scope expansion.

### Negative / tradeoffs

- A later write feature requires a deliberate auth redesign and new approval.
- A later arbitrary-target read feature requires a deliberate product/privacy decision.
- User-context authentication remains credential-sensitive even when read-only.
- Authenticated-subject resolution/verification adds at least one provider-boundary concern that must be designed and tested.

## Authority / security / recovery effects

The MVP has read authority only for data permitted by the authenticated X account, and authenticated bookmarks/likes are further restricted to the currently authenticated subject. It has no product-authorized external mutation path and no P0 arbitrary-user activity target path.

Credential or subject-resolution failure recovery is to re-authenticate or correct configuration; it is not to log tokens, weaken scope/subject checks, accept caller-supplied arbitrary collection targets, or reuse browser session cookies.

## Evidence / validation required

Before treating this decision as validated in practice:

- configured/requested OAuth scopes must be reviewable and limited to read requirements;
- automated tests must show no mutation commands are registered;
- automated tests must prove authenticated collection target identity equals the authenticated subject before the collection request;
- CLI tests must prove no arbitrary target-user argument exists for P0 bookmarks/likes;
- logs and error paths must be checked for token/authorization-header and opaque page-token leakage;
- real-boundary smoke evidence must document successful same-subject read behavior without publishing credential or private collection material.

## Supersession

If replaced later, record `Superseded by ADR-xxxx` rather than erasing this history.
