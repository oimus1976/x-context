# ADR-0003 — Use only the official X API for MVP data acquisition

- **Status:** Proposed
- **Date recorded:** 2026-09-09
- **Decision owners:** Project owner
- **Related:** Issue #1, SPEC-0001

## Context

x-context exists to make X content reliably available to local tools and AI-assisted analysis. Technically, unofficial options exist, including browser scraping, browser-cookie reuse, internal GraphQL endpoints, and third-party scraping/mirror services.

Those alternatives may appear cheaper or broader, but they create unstable platform coupling, credential/cookie risk, unclear authority boundaries, and a higher chance of silent breakage when X changes its web implementation. The project needs a durable MVP boundary that remains understandable during failure and maintenance.

## Decision

The MVP will acquire X data only through documented official X API interfaces.

When the official API cannot satisfy a request, x-context will fail explicitly. It will not automatically fall back to scraping, browser automation, browser cookies, undocumented/internal GraphQL endpoints, or third-party mirrors/proxies.

A future non-official provider, if ever considered, requires an explicit specification and ADR change before implementation.

## Alternatives considered

### Browser scraping

Rejected for the MVP because markup and access behavior are not a stable data contract, and scraping would increase breakage and policy/operational uncertainty.

### Browser cookie + internal GraphQL

Rejected for the MVP because browser session material is high-value credential data, internal query contracts can change without compatibility guarantees, and the technique blurs the boundary between a local reader and session impersonation.

### Third-party scraping/mirror provider

Rejected as an equivalent authority because it adds another trust, privacy, and availability dependency and may obscure the original provider's semantics.

### Provider abstraction with multiple implementations from day one

Deferred. The implementation may isolate X API access behind a provider boundary for maintainability, but only the official provider is authorized by SPEC-0001.

## Consequences

### Positive

- Clear and reviewable acquisition authority.
- Lower credential exposure than browser-cookie approaches.
- Provider behavior can be validated against published API semantics.
- Failure modes remain explicit instead of silently changing data sources.

### Negative / tradeoffs

- API availability, pricing, quotas, and endpoint changes remain external dependencies.
- Some data visible in the X web UI may not be available through the authorized API contract.
- The project may incur usage cost.

## Authority / security / recovery effects

This ADR narrows runtime authority. The MVP is not authorized to scrape X or access browser session cookies.

On provider failure, recovery is diagnostic: report the failure category, retain non-secret evidence, and stop. Recovery does not include switching to an unofficial provider.

## Evidence / validation required

Before treating this decision as validated in practice:

- automated tests must prove provider failure does not invoke an unofficial fallback;
- real-boundary smoke must demonstrate the configured destination is an official X API endpoint;
- repository review must find no browser-cookie acquisition or undocumented GraphQL implementation in MVP product code.

## Supersession

If replaced later, record `Superseded by ADR-xxxx` rather than erasing this history.
