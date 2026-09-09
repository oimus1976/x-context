# ADR-0004 — Keep MVP authentication and product authority read-only

- **Status:** Proposed
- **Date recorded:** 2026-09-09
- **Decision owners:** Project owner
- **Related:** Issue #1, SPEC-0001

## Context

The MVP needs authenticated access to user-specific X activity such as bookmarks and liked posts. OAuth credentials may be granted broader capabilities than the application actually needs. If the application requests or exposes mutation authority unnecessarily, a credential compromise or implementation defect could cause external writes to the user's X account.

The project therefore needs a narrow authorization contract independent of whatever broader authority a supplied credential might technically possess.

## Decision

The MVP will request only read-capable scopes/permissions required for the accepted read operations.

Product behavior will expose no X mutation operations. Even if a supplied credential possesses broader write authority, x-context will not surface posting, deleting, liking, bookmarking, following, messaging, or equivalent mutation commands in the MVP.

Credential material must remain outside repository content and normal logs/output.

## Alternatives considered

### Request broad scopes now for future convenience

Rejected because unused write authority increases blast radius without helping the accepted MVP.

### Accept any credential and expose writes only when requested later

Rejected as an authority-by-accident model. Future mutation features require explicit specification, risk review, and authorization design.

### App-only authentication for all operations

Insufficient because authenticated-user bookmarks/likes require user-context authorization. The project may use the least-authority official flow appropriate to each operation, but the product boundary remains read-only.

## Consequences

### Positive

- Reduced external-write risk.
- Easier human comprehension of the application's authority.
- Clear negative requirement for tests and reviews.
- Future write support cannot arrive silently as incidental scope expansion.

### Negative / tradeoffs

- A later write feature requires a deliberate auth redesign and new approval.
- User-context authentication remains credential-sensitive even when read-only.

## Authority / security / recovery effects

The MVP has read authority only for data permitted by the authenticated X account and official API. It has no product-authorized external mutation path.

Credential failure recovery is to re-authenticate or correct configuration; it is not to log tokens, weaken scope checks, or reuse browser session cookies.

## Evidence / validation required

Before treating this decision as validated in practice:

- configured/requested OAuth scopes must be reviewable and limited to read requirements;
- automated tests must show no mutation commands are registered;
- logs and error paths must be checked for token/authorization-header leakage;
- real-boundary smoke evidence must document successful read behavior without publishing credential material.

## Supersession

If replaced later, record `Superseded by ADR-xxxx` rather than erasing this history.
