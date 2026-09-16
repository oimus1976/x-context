# Project Status

## 30-second state

- **Goal:** Read X content through the official X API for local tooling and AI-assisted analysis while preserving a narrow read-only authority boundary.
- **Completed foundation:** OAuth 2.0 Authorization Code + PKCE acquisition was merged by PR #24. Its merge commit is `dec7b8c537dd8d5079db3402fe4af691bdf95107`.
- **OAuth closeout evidence:** 140/140 tests passed; canonical `main` was clean and its `HEAD` matched `origin/main` at that closeout point.
- **Public-readiness workstream:** Audit Issue #25 and remediation Issue #28 / PR #29 are completed.
- **Repository state:** `oimus1976/x-context` is public. Current publication baseline at this closeout is `main@c2dfb8bbf739d8d13db275531ead88e430d4aa31`.
- **Public hosted CI:** `project-ci` and `policy-check` completed successfully on `main@c2dfb8bbf739d8d13db275531ead88e430d4aa31` after publication.
- **Superseded workstream:** Issue #26 and Draft PR #27 were closed without merge after Issue #28 / PR #29 became the completed remediation path.
- **Next candidate workstream:** credential lifecycle, as a separate Issue after this documentation closeout.
- **Human decisions:** Ready, merge, destructive cleanup, and any future authority expansion remain human-final.

## Completed OAuth work

The native/public-client OAuth acquisition work formerly tracked by Issue #23 is merged and is no longer the active implementation workstream. The merged boundary provides:

- fixed IPv4 loopback callback handling on `127.0.0.1`;
- fresh state and PKCE verifier per attempt with S256 only;
- listener bind before external system-browser launch;
- bounded callback validation and one official authorization-code token exchange;
- in-memory token results with secret-bearing values excluded from normal logs and representations;
- no client secret, secure persistence, automatic refresh, revoke/logout, clipboard, or parent-environment mutation.

The authoritative post-merge OAuth validation recorded 140/140 tests passing with clean canonical `main` synchronized to `origin/main`. The later intentional real-provider qualification also passed for the non-refresh-capable public-client flow. These are historical closeout facts for the OAuth acquisition slice; they are not claims about a completed credential lifecycle.

## Completed public-readiness work

Issue #25 provided the public-readiness audit/control plane. Issue #28 / PR #29 provided the current-tree remediation that was ultimately merged.

Completed publication-readiness outcomes include:

- public-facing `x-context` README and project identity;
- publication-safe validation workspace configuration and neutral validation fixtures;
- raw local verification logs kept outside source control;
- project CI and policy-check workflows with least-privilege/fork-safe design;
- MIT License selected by the human owner and recorded in root `LICENSE`;
- publication review and final visibility change completed;
- repository visibility is now public;
- public hosted `project-ci` and `policy-check` both succeeded on `main@c2dfb8bbf739d8d13db275531ead88e430d4aa31`.

Issue #26 / Draft PR #27 were an earlier remediation attempt and are closed without merge as superseded by the completed Issue #28 / PR #29 path.

## Next candidate: credential lifecycle

The next candidate implementation workstream is the credential lifecycle deferred by Issue #23. It should be specified in a new Issue before implementation and should cover at least:

- secure Windows credential persistence, including an explicit Windows Credential Manager vs DPAPI-backed storage decision;
- secure persistence schema and atomic credential replacement;
- refresh-before-use behavior;
- re-verification of current X refresh-token rotation/reuse semantics before encoding any provider-specific assumptions;
- migration from manual `X_CONTEXT_USER_ACCESS_TOKEN` injection to a secure credential provider, with an explicit compatibility/recovery path if retained;
- revoke/logout behavior;
- deletion and recovery semantics.

This status document does not authorize or specify those behaviors. Requirement -> AC -> Test -> Implementation remains the required workflow.

## Authority and safety boundaries

- GitHub Issues own planning and workstream state; Git commits own repository content and exact revisions.
- The official X API remains the only supported data boundary; unofficial scraping, browser-cookie, and internal-GraphQL fallbacks remain excluded.
- Actual credentials and private X data remain local runtime inputs and must not enter repository, Issue/PR, CI, or retained validation artifacts.
- The current OAuth acquisition slice does not persist credentials or automatically refresh them.
- No refresh-token rotation/reuse contract is assumed until current provider behavior is re-verified and specified in the credential-lifecycle workstream.
- The MIT License is recorded in root `LICENSE`.
- Branch protection, rulesets, and external-fork governance should be described as enforced only when separately verified from GitHub platform state.
- Ready and merge remain separate human-final gates. Passing implementation, tests, review, or CI does not authorize either effect.
- Destructive cleanup and future authority expansion remain human-final.

## Validation state

Historical OAuth closeout evidence:

- 140/140 tests passed at OAuth post-merge closeout;
- exact canonical `main` matched `origin/main` at that closeout;
- real non-refresh-capable OAuth qualification passed without retaining secret material.

Public-readiness remediation evidence before publication reported:

- full project suite: 142/142 passed;
- `python scripts/verify_repo.py --repository "oimus1976/x-context"`: passed;
- `git diff --check`: passed;
- R3/R4 independent review: final `MUST_FIX=0`;
- R6 fork-safety review: `MUST_FIX=0`.

Post-publication hosted evidence now additionally confirms:

- `project-ci`: success on `main@c2dfb8bbf739d8d13db275531ead88e430d4aa31`;
- `policy-check`: success on `main@c2dfb8bbf739d8d13db275531ead88e430d4aa31`.

This Issue #30 change is documentation-only and must still follow the normal exact-head validation and human Ready / merge gates before merge.

## Recovery / first diagnostic entry points

- Confirm the current workstream and acceptance criteria in GitHub Issue #30 until this closeout merges; after merge, re-read open Issues before starting new work.
- Confirm local execution state with `git branch --show-current`, `git rev-parse HEAD`, `git status --short`, and `git diff --cached --name-only` before editing or recovery.
- Use `docs/TEST_MATRIX.md` for requirement-to-test traceability and `scripts/verify_repo.py` for baseline repository-policy checks.
- For OAuth acquisition behavior, start with `docs/specs/0002-oauth-acquisition-clarification.md`, `x_context/oauth.py`, `tests/test_oauth_acquisition.py`, and `tests/test_oauth_acquisition_security.py`.
- For validation workspace behavior, start with `scripts/validation_workspace.py`, `tests/test_validation_workspace.py`, and `tests/test_validation_runner_contract.py`.
- Preserve unaccounted local work and fail closed on uncertain credentials, private-data exposure, destructive cleanup, publication, or governance state.
