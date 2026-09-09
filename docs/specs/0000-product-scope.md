# SPEC-0000 — x-context Product Scope and Capability Map

- **Status:** Proposed
- **Date recorded:** 2026-09-09
- **Related:** Issue #1, SPEC-0001
- **Scope:** Product direction and capability boundaries; this document does not authorize implementation by itself

## 1. Product intent

x-context is intended to become a read-only personal X context reader: a narrow, inspectable layer that obtains X data through supported interfaces, normalizes it, and makes it usable by local tools and AI-assisted analysis without granting product-level mutation authority.

The product is broader than SPEC-0001. SPEC-0001 is the first implementation slice, not the full target capability set.

## 2. Durable product principles

1. **Read-only by product design.** x-context does not expose X mutation operations as part of the intended product direction.
2. **Official X API is the default authority boundary.** Unofficial scraping, browser-cookie reuse, internal GraphQL, or browser automation are not equivalent substitutes and require an explicit specification/ADR change before any future consideration.
3. **User activity data is private context.** Bookmarks, likes, follows, lists, blocks, mutes, and similar relationship/activity data are treated as sensitive even when referenced posts or accounts are public.
4. **Canonical normalized output precedes integrations.** Consumers such as ChatGPT, other AI tools, Obsidian, Markdown exporters, or agents should depend on x-context's normalized contract rather than provider-specific payloads.
5. **Scope is staged.** A capability appearing in this map is not implementation authorization. Each implementation slice requires its own accepted requirements, acceptance criteria, tests, and work item.
6. **External platform facts remain external facts.** Endpoint availability, scopes, pricing, owned-read treatment, rate limits, and policy constraints must be verified against current X documentation when a capability is promoted into an implementation specification.

## 3. Capability map

### P0 — Initial usable reader

Defined by SPEC-0001.

- Read an arbitrary supported X post URL.
- Read the authenticated user's bookmarks.
- Read the authenticated user's liked posts.
- Normalize results into canonical JSON.
- Expose a stable CLI/error contract.
- Preserve read-only, official-API-only, fail-closed behavior.

**Why Likes are included in P0:** Likes provide a second authenticated-user activity collection with semantics different from bookmarks. Supporting both in the first slice tests whether the canonical model and privacy boundary work across more than one owned/read-only activity endpoint without yet expanding into relationship graphs or synchronization features.

This P0 choice is provisional product prioritization, not a claim that Likes are more important than every P1 capability. The owner may reprioritize before implementation of FR-004 without changing the overall product intent.

### P1 — Broader personal X context

Candidate read-only capabilities identified during discovery:

- authenticated user's own posts;
- mentions of the authenticated user;
- followers;
- following;
- owned lists;
- followed lists;
- list memberships;
- pinned lists;
- blocks;
- mutes.

For each P1 capability, a future implementation specification must verify current official endpoint availability, authorization scopes, pricing/usage semantics, pagination/completeness behavior, and privacy implications before implementation.

P1 does **not** imply that all listed capabilities should be synchronized or persisted. One-shot read/return behavior remains the safer default until persistence is separately specified.

### P2 — Knowledge-ingestion outputs

Candidate capabilities after the core read model is stable:

- Markdown export;
- Obsidian-compatible output and metadata;
- optional extraction of links and referenced resources;
- explicit thread/reference/quote expansion where supported by the official provider contract;
- user-controlled local persistence with defined storage, retention, deletion, and export behavior.

P2 must consume the canonical x-context model rather than introduce direct provider calls inside each exporter.

### P3 — AI-assisted context use

Candidate consumers/features after deterministic acquisition and normalization are established:

- summarization;
- classification/tagging;
- thematic retrieval across collected context;
- handing normalized X context to ChatGPT or other AI tooling;
- agent workflows that propose actions based on X context.

AI features do not inherit authority to mutate X. Any agent action outside read/analysis requires a separate product and authority decision rather than implicit scope expansion.

## 4. Explicit non-goals

The following are not part of the intended x-context product direction unless a future product decision explicitly supersedes this document:

- posting, deleting, liking, bookmarking, following, blocking, muting, or other X mutations;
- DM sending or other communication actions;
- silent fallback from the official API to scraping/internal GraphQL/browser-cookie access;
- treating private activity collections as ordinary public telemetry;
- allowing an AI/agent integration to gain broader X authority merely because credentials happen to permit it.

DM **reading** is not part of the current capability map and must not be inferred from the general read-only goal; it would require a separate privacy/necessity decision before even entering a future scope.

## 5. Prioritization rules

When deciding which capability moves from the map into an implementation spec, prefer:

1. direct usefulness to the user's stated context-reading goal;
2. low additional authority and privacy risk;
3. ability to reuse the canonical model rather than create endpoint-specific output;
4. observable and bounded API cost;
5. deterministic testing without live private payloads;
6. small vertical slices that can be reviewed independently.

Do not promote a capability merely because the API exposes it.

## 6. Relationship to SPEC-0001

SPEC-0001 is the P0 implementation contract. It intentionally excludes P1-P3 capabilities so that the first implementation remains reviewable and testable.

Therefore:

- an item being out of scope in SPEC-0001 does not mean it has been rejected from the product direction;
- an item appearing in this capability map does not mean it is authorized for implementation;
- material changes to P0 behavior are made in SPEC-0001 before tests/implementation;
- promotion of a P1/P2/P3 capability requires a new or amended implementation specification with traceable acceptance criteria.

## 7. Current evidence and uncertainty

The capability candidates above reflect the discovery performed for Issue #1 and the user's stated goal of broad read-only access to their X context. This document intentionally does not freeze current X API endpoint names, prices, or entitlement rules as durable product facts. Those external facts must be re-verified when each capability is selected for implementation.
