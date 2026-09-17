# x-context

`x-context` is an experimental, narrow Python tool and library for reading X content for local tooling and AI-assisted analysis. It uses the official X API and deliberately excludes scraping, browser-cookie reuse, and internal or unofficial API fallbacks.

The current product boundary is read-only. It normalizes successful results into a small canonical JSON envelope and emits separate structured diagnostics for operational visibility.

## Current capabilities

| Interface | Current behavior | Credential |
| --- | --- | --- |
| `read` | Parses a supported `x.com` or `twitter.com` Post URL and reads that single Post through the official API. | App-only Bearer Token |
| `bookmarks` | Resolves the authenticated user, binds the request to that subject, and reads at most one bookmark page. | Explicit env override or lifecycle-managed OAuth 2.0 user credential |
| `likes` | Resolves the authenticated user, binds the request to that subject, and reads at most one liked-Post page. | Explicit env override or lifecycle-managed OAuth 2.0 user credential |
| OAuth acquisition library | Runs one native/public-client Authorization Code + PKCE ceremony and returns the resulting token data in memory. | Client ID; no client secret |
| Credential lifecycle library | Explicit persistence, credential resolution, refresh-before-use, local deletion, and bounded single-token provider revoke. | Windows DPAPI `CurrentUser` protected store |

`bookmarks` and `likes` do not accept a target user ID. Each invocation may request one caller-sized page only: `--max-results` defaults to 25 and accepts 1 through 100. An optional `--page-token` continues from a token returned by a previous call; there is no implicit traversal or fetch-all mode.

## Credential model

- `read` obtains its app-only credential from `X_CONTEXT_BEARER_TOKEN`.
- `bookmarks` and `likes` first honor `X_CONTEXT_USER_ACCESS_TOKEN` as an explicit unmanaged compatibility/recovery override. If that variable is absent, they use the lifecycle-managed persisted credential. They never fall back to the app-only token.
- The environment override is never automatically persisted, refreshed, replaced, or revoked by the lifecycle provider.
- On Windows, the default lifecycle store is `%LOCALAPPDATA%\x-context\credential-v1.dpapi`. The complete versioned credential envelope is protected with Windows DPAPI `CurrentUser` and atomically replaced as one unit.
- Native/public-client acquisition in `x_context.oauth` accepts a Client ID and uses Authorization Code + PKCE with S256. It does not use or require a client secret.
- OAuth acquisition remains non-persistent by default. A successful ceremony returns an `OAuthTokenResult` in memory; persistence requires an explicit lifecycle call such as `persist_oauth_result(...)`.
- For persisted credentials with known expiry, collection resolution attempts refresh within the 300-second safety window. One resolution performs at most one refresh request, and a successful refresh must return both an access token and a replacement refresh token before the stored credential is replaced and used.
- Collection CLI refresh uses `X_CONTEXT_OAUTH_CLIENT_ID` as non-secret public-client configuration when refresh is actually required.
- Local delete and provider revoke are separate lifecycle operations. Provider revoke submits one token only, preferring the refresh token when present, and does not claim complete provider logout or token-family invalidation.

The command line still has no credential argument. Do not put credentials in command arguments, tracked files, examples, or retained logs.

OAuth acquisition, explicit persistence, local delete, and provider revoke are currently library operations rather than end-user CLI commands. The collection CLI can consume an already-persisted lifecycle credential automatically when no environment override is present.

## Usage

The repository currently defines no package installer or installed `x-context` console script. From the repository root, use the module entrypoint with a compatible Python interpreter after supplying the required credential through one of the supported credential paths:

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

- Product authority is read-only; there are no commands for posting, deleting posts, liking, bookmarking, following, or other X mutations.
- Bookmarks and liked-Post history are treated as private activity data. Collection results are process-and-return by default and are not persisted by the collection implementation.
- Lifecycle persistence stores only the explicitly committed protected credential envelope; it does not persist collection payloads.
- Credentials, authorization headers, raw provider responses, callback secrets, PKCE verifier/state values, protected-blob bytes, and private collection contents are excluded from normal diagnostics and retained validation evidence.
- Provider errors fail conservatively and never trigger scraping, cookie automation, browser automation, internal GraphQL, or another unofficial fallback.
- Collection pagination is caller-controlled and bounded to one provider page per invocation. No command silently retrieves all pages.
- OAuth acquisition is bounded to one listener, one browser launch, one terminal callback, and at most one token exchange per invocation; it has no automatic retry loop.
- Real provider refresh/revoke qualification is separate from synthetic contract tests and remains human-gated.

## Development and validation

Run the current project test suite from the repository root:

```console
python -m unittest discover -s tests -v
```

The current suite contains 163 tests covering URL parsing, official provider boundaries, canonical output, CLI behavior, authenticated-subject binding, OAuth acquisition, credential lifecycle, secret redaction, Windows DPAPI integration, and validation-workspace policy. The real-DPAPI integration test runs only on Windows and is skipped on non-Windows hosts by design.

The repository is public. Hosted GitHub Actions run `.github/workflows/project-ci.yml` and `.github/workflows/policy-check.yml` on pull requests, with project CI validating the proposed PR head rather than GitHub's synthetic merge commit. Windows exact-head validation is used when evidence must exercise the real DPAPI boundary. Current closeout evidence is summarized in `PROJECT_STATUS.md`.

## Status and limitations

`x-context` remains experimental. Its current canonical Post representation is intentionally small, and provider availability, entitlements, limits, and OAuth behavior are external facts that may change and must be re-verified when relevant.

There is still no stable end-user CLI for OAuth acquisition, explicit lifecycle persistence, local credential deletion, or provider revoke. Packaging and release/distribution are also not established. Real-provider refresh/revoke qualification remains a separate human decision.

Licensed under the MIT License. See LICENSE.
