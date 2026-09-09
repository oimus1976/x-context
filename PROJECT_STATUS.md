# Project Status

> Keep this top block short enough to read in about 30 seconds.

## 30-second state

- **Goal:** Establish a read-only official-X-API context reader with specification-driven traceability.
- **Current phase:** Specification baseline (Issue #1, spec-only).
- **Last completed:** Repository bootstrap from ai-dev-starter and initial SPEC-0001/ADR/test-matrix draft.
- **Now working on:** Review and validation of the MVP specification contract.
- **Next:** Open a spec-only Draft PR, review the contract, then implement the first vertical slice only after human acceptance.
- **Human decision pending:** Accept the MVP scope and authority/privacy boundaries before product implementation.
- **Main risks:** Private activity data, credentials, X API/platform dependency, usage cost/spec drift.
- **Required comprehension level:** C1

## Current authority summary

See `PROJECT_PROFILE.toml`; baseline rules live only in `BASELINE.md`.

- Planning: GitHub Issues and accepted specs/ADRs
- Execution: Git topic branches and pull requests
- Source code: Git
- Private/actual data: Local runtime only; not repository/PR/CI artifacts by default
- CI evidence: GitHub Actions once implementation bootstrap defines checks
- Production/deployed state: N/A during experimental MVP

## Current risk facets

- PRIVATE_DATA
- CREDENTIALS
- PLATFORM_DEPENDENT

Default project risk level: `ELEVATED`.

## Validated facts

- Repository: `oimus1976/x-context`.
- Initial `main` commit: `a25fc4bd957d3c150837071765653111c9ee30b4`.
- Issue #1 defines a spec-only MVP contract.
- Current specification branch: `spec/issue-1-mvp-contract`.
- SPEC-0001 limits the MVP to arbitrary post read, authenticated bookmarks, and authenticated likes.
- ADR-0003 proposes official-X-API-only acquisition.
- ADR-0004 proposes a read-only authentication/product authority boundary.

## Current implementation scope

No product implementation is authorized by Issue #1.

Current deliverables are documentation/configuration only:

- `docs/specs/0001-mvp.md`
- `docs/TEST_MATRIX.md`
- `docs/adr/0003-official-x-api-boundary.md`
- `docs/adr/0004-read-only-auth-boundary.md`
- project-specific `PROJECT_PROFILE.toml`
- this status record
- semantic CHANGELOG entry

## Known limitations / residual risks

- X API pricing, endpoint availability, scopes, and rate-limit semantics are external and may change.
- The current project profile declares but does not yet independently verify branch protection / required CI enforcement.
- Real-boundary smoke requires live credentials and must not expose tokens or private bookmark/like payloads.
- Canonical JSON details beyond SPEC-0001 remain intentionally unimplemented and may need refinement during review before code work.

## Deferred work

- Product code and packaging.
- OAuth implementation details and credential-store choice.
- Mentions/lists/followers/following access.
- Markdown/Obsidian export.
- LLM enrichment.
- Background monitoring or automation.
- Any X write operation.
- Any unofficial X acquisition provider.

## Recovery / first diagnostic entry points

- First place to inspect on failure: `PROJECT_STATUS.md`, then `docs/specs/0001-mvp.md`, relevant ADRs, and the active Issue/PR.
- Rollback/recovery entry point: Git history and the previous accepted specification/ADR state; do not bypass official-API/read-only boundaries as a recovery shortcut.
- Data/source that must not be overwritten: Local credentials and private X activity data; they are not repository state.

## Recent meaningful changes

See `CHANGELOG.md` for semantic history and Git/PRs for implementation detail.
