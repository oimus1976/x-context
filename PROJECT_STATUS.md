# Project Status

> Keep this top block short enough to read in about 30 seconds.

## 30-second state

- **Goal:** Establish a read-only official-X-API context reader with specification-driven traceability and a broader staged personal-context roadmap.
- **Current phase:** P0 implementation, FR-006 `read` CLI (Issue #9).
- **Last completed:** Issue #7 / PR #8 (FR-002 official single-Post lookup), merged to `main` at `1b958ee2bec458ef764818b8a5650511490e418f`; post-merge FR-001 + FR-002 + FR-005 regression was 31/31 PASS.
- **Now working on:** `issue-9-fr006-read-cli`, composing FR-001 -> FR-002 -> FR-005 into the first CLI vertical slice with safe NFR-005 diagnostics.
- **Next:** run authoritative local regression and exact-head validation from the GitHub branch; remediate any failures before Draft PR.
- **Human decision pending:** Ready / merge remain human-final.
- **Main risks:** credential/raw-provider leakage through CLI diagnostics or traceback; accidental canonical-schema pollution by provider metadata; validation must not confuse PowerShell native stderr rendering with process failure.
- **Required comprehension level:** C1

## Current authority summary

See `PROJECT_PROFILE.toml`; baseline rules live only in `BASELINE.md`.

- Planning: GitHub Issues and accepted specs/ADRs.
- Execution: Git topic branches and pull requests.
- Source code/current shared state: GitHub.
- Private/actual data: local runtime only; not repository/PR/CI artifacts by default.
- CI evidence: GitHub Actions when available; monthly Actions minutes are currently exhausted. Queued/unstarted jobs are not code-test results.
- Production/deployed state: N/A during experimental MVP.

## Current risk facets

Persistent project facets:

- PRIVATE_DATA
- CREDENTIALS
- PLATFORM_DEPENDENT

Default project risk level: `ELEVATED`.

Issue #9 adds a user-facing CLI boundary around an existing credential-bearing official-provider read. It does not add write authority, private-activity collection reads, browser/cookie access, unofficial providers, persistence, or OAuth user-flow implementation.

## Verified starting point

- Repository: `oimus1976/x-context`.
- Issue #7 is closed/completed.
- PR #8 is merged.
- Current `main` at Issue #9 start: `1b958ee2bec458ef764818b8a5650511490e418f`.
- Completed dependencies: FR-001 URL parsing, FR-002 official single-Post lookup, FR-005 minimal canonical `read` envelope.
- The FR-002 compatibility contract remains `lookup_post(...) -> CanonicalEnvelope`.
- X platform prices, current numeric rate limits, monthly caps, and Owned Read rules remain external facts and are not product constants.

## Issue #9 contract

The first FR-006 slice implements the logical command:

```text
x-context read <x-status-url>
```

Current implementation mechanism includes `python -m x_context read <x-status-url>`; packaging/console-script wiring remains an implementation-detail decision as allowed by SPEC-0001.

The slice is constrained to:

- URL input only; no direct Post-ID CLI path;
- `X_CONTEXT_BEARER_TOKEN` environment-variable credential input only;
- FR-001 ID extraction followed by the FR-002 provider boundary;
- FR-005 canonical JSON only on stdout;
- non-secret usage/error diagnostics only on stderr;
- exit `0` success, `2` local/parser/input/configuration failure, `3` provider/read failure;
- existing stable error categories for the fine-grained cause;
- NFR-005 diagnostics for operation, provider requests attempted, returned item count, continuation state, and safe allow-listed rate metadata;
- no fabricated requested-page-size value for `read`.

The normative Issue #9 clarification is recorded in `docs/specs/0001-fr006-read-clarification.md` and mapped in `docs/TEST_MATRIX.md`. It narrows only the first `read` slice and does not implement the deferred bookmarks/likes CLI portions.

## Current implementation state

Branch `issue-9-fr006-read-cli` currently adds:

- `x_context/cli.py` with an injectable/testable `main(...)`;
- `x_context/__main__.py` module entry point;
- a compatible `lookup_post_with_diagnostics(...)` provider path while retaining `lookup_post(...) -> CanonicalEnvelope`;
- success-path allow-listed rate metadata outside the canonical model;
- provider-request attempt counting on success and failure;
- fail-closed suppression of arbitrary transport exception text;
- FR-006 CLI contract and security tests.

A reconstructed targeted check of the new CLI behavior passed eight representative cases, including success, local rejection, credential rejection, provider categories, allow-listed rate metadata, parser secret non-echo, and unexpected transport exception redaction. This check is an early implementation sanity check only; it is **not** authoritative exact-head evidence because it was not executed from an exact GitHub checkout.

## Validation still required before Draft PR

Authoritative operator validation must use an exact checkout of the current GitHub branch head and record at least:

- FR-001 tests;
- FR-002 tests;
- FR-005 tests;
- FR-006 CLI/security tests;
- `git diff --check origin/main...HEAD`;
- exact branch/head identity;
- clean working tree after validation.

On Windows PowerShell 5.1, native process success is governed by `$LASTEXITCODE`. If unittest stderr is merged into a log, merge it inside `cmd.exe` before piping to PowerShell to avoid the known false-positive `NativeCommandError` pattern.

## Adversarial review focus

Before Ready consideration, explicitly inspect:

- stdout contains canonical JSON only on success;
- stderr cannot contain Bearer Token, Authorization header, raw response body, arbitrary provider header values, or underlying transport exception text;
- invalid URL, provider-incompatible ID, and local credential failure report zero provider requests;
- provider failures after transport report one attempted request;
- direct Post-ID and token CLI arguments are not accepted;
- rate metadata is allow-listed and absent values are not fabricated into numeric facts;
- provider diagnostics do not enter FR-005 canonical JSON;
- `lookup_post(...)` callers remain behaviorally compatible;
- no bookmarks/likes, authenticated-subject, persistence, optional canonical-field, pricing, scraping/browser/cookie/internal-GraphQL, or OAuth-user-flow scope expansion occurred.

## Deferred work

After FR-006 `read` is completed, the accepted preferred P0 order remains:

1. authenticated-subject resolution/binding contract;
2. FR-003 bookmarks;
3. FR-004 likes.

Product-level P1-P3 candidates remain governed by SPEC-0000 and are not implied by Issue #9.

## Recovery / first diagnostic entry points

- Issue #9.
- `docs/specs/0001-mvp.md`.
- `docs/specs/0001-fr006-read-clarification.md`.
- `docs/TEST_MATRIX.md`.
- `x_context/cli.py`.
- `x_context/x_api.py`.
- `tests/test_fr006_read_cli.py`.
- `tests/test_fr006_security.py`.

Compare the topic branch against `main` before review. Use fake credentials for deterministic validation; any live X API smoke remains optional and requires an intentional human decision because it may consume paid usage.

## Recent meaningful changes

See `CHANGELOG.md` for semantic history and Git/PRs for implementation detail.
