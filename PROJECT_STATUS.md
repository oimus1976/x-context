# Project Status

> Keep this top block short enough to read in about 30 seconds.

## 30-second state

- **Goal:** Establish a read-only official-X-API context reader with specification-driven traceability and a broader staged personal-context roadmap.
- **Current phase:** Specification baseline and adversarial review (Issue #1, spec-only).
- **Last completed:** Review-0001 remediated the material pagination/usage/provenance gaps in SPEC-0001 and TEST_MATRIX.
- **Now working on:** Local/static validation of the amended specification contract and human review of P0 boundaries.
- **Next:** Verify local diff/evidence while GitHub Actions is unavailable; keep PR #2 Draft until the owner accepts the amended spec.
- **Human decision pending:** Accept the staged product scope plus the amended P0 pagination, usage, authority, and privacy boundaries before product implementation.
- **Main risks:** Private activity data, credentials, X API/platform dependency, usage cost/spec drift.
- **Required comprehension level:** C1

## Current authority summary

See `PROJECT_PROFILE.toml`; baseline rules live only in `BASELINE.md`.

- Planning: GitHub Issues and accepted specs/ADRs
- Execution: Git topic branches and pull requests
- Source code: Git
- Private/actual data: Local runtime only; not repository/PR/CI artifacts by default
- CI evidence: GitHub Actions when available; currently unavailable because the monthly Actions-minute quota is exhausted. Do not infer CI success from queued/unstarted runs.
- Production/deployed state: N/A during experimental MVP

## Current risk facets

- PRIVATE_DATA
- CREDENTIALS
- PLATFORM_DEPENDENT

Default project risk level: `ELEVATED`.

## Validated facts

- Repository: `oimus1976/x-context`.
- Initial `main` commit: `a25fc4bd957d3c150837071765653111c9ee30b4`.
- Issue #1 defines a spec-only bootstrap contract.
- Current specification branch: `spec/issue-1-mvp-contract`.
- SPEC-0000 records the broader read-only personal X context product direction and staged P0-P3 capability map.
- SPEC-0001 defines only the P0 implementation slice: arbitrary post read, authenticated bookmarks, and authenticated likes.
- Review-0001 identified two MAJOR gaps (unbounded/undefined pagination continuation and non-normative usage handling), one MODERATE provenance gap, and one MINOR capability-map omission.
- The MAJOR and MODERATE findings are remediated in SPEC-0001/TEST_MATRIX: one-page bounded collection reads, explicit continuation, default 25 / product cap 100, `usage_blocked`, normative usage observability, and UTC `retrieved_at`.
- Bookmark-folder support remains a non-blocking P1 candidate gap; it is not authorized in P0.
- ADR-0003 proposes official-X-API-only acquisition.
- ADR-0004 proposes a read-only authentication/product authority boundary.
- Current official X documentation was checked during Review-0001 for pay-per-use/Owned Reads and Bookmark Folders, but those external platform facts are not frozen as durable product constants.
- GitHub Actions is not usable at present because the account monthly Actions-minute quota has been exhausted; local/static validation is required and CI success must not be claimed.

## Current implementation scope

No product implementation is authorized by Issue #1.

Current deliverables are documentation/configuration only:

- `docs/specs/0000-product-scope.md`
- `docs/specs/0001-mvp.md`
- `docs/TEST_MATRIX.md`
- `docs/adr/0003-official-x-api-boundary.md`
- `docs/adr/0004-read-only-auth-boundary.md`
- `docs/reviews/0001-spec-adversarial-review.md`
- project-specific `PROJECT_PROFILE.toml`
- this status record
- semantic CHANGELOG entry

## Known limitations / residual risks

- X API pricing, endpoint availability, scopes, Owned Read qualification, billing behavior, and rate-limit semantics are external and may change.
- SPEC-0000 deliberately records capability categories rather than freezing endpoint names/prices as durable facts; these must be re-verified when promoted into implementation specs.
- Review-0001 intentionally does not specify an exact monetary-cost calculator; a future exact-cost feature requires a verified pricing source/freshness contract.
- Bookmark Folders are visible in current official documentation but are not yet represented in SPEC-0000 P1; this omission is non-blocking for P0 and should be revisited when P1 is prioritized.
- The current project profile declares but does not yet independently verify branch protection / required CI enforcement.
- GitHub Actions is currently unavailable due to exhausted monthly Actions minutes; this is an evidence-availability limitation, not evidence of test failure or success.
- Real-boundary smoke requires live credentials and must not expose tokens or private bookmark/like payloads.

## Deferred work

Product-level candidates preserved in SPEC-0000 but not authorized by SPEC-0001 include:

- own-post reads and mentions;
- followers/following and list-related reads;
- blocks and mutes;
- Markdown/Obsidian export and user-controlled persistence;
- LLM summarization/classification/context retrieval;
- AI/agent consumers of normalized X context;
- background monitoring or automation.

Explicitly outside the intended direction absent a future product-level decision:

- any X write operation;
- silent unofficial acquisition fallback;
- DM access (including read) without a separate privacy/necessity decision.

## Recovery / first diagnostic entry points

- First place to inspect on failure: `PROJECT_STATUS.md`, then `docs/specs/0000-product-scope.md`, `docs/specs/0001-mvp.md`, `docs/reviews/0001-spec-adversarial-review.md`, relevant ADRs, and the active Issue/PR.
- Rollback/recovery entry point: Git history and the previous accepted specification/ADR state; do not bypass official-API/read-only boundaries as a recovery shortcut.
- Data/source that must not be overwritten: Local credentials and private X activity data; they are not repository state.

## Recent meaningful changes

See `CHANGELOG.md` for semantic history and Git/PRs for implementation detail.
