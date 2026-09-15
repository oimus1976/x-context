# Project Status

## 30-second state

- **Goal:** Read X content through the official X API for local tooling and AI-assisted analysis while preserving a narrow read-only authority boundary.
- **Completed foundation:** OAuth 2.0 Authorization Code + PKCE acquisition was merged by PR #24. Its merge commit and former `main` baseline is `dec7b8c537dd8d5079db3402fe4af691bdf95107`.
- **OAuth closeout evidence:** 140/140 tests passed; canonical `main` was clean and its `HEAD` matched `origin/main` at closeout.
- **Audit workstream:** Issue #25 is open as the public-readiness audit/control plane.
- **Current remediation:** Issue #28 is open on `issue-28-public-readiness-remediation`. R1-R6 are completed and committed; PR review and merge closeout remain outstanding.
- **Repository state:** The repository is still private. Audit evidence does not currently require a history rewrite.
- **Human decisions:** The human owner selected the MIT License. Private-to-public visibility, destructive branch cleanup, final branch-protection/ruleset/fork policy, Ready, and merge remain human-final.

## Completed OAuth work

The native/public-client OAuth acquisition work formerly tracked by Issue #23 is merged and is no longer the active implementation workstream. The merged boundary provides:

- fixed IPv4 loopback callback handling on `127.0.0.1`;
- fresh state and PKCE verifier per attempt with S256 only;
- listener bind before external system-browser launch;
- bounded callback validation and one official authorization-code token exchange;
- in-memory token results with secret-bearing values excluded from normal logs and representations;
- no client secret, secure persistence, automatic refresh, revoke/logout, clipboard, or environment mutation.

The authoritative post-merge validation recorded 140/140 tests passing with clean canonical `main` synchronized to `origin/main`. That evidence describes the OAuth merge closeout; it is not a claim about current public CI or a completed public transition.

## Public-readiness workstreams

Issue #25 owns the audit/control-plane workstream. Issue #28 owns current-tree remediation and does not authorize repository publication or any other human-final effect.

Issue #28 state:

- **R1 completed:** the starter README is replaced with public-facing `x-context` documentation.
- **R2 completed:** this operational status reflects the completed current-tree remediation state.
- **R3/R4 completed:** publication-safe validation workspace policy and neutral deterministic validation fixtures are committed at `cd883093f25ad1de5d072fe667e3d5b1a39b4a13`.
- **R5 completed:** The human owner selected the MIT License; root `LICENSE` and README license wording are committed at `42d247d7f3a9dbfd0adb2311b806234b3cbbda92`.
- **R6 completed locally:** the project CI and fork-safety workflow is committed. Hosted CI has not been qualified because GitHub Actions execution is currently unavailable while the repository remains private.

Issue #28 remains open until PR review and merge closeout. The hosted failures on PR #29 are classified as execution-blocked, not as test or workflow failure evidence. No current evidence establishes successful hosted CI, public repository visibility, or enforced branch protection or rulesets. After remediation is merged, Issue #25 must refresh the public-readiness audit against then-current `main` before a later human-final visibility decision.

## Authority and safety boundaries

- GitHub Issues own planning and workstream state; Git commits own repository content and exact revisions.
- The official X API remains the only supported data boundary; unofficial scraping, browser-cookie, and internal-GraphQL fallbacks remain excluded.
- Actual credentials and private X data remain local runtime inputs and must not enter repository, Issue/PR, CI, or retained validation artifacts.
- History rewrite is not currently required by audit evidence. Any later destructive history or branch cleanup decision remains human-final.
- The human owner selected the MIT License, recorded in root `LICENSE`; no license is implied by repository availability.
- Final branch protection, ruleset, and external-fork policy are unresolved human decisions and must not be described as enforced without platform verification.
- Ready and merge are separate human-final gates. Passing implementation, tests, or review does not authorize either effect.

## Validation state

Completed local remediation evidence reports:

- full project suite: 142/142 passed;
- `python scripts/verify_repo.py --repository "oimus1976/x-context"`: passed;
- `git diff --check`: passed;
- R3/R4 independent review: final `MUST_FIX=0`;
- R6 fork-safety review: `MUST_FIX=0`.

These local results do not establish hosted CI success. GitHub Actions execution is currently unavailable while the repository remains private, and the hosted failures on PR #29 are execution-blocked rather than evidence that the tests or workflow failed. Ready and merge remain human-final. Publication remains under Issue #25 and requires a later, separate human-final visibility decision.

## Recovery / first diagnostic entry points

- Confirm workstream authority and current acceptance criteria in GitHub Issues #25 and #28.
- Confirm local execution state with `git branch --show-current`, `git rev-parse HEAD`, `git status --short`, and `git diff --cached --name-only` before editing or recovery.
- Use `docs/TEST_MATRIX.md` for requirement-to-test traceability and `scripts/verify_repo.py` for baseline repository-policy checks.
- For OAuth acquisition behavior, start with `docs/specs/0002-oauth-acquisition-clarification.md`, `x_context/oauth.py`, `tests/test_oauth_acquisition.py`, and `tests/test_oauth_acquisition_security.py`.
- For validation workspace behavior, start with `scripts/validation_workspace.py`, `tests/test_validation_workspace.py`, and `tests/test_validation_runner_contract.py`.
- Preserve unaccounted local work and fail closed on uncertain credentials, private-data exposure, destructive cleanup, publication, or governance state.
