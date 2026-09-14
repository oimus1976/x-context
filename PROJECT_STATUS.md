# Project Status

## 30-second state

- **Goal:** Read-only official X API context reader with bounded personal collection access and safe native OAuth user-token acquisition.
- **Current work:** Issue #26, public-readiness remediation, on `issue-26-public-readiness-remediation`.
- **Current main baseline:** `dec7b8c537dd8d5079db3402fe4af691bdf95107` (OAuth PR #24 merge).
- **Implemented:** FR-001/002/003/004/005/006, authenticated-subject binding, bookmarks, likes, and native/public-client OAuth 2.0 Authorization Code + PKCE acquisition.
- **OAuth qualification:** Real provider qualification passed for the bounded non-refresh-capable read-scope flow; no secret values or raw ceremony data were retained.
- **Public-readiness audit:** Issue #25 found 0 Gitleaks findings in reachable patch history and in all 170 unique reachable blobs at the frozen baseline. No history rewrite is currently indicated by secret scanning.
- **Human decisions still required:** license selection, Ready, merge, destructive branch cleanup, history rewrite if ever proposed, branch/ruleset policy, and private -> public visibility change.

## Issue #26 scope

Issue #26 prepares the repository and mutable publication surfaces for a possible later public visibility change without expanding product authority.

Current remediation scope:

1. replace the inherited starter README with an x-context-specific public README;
2. remove workstation/user-specific absolute paths from tracked validation configuration while preserving fail-closed validation behavior;
3. make validation-workspace tests use synthetic/non-identifying paths;
4. keep raw local verification logs outside source control;
5. add project-specific read-only GitHub Actions regression CI suitable for ordinary pull requests and forks;
6. update project status/changelog to the post-OAuth/public-readiness state;
7. sanitize practical mutable Issue/PR metadata that exposes workstation-specific absolute paths.

License selection is intentionally excluded until the owner makes an explicit decision.

## Product authority boundary

The current implemented product remains read-only and official-API-only:

- `read <status-url>` performs one official single-Post lookup after strict local URL/Post-ID validation;
- `bookmarks` and `likes` resolve the authenticated subject first and then perform one bounded personal collection request;
- no arbitrary target-user collection CLI exists;
- no implicit multi-page traversal exists;
- no scraping, internal GraphQL, browser-cookie fallback, or X write authority exists;
- private collection contents are runtime data and are not retained as repository/PR/CI evidence by default.

## OAuth state

`x_context.oauth` implements the native/public-client Authorization Code + PKCE acquisition boundary:

- exact fixed IPv4 loopback redirect on `127.0.0.1`;
- fresh state and verifier per attempt;
- S256 only;
- listener bind before system-browser launch;
- exact callback path/state validation;
- one bounded authorization-code token exchange;
- no client secret or Basic authorization;
- read scopes only for the current MVP;
- optional `offline.access` only when explicitly requested;
- in-memory secret-bearing token result only;
- no persistence, automatic refresh, clipboard export, parent-environment mutation, or automatic retry loop.

The OAuth acquisition module is not yet exposed as a CLI command and does not replace the existing `X_CONTEXT_USER_ACCESS_TOKEN` runtime source used by `bookmarks` / `likes`.

## Security boundary

The following values must not enter committed files, normal stdout/stderr diagnostics, retained validation evidence, Issue/PR text, callback response pages, normal repr/debug strings, or controlled traceback chaining:

- access token;
- refresh token;
- authorization code;
- state;
- PKCE verifier;
- Authorization header material;
- raw token response;
- full callback query;
- private collection contents except intentional local runtime output.

Tests use fake/synthetic values only.

## Validation state

The merged OAuth baseline `main@dec7b8c537dd8d5079db3402fe4af691bdf95107` was authoritatively validated after merge:

- 140/140 tests passed;
- `TEST_EXIT=0`;
- `DIFF_EXIT=0`;
- exact verification worktree was clean;
- canonical `main == origin/main`;
- final working tree was clean;
- `FINAL_RESULT=PASS`.

Public-readiness audit evidence on that frozen baseline additionally established:

- reachable commits: 126;
- unique reachable blobs: 170;
- opaque/binary reachable blobs: 0;
- patch-history Gitleaks scan: PASS, 0 findings;
- blob-complete Gitleaks scan: PASS, 0 findings.

Issue #26 must receive a fresh exact-head regression, `git diff --check`, current-tree publication review, and independent/adversarial review before human Ready consideration.

## CI/publication state

The repository remains private during Issue #26. The inherited `policy-check` workflow uses read-only contents permission, SHA-pinned actions, non-persistent checkout credentials, and bounded timeouts. Issue #26 adds a dedicated `project-ci` workflow so x-context product tests run on ordinary `pull_request` and `push` to `main` without repository write authority or secret dependency.

Historical private-repository Actions runs that never executed jobs are recorded as execution-blocked evidence, not product-test failure evidence. Public-hosted CI must be re-qualified after any later visibility change.

## Next gates

1. validate the exact Issue #26 topic head locally;
2. perform independent/adversarial review of the remediation diff;
3. sanitize mutable GitHub publication metadata identified by Issue #25;
4. make the separate human license decision;
5. human Ready / merge;
6. re-freeze merged `main` and repeat final public-readiness audit;
7. only then consider the human-final private -> public visibility change;
8. after publication, verify hosted CI, branch/ruleset behavior, and external-fork workflow behavior before recording publication as verified.

## Recovery / first diagnostic entry points

When a development or validation session is interrupted, use GitHub as the shared-state authority and recover in this order:

1. confirm the intended Issue/PR workstream and fetch `origin`;
2. compare the current branch, `HEAD`, and the exact GitHub branch head before changing files;
3. run `git status --short --untracked-files=all` and stop on unexpected local state;
4. for validation failures, inspect the project-local `logs/verification/` evidence and the first failing command/exit code rather than inferring success from later output;
5. use `scripts/validation_workspace.py` to inspect/check configured workspace paths and `scripts/Invoke-XContextValidation.ps1` for authoritative Windows exact-head validation;
6. do not reset, clean, force-remove worktrees, rewrite history, delete branches, change visibility, or expose credentials as a recovery shortcut.

For product behavior failures, start with the matching test under `tests/` and the requirement mapping in `docs/TEST_MATRIX.md`. For OAuth/authentication failures, retain only redacted category/state evidence; never capture live tokens, authorization codes, PKCE verifier/state material, raw callback URLs, or private collection contents in durable diagnostics.
