# x-context

`x-context` is an experimental, narrow Python tool and library for reading X content for local tooling and AI-assisted analysis. It uses the official X API and deliberately excludes scraping, browser-cookie reuse, and internal or unofficial API fallbacks.

The current product boundary is read-only. It normalizes successful results into a small canonical JSON envelope and emits separate structured diagnostics for operational visibility.

## Current capabilities

| Interface | Current behavior | Credential |
| --- | --- | --- |
| `read` | Parses a supported `x.com` or `twitter.com` Post URL and reads that single Post through the official API. | App-only Bearer Token |
| `bookmarks` | Resolves the authenticated user, binds the request to that subject, and reads at most one bookmark page. | OAuth 2.0 user access token |
| `likes` | Resolves the authenticated user, binds the request to that subject, and reads at most one liked-Post page. | OAuth 2.0 user access token |
| OAuth acquisition library | Runs one native/public-client Authorization Code + PKCE ceremony and returns the resulting token data in memory. | Client ID; no client secret |

`bookmarks` and `likes` do not accept a target user ID. Each invocation may request one caller-sized page only: `--max-results` defaults to 25 and accepts 1 through 100. An optional `--page-token` continues from a token returned by a previous call; there is no implicit traversal or fetch-all mode.

## Credential model

- `read` obtains its app-only credential from `X_CONTEXT_BEARER_TOKEN`.
- `bookmarks` and `likes` obtain their user-context credential from `X_CONTEXT_USER_ACCESS_TOKEN`. They never fall back to the app-only token.
- The command line has no credential argument. Supply credentials to the process environment through an appropriate local secret-management or shell-session mechanism; do not put them in command arguments, tracked files, examples, or retained logs.
- Native/public-client acquisition in `x_context.oauth` accepts a Client ID and uses Authorization Code + PKCE with S256. It does not use or require a client secret.

OAuth acquisition is currently a library boundary, not a CLI command or a complete credential lifecycle. A successful ceremony returns an `OAuthTokenResult` in memory; it does not persist the token or set `X_CONTEXT_USER_ACCESS_TOKEN` for collection commands.

The current OAuth implementation does not provide persistent token storage, Windows Credential Manager integration, automatic refresh, refresh-token rotation, revoke/logout, clipboard export, or parent-shell environment mutation. Refresh-capable acquisition can be requested explicitly at the library boundary, but storage, replacement, and refresh execution are not implemented.

## Usage

The repository currently defines no package installer or installed `x-context` console script. From the repository root, use the module entrypoint with a compatible Python interpreter after supplying the required environment credential outside the command line:

```console
python -m x_context read "https://x.com/example/status/1234567890"
python -m x_context bookmarks
python -m x_context bookmarks --max-results 50
python -m x_context likes --max-results 25
python -m x_context likes --page-token "<token-from-a-previous-page>"
```

On success, stdout contains one canonical JSON document. Structured usage diagnostics are written separately to stderr. Handled failures leave stdout empty and report a stable error category on stderr.

Canonical output identifies the schema version, source, operation, retrieval time, normalized Post items, and page state. Personal-collection output also includes the authenticated subject and may include a continuation token for an explicit later invocation.

## Safety and privacy boundaries

- Product authority is read-only; there are no commands for posting, deleting, liking, bookmarking, following, or other X mutations.
- Bookmarks and liked-Post history are treated as private activity data. Collection results are process-and-return by default and are not persisted by the current implementation.
- Credentials, authorization headers, raw provider responses, callback secrets, PKCE verifier/state values, and private collection contents are excluded from normal diagnostics and retained validation evidence.
- Provider errors fail conservatively and never trigger scraping, cookie automation, browser automation, internal GraphQL, or another unofficial fallback.
- Collection pagination is caller-controlled and bounded to one provider page per invocation. No command silently retrieves all pages.
- OAuth acquisition is bounded to one listener, one browser launch, one terminal callback, and at most one token exchange per invocation; it has no automatic retry loop.

## Development and validation

Run the current project test suite from the repository root:

```console
python -m unittest discover -s tests -v
```

The suite currently contains 142 tests covering URL parsing, official provider boundaries, canonical output, CLI behavior, authenticated-subject binding, credential and diagnostic redaction, OAuth acquisition, and validation-workspace policy.

Repository policy tooling also exists in `scripts/verify_repo.py`, but project-specific public CI and fork-safety readiness remain open work. Do not treat local test success or the starter policy workflow as evidence that project CI is operational.

## Status and limitations

`x-context` remains experimental. Its current canonical Post representation is intentionally small, and provider availability, entitlements, limits, and OAuth behavior are external facts that may change and must be re-verified when relevant.

The OAuth module has no stable CLI wrapper or persistent credential-provider integration. Packaging, release status, public CI readiness, and final repository publication controls are not established by this README.

License: not yet selected.
