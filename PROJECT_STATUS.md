# Project Status

> Keep this top block short enough to read in about 30 seconds.

## 30-second state

- **Goal:** Establish a read-only official-X-API context reader with specification-driven traceability and a broader staged personal-context roadmap.
- **Current phase:** P0 implementation, FR-002 official single-Post lookup (Issue #7), Draft-PR preparation/final exact-head gate.
- **Last completed:** Issue #5 / PR #6 (FR-005 minimal canonical `read` schema), merged to `main` at `d8efde8f4156fd56c03831763b3d1cd3dfcd4d9a` with 14/14 post-merge regression passing.
- **Now working on:** FR-002 provider contract and implementation are on `issue-7-fr002-official-post-lookup`; implementation head `4783bf1a6bfbe6cd35967e0ec8c545c4c294b42e` passed exact-head checkout validation with 31/31 product tests and `git diff --check` exit 0.
- **Next:** Create the Draft PR, then revalidate the documentation-updated PR head once more before human Ready consideration. Ready/merge remain human-final.
- **Main risks:** X API platform facts can change; provider/raw/credential data must not leak into public schema or diagnostics; GitHub Actions minutes are exhausted, so local/static evidence is required.
- **Required comprehension level:** C1

## Current authority summary

See `PROJECT_PROFILE.toml`; baseline rules live only in `BASELINE.md`.

- Planning: GitHub Issues and accepted specs/ADRs
- Execution: Git topic branches and pull requests
- Source code/current shared state: GitHub
- Private/actual data: Local runtime only; not repository/PR/CI artifacts by default
- CI evidence: GitHub Actions when available; currently unavailable because the monthly Actions-minute quota is exhausted. Queued/unstarted runs are not code-test results.
- Production/deployed state: N/A during experimental MVP

## Current risk facets

Persistent project facets:

- PRIVATE_DATA
- CREDENTIALS
- PLATFORM_DEPENDENT

Default project risk level: `ELEVATED`.

Issue #7 introduces a real official-provider read path and credential-bearing HTTP request construction, but no write authority, private-activity collection read, browser/cookie access, unofficial provider, persistence, or OAuth user-flow implementation.

## Validated facts

- Repository: `oimus1976/x-context`.
- Current `main` at Issue #7 start: `d8efde8f4156fd56c03831763b3d1cd3dfcd4d9a`.
- Issue #5 is closed/completed and PR #6 is merged.
- Active work item: Issue #7, `FR-002: official single-post lookup via X API`.
- Active branch: `issue-7-fr002-official-post-lookup`.
- Official-provider research was rechecked before implementation and source provenance is recorded on Issue #7.
- The first FR-002 slice uses only `GET https://api.x.com/2/tweets/{id}` with OAuth 2.0 app-only Bearer authorization.
- OAuth 1.0a User Context and OAuth 2.0 Authorization Code with PKCE are provider-supported for Post lookup but intentionally not implemented in Issue #7.
- FR-001 remains URL syntax/extraction only. FR-002 separately enforces the official endpoint's current `^[0-9]{1,19}$` path-ID boundary before network access.
- The provider requests no optional `post.fields` or `expansions`; only `data.id` and `data.text` enter the existing canonical `read` envelope.
- Stable error mapping distinguishes `authentication_failed`, `authorization_failed`, `resource_unavailable`, `rate_limited`, `usage_blocked`, `configuration_error`, `invalid_input`, and conservative `provider_error` conditions without requiring callers to parse arbitrary provider prose.
- Ambiguous `429` responses fail conservatively as `provider_error`; only safely identified rate-limit or usage-cap problem types receive the more specific categories.
- Rate-limit diagnostics allow-list only the standard limit/remaining/reset headers; provider response bodies and arbitrary headers are not surfaced.
- Authorization-bearing request headers are excluded from dataclass `repr`; transport exception chaining is suppressed; CR/LF-bearing Bearer values are rejected before transport.
- Current X pricing/rate-limit/monthly-cap/Owned Read values are not hard-coded as product behavior. Official X documentation currently publishes conflicting monthly pay-per-use Post-read cap figures, so the implementation deliberately does not choose one.
- Exact-head checkout validation on implementation head `4783bf1a6bfbe6cd35967e0ec8c545c4c294b42e` passed 31 tests total: FR-001 6, FR-002 17, FR-005 8; `TEST_EXIT=0`; `git diff --check origin/main...HEAD` exit 0. The first wrapper attempt produced `TEST_EXIT=-1` and a false-positive PASS marker due to Windows PowerShell 5.1 native stderr handling; it is retained as validator-failure evidence, not implementation PASS evidence. The corrected retry merged native stderr inside `cmd.exe` and used `$LASTEXITCODE` as authority.
- This PROJECT_STATUS update moves the topic-branch head, so one final exact-head revalidation remains necessary before human Ready consideration.
- GitHub Actions remains unavailable due to exhausted monthly Actions minutes.

## Current implementation scope

Issue #7 is limited to:

- official single-Post lookup provider;
- app-only Bearer request construction;
- provider-compatible Post-ID validation;
- normalization of provider `id` + `text` to the existing canonical `read` model;
- stable fail-closed provider error classification;
- safe allow-listed rate-limit failure metadata;
- credential/raw-response diagnostic hardening;
- deterministic unit/contract tests and requirement traceability.

Explicitly not authorized in Issue #7:

- FR-006 CLI wiring;
- OAuth authorization-code/token lifecycle or OAuth 1.0a implementation;
- authenticated-subject resolution/binding;
- bookmarks/likes;
- optional canonical author/created-at/URL/reference/media/link fields;
- private activity persistence;
- pricing calculator, monthly-cap enforcement, or hard-coded X platform economics;
- unofficial acquisition fallback.

## Known limitations / residual risks

- The implementation head has been exact-head validated, but this status update changes the branch head; the resulting PR head must be revalidated once before Ready.
- A live API smoke is optional qualification evidence only and must be intentionally authorized because reads may consume paid usage; no live call is required for unit/contract correctness.
- Success-path per-command usage diagnostics required by NFR-005 will be completed when FR-006 wires the CLI; Issue #7 preserves the provider boundary and safe failure metadata without making provider response details part of canonical JSON.
- Optional author/created-at/canonical-URL/reference/media/link fields remain deferred until their canonical shapes are separately specified and tested.
- Authenticated collection subject provenance and known-empty/unknown semantics remain deferred to the collection workstreams.
- X API endpoint/auth/pricing/rate-limit/Owned Read behavior remains external and must be re-verified when later workstreams depend on it.

## Deferred work

After Issue #7, the accepted preferred P0 order remains:

- FR-006 `read` CLI;
- authenticated-subject resolution/binding contract for collections;
- FR-003 bookmarks;
- FR-004 likes.

Product-level P1-P3 candidates remain governed by SPEC-0000 and are not implied by Issue #7.

## Recovery / first diagnostic entry points

- Inspect Issue #7, the Draft PR, `docs/specs/0001-mvp.md`, `docs/TEST_MATRIX.md`, `x_context/x_api.py`, `tests/test_fr002_x_api.py`, and `tests/test_fr002_security.py`.
- Compare the topic branch against `main` before Ready/merge; do not expand into FR-006 or authenticated collections to solve an FR-002 issue.
- For local validation, use fake credentials only unless an intentional live smoke is separately chosen; never retain Authorization headers or raw provider bodies in evidence logs.

## Recent meaningful changes

See `CHANGELOG.md` for semantic history and Git/PRs for implementation detail.
