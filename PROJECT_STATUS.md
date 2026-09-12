# Project Status

> Keep this top block short enough to read in about 30 seconds.

## 30-second state

- **Goal:** Establish a read-only official-X-API context reader with specification-driven traceability and a broader staged personal-context roadmap.
- **Current phase:** P0 authenticated-subject resolution/binding boundary (Issue #11).
- **Last completed:** Issue #9 / PR #10 (FR-006 `read` CLI), squash-merged to `main` at `b13cfb1b8518826bf93328cced89a0d6e0dda1b8`.
- **Last closeout evidence:** exact merged `main` passed 45/45 product tests; detached verification worktree was clean; canonical local `main` was then fast-forwarded to the same GitHub SHA with clean status.
- **Now working on:** `issue-11-authenticated-subject-binding`, adding the shared official `/2/users/me` subject boundary required before bookmarks/likes.
- **Next:** authoritative local regression and exact-head validation of Issue #11; remediate before Draft PR.
- **Human decision pending:** Ready / merge remain human-final.
- **Main risks:** confusing app-only and user-context credentials; leaking user token/raw provider data; allowing a future collection target to diverge from the authenticated subject; hiding the extra `/users/me` request from NFR-005 accounting.
- **Required comprehension level:** C1

## Current authority summary

See `PROJECT_PROFILE.toml`; baseline rules live only in `BASELINE.md`.

- Planning: GitHub Issues and accepted specs/ADRs.
- Execution: Git topic branches and pull requests.
- Source code/current shared state: GitHub.
- Private/actual data: local runtime only; not repository/PR/CI artifacts by default.
- CI evidence: GitHub Actions when available; local exact-head evidence remains required when Actions cannot execute.
- Production/deployed state: N/A during experimental MVP.

## Current risk facets

Persistent project facets:

- PRIVATE_DATA
- CREDENTIALS
- PLATFORM_DEPENDENT

Default project risk level: `ELEVATED`.

Issue #11 adds user-context identity resolution but still does not retrieve bookmark/like collection contents, add write authority, persist credentials/private data, or implement browser/cookie/unofficial acquisition.

## Verified starting point

- Repository: `oimus1976/x-context`.
- Issue #9 is closed/completed and PR #10 is merged.
- Issue #11 base `main`: `b13cfb1b8518826bf93328cced89a0d6e0dda1b8`.
- Completed dependencies: FR-001 URL parsing, FR-005 minimal canonical `read`, FR-002 official single-Post lookup, FR-006 `read` CLI.
- Existing app-only CLI credential source remains `X_CONTEXT_BEARER_TOKEN`.
- Existing `lookup_post(...) -> CanonicalEnvelope` compatibility contract remains in force.

## Issue #11 contract

Issue #11 isolates the common identity boundary required by FR-003 bookmarks and FR-004 likes.

The slice is constrained to:

- official authenticated-user lookup `GET https://api.x.com/2/users/me`;
- explicit user-context access token supplied to the provider helper;
- future collection CLI credential source distinct from app-only auth: `X_CONTEXT_USER_ACCESS_TOKEN`;
- no fallback from missing user-context authority to `X_CONTEXT_BEARER_TOKEN`;
- minimum subject provenance: required ASCII-decimal X user ID plus optional username;
- local same-subject binding guard before any future collection request;
- existing stable error categories and fail-closed conservative provider mapping;
- safe rate metadata and provider-request attempt count outside canonical JSON;
- no bookmarks/likes payload retrieval in this slice.

The normative clarification is `docs/specs/0001-authenticated-subject-clarification.md`; acceptance/test mapping is in `docs/TEST_MATRIX.md`.

## Current implementation state

Branch `issue-11-authenticated-subject-binding` currently adds:

- `AuthenticatedSubject` minimum identity value;
- `SubjectResolutionResult` carrying subject plus safe rate/request diagnostics;
- `resolve_authenticated_subject(...)` using only `GET /2/users/me`;
- local rejection of missing/empty/CRLF-bearing user-context token before transport;
- no optional `user.fields` or expansions;
- fail-closed subject payload validation;
- 401/403 and safely identified rate/usage categories, with ambiguous failures conservative;
- unexpected transport exception suppression with one attempted request;
- `bind_collection_subject(...)` exact-ID guard using `subject_mismatch` for a valid different target;
- contract/security tests including proof that an app-only environment token is not used as user-context fallback.

The FR-005 canonical envelope is intentionally unchanged. Collection-side subject serialization remains deferred until FR-003/FR-004 integration.

## Validation still required before Draft PR

Authoritative operator validation must use an exact checkout of the current GitHub branch head and record at least:

- full `tests/` regression, including FR-001/002/005/006 and authenticated-subject tests;
- `git diff --check origin/main...HEAD`;
- exact branch/head identity;
- clean verification worktree;
- final canonical working directory, branch, HEAD, status, and log path.

The validation wrapper must fail closed if the final working directory is not `C:\Users\oimus\x-context`, if branch/head are unexpected, if status is dirty, or if the verification log was not created/non-empty. On Windows PowerShell 5.1, native command success is governed by `$LASTEXITCODE`; merge native stderr inside `cmd.exe` before piping to PowerShell when capturing unittest output.

## Adversarial review focus

Before Draft PR/Ready consideration, explicitly inspect:

- no implicit app-only -> user-context credential fallback;
- `/users/me` is the sole identity authority in this slice;
- no identity inference from token contents, caller target, username cache, or local config;
- subject requires a valid ASCII-decimal ID; username is optional and cannot become arbitrary provider passthrough;
- malformed/ambiguous provider states fail closed;
- 404 from authenticated-user lookup is not fabricated into `resource_unavailable` semantics;
- token, Authorization header, raw body, arbitrary headers, and transport exception text cannot escape through normal error/repr/chaining paths;
- same-subject binding is local and exact; mismatch occurs before a collection request;
- `/users/me` request accounting remains available for later NFR-005 collection aggregation;
- no bookmarks/likes, token refresh/storage, OAuth browser ceremony, persistence, mutation, or unofficial fallback scope expansion occurred;
- FR-002/FR-006 `read` behavior remains compatible.

## Deferred work

After Issue #11 is completed, the accepted P0 order remains:

1. FR-003 bookmarks with same-subject and bounded one-page continuation;
2. FR-004 likes with same-subject and bounded one-page continuation.

OAuth user authorization UX/token refresh storage remains a separately specified concern rather than being silently pulled into this provider-boundary slice.

Product-level P1-P3 candidates remain governed by SPEC-0000 and are not implied by Issue #11.

## Recovery / first diagnostic entry points

- Issue #11.
- `docs/specs/0001-mvp.md`.
- `docs/specs/0001-authenticated-subject-clarification.md`.
- `docs/TEST_MATRIX.md`.
- `x_context/x_api.py`.
- `tests/test_authenticated_subject.py`.
- `tests/test_authenticated_subject_rate_usage.py`.

Compare the topic branch against `main` before review. Unit/contract tests use fake credentials and fake transports only. Any live `/users/me` smoke remains optional and requires an intentional human decision because it touches real account identity and may consume API usage.

## Recent meaningful changes

See `CHANGELOG.md` for semantic history and Git/PRs for implementation detail.
