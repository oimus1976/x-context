# x-context

`x-context` is an experimental, read-only X context reader for local tooling and AI-assisted analysis. It uses the official X API only and keeps authentication, private activity data, pagination, diagnostics, and fallback behavior inside narrow fail-closed boundaries.

## Current capabilities

The current MVP supports:

- reading one X post from a supported `https://x.com/.../status/<id>` or supported Twitter status URL;
- reading one bounded page of the authenticated user's bookmarks;
- reading one bounded page of the authenticated user's liked posts;
- resolving the authenticated user through the official `/2/users/me` boundary before personal collection access;
- acquiring a user-context access token through an OAuth 2.0 Authorization Code + PKCE public-client flow in `x_context.oauth`.

OAuth acquisition currently stops at an in-memory token result. It is not exposed as a CLI command, does not persist credentials, does not automatically refresh them, and does not change the existing runtime token source used by `bookmarks` and `likes`.

## Authority and safety boundaries

`x-context` is intentionally read-only.

- Official X API endpoints only.
- No scraping, internal GraphQL, browser-cookie fallback, or OAuth 1.0a fallback.
- No X write operations.
- Personal collections are bound to the authenticated subject; arbitrary target-user collection reads are not part of the MVP.
- Collection reads are bounded to one provider page per invocation. There is no implicit fetch-all behavior.
- Credentials, authorization codes, PKCE verifier/state material, raw provider responses, and opaque continuation tokens are excluded from normal diagnostics and retained validation evidence.
- Private collection contents stay in local runtime output and are not repository/PR/CI artifacts by default.

See `docs/specs/`, `docs/adr/`, and `docs/TEST_MATRIX.md` for the normative product and verification contracts.

## Requirements

- Python 3.11+
- An X API application with the permissions/scopes required for the operation being used

The repository currently runs directly from source; packaging and release artifacts are not yet specified.

## CLI

Run commands from the repository root with:

```text
python -m x_context <command> ...
```

### Read one post

Set `X_CONTEXT_BEARER_TOKEN` in the process environment, then run:

```text
python -m x_context read https://x.com/example/status/1234567890
```

Successful canonical JSON is written to stdout. Safe usage diagnostics are written separately to stderr.

### Read bookmarks

Set `X_CONTEXT_USER_ACCESS_TOKEN` in the process environment, then run:

```text
python -m x_context bookmarks
python -m x_context bookmarks --max-results 50
```

### Read liked posts

```text
python -m x_context likes
python -m x_context likes --max-results 50
```

`--max-results` is bounded to 1..100 and defaults to 25. `--page-token` may be supplied explicitly for one continuation page. The CLI does not automatically traverse all pages.

Do not put live credentials on the command line, in committed files, test fixtures, Issue/PR text, or retained validation logs.

## OAuth acquisition

`x_context.oauth` implements the native/public-client OAuth 2.0 Authorization Code + PKCE acquisition boundary:

- fixed registered IPv4 loopback callback on `127.0.0.1`;
- fresh state and PKCE verifier for each bounded attempt;
- S256 PKCE only;
- external system browser after the loopback listener binds;
- one validated callback and one token exchange;
- no client secret;
- read scopes only for the current MVP;
- optional `offline.access` only when refresh-capable acquisition is explicitly requested;
- in-memory token result only.

The OAuth module has been qualified against the real provider for the non-refresh-capable read-scope flow. No credential values or raw ceremony data are retained in repository evidence.

## Development and validation

Run the product regression suite:

```text
python -m unittest discover -s tests -v
```

Run the repository structural policy check:

```text
python scripts/verify_repo.py --repository oimus1976/x-context
```

Before a change is treated as validated, the project uses exact-head evidence, `git diff --check`, a clean verification worktree, and fail-closed final-state checks. The Windows validation runner is `scripts/Invoke-XContextValidation.ps1`.

Raw local verification logs belong under project-local `logs/verification/` and are ignored by Git. When public evidence is needed, publish only a sanitized summary containing no credentials, private X content, callback material, or machine-specific paths.

GitHub Actions uses read-only repository permissions, SHA-pinned actions, and non-persistent checkout credentials. `project-ci` runs the x-context product tests for pushes and ordinary pull requests; the inherited `policy-check` workflow verifies repository governance/structure.

## Project state

The repository is experimental. FR-001 through FR-006, authenticated-subject binding, bookmarks, likes, and bounded OAuth acquisition are implemented. Secure credential persistence, automatic token refresh, revoke/logout, packaging/releases, write operations, and unofficial provider fallbacks remain outside the current implemented scope.

Current implementation/governance state is summarized in `PROJECT_STATUS.md`.

## License

No repository license has been selected yet. A license file will be added only after an explicit owner decision.
