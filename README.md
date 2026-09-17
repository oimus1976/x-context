# x-context

`x-context` is an experimental, narrow Python tool and library for reading X content for local tooling and AI-assisted analysis. It uses the official X API and deliberately excludes scraping, browser-cookie reuse, and internal or unofficial API fallbacks.

The current product boundary is read-only. It normalizes successful results into a small canonical JSON envelope and emits separate structured diagnostics for operational visibility.

## Current capabilities

| Interface | Current behavior | Credential |
| --- | --- | --- |
| `read` | Parses a supported `x.com` or `twitter.com` Post URL and reads that single Post through the official API. | App-only Bearer Token |
| `bookmarks` | Resolves the authenticated user, binds the request to that subject, and reads at most one bookmark page. | Explicit env override or lifecycle-managed OAuth 2.0 user credential |
| `likes` | Resolves the authenticated user, binds the request to that subject, and reads at most one liked-Post page. | Explicit env override or lifecycle-managed OAuth 2.0 user credential |
| `auth login` | Runs one native/public-client Authorization Code + PKCE ceremony and commits a refresh-capable credential to the lifecycle store after bounded validation. | Client ID + exact registered loopback redirect URI; no client secret |
| OAuth acquisition library | Runs one native/public-client Authorization Code + PKCE ceremony and returns the resulting token data in memory. | Client ID; no client secret |
| Credential lifecycle library | Explicit persistence, credential resolution, refresh-before-use, local deletion, and bounded single-token provider revoke. | Windows DPAPI `CurrentUser` protected store |

`bookmarks` and `likes` do not accept a target user ID. Each invocation may request one caller-sized page only: `--max-results` defaults to 25 and accepts 1 through 100. An optional `--page-token` continues from a token returned by a previous call; there is no implicit traversal or fetch-all mode.

## Credential model

- `read` obtains its app-only credential from `X_CONTEXT_BEARER_TOKEN`.
- `bookmarks` and `likes` first honor `X_CONTEXT_USER_ACCESS_TOKEN` as an explicit unmanaged compatibility/recovery override. If that variable is absent, they use the lifecycle-managed persisted credential. They never fall back to the app-only token.
- The environment override is never automatically persisted, refreshed, replaced, or revoked by the lifecycle provider.
- On Windows, the default lifecycle store is `%LOCALAPPDATA%\x-context\credential-v1.dpapi`. The complete versioned credential envelope is protected with Windows DPAPI `CurrentUser` and atomically replaced as one unit.
- Native/public-client acquisition in `x_context.oauth` accepts a Client ID and uses Authorization Code + PKCE with S256. It does not use or require a client secret.
- Generic OAuth acquisition remains non-persistent by default. A successful library ceremony returns an `OAuthTokenResult` in memory; persistence requires an explicit lifecycle call such as `persist_oauth_result(...)`.
- `auth login` is the bounded end-user composition of those existing boundaries. It reads `X_CONTEXT_OAUTH_CLIENT_ID` and `X_CONTEXT_OAUTH_REDIRECT_URI`, requests the existing P0 read scopes plus `offline.access`, and persists only after the normalized result contains both a refresh token and a positive expiry duration. It never imports `X_CONTEXT_USER_ACCESS_TOKEN` into managed storage.
- `X_CONTEXT_OAUTH_REDIRECT_URI` must exactly match the registered fixed loopback callback and the existing OAuth contract: `http://127.0.0.1:<fixed-registered-port>/<fixed-callback-path>`. The command does not silently change host, port, or callback path.
- For persisted credentials with known expiry, collection resolution attempts refresh within the 300-second safety window. One resolution performs at most one refresh request, and a successful refresh must return both an access token and a replacement refresh token before the stored credential is replaced and used.
- Collection CLI refresh uses `X_CONTEXT_OAUTH_CLIENT_ID` as non-secret public-client configuration when refresh is actually required.
- Local delete and provider revoke are separate lifecycle operations. Provider revoke submits one token only, preferring the refresh token when present, and does not claim complete provider logout or token-family invalidation.

The command line has no credential argument. Do not put credentials in command arguments, tracked files, examples, or retained logs.

Local credential deletion and provider revoke remain library operations rather than end-user CLI commands. The collection CLI consumes an already-persisted lifecycle credential automatically when no environment override is present.

## Usage

The repository currently defines no package installer or installed `x-context` console script. From the repository root, use the module entrypoint with a compatible Python interpreter.

For a lifecycle-managed personal-collection credential on Windows, configure the non-secret Native App values and run the bootstrap command:

```console
set X_CONTEXT_OAUTH_CLIENT_ID=<your-public-client-id>
set X_CONTEXT_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/callback
python -m x_context auth login
```

The redirect URI shown above is only an example shape: use the exact loopback callback registered for your X App.

Then use the existing read commands:

```console
python -m x_context read "https://x.com/example/status/1234567890"
python -m x_context bookmarks
python -m x_context bookmarks --max-results 50
python -m x_context likes --max-results 25
python -m x_context likes --page-token "<token-from-a-previous-page>"
```

On successful `read`, `bookmarks`, or `likes`, stdout contains one canonical JSON document and structured usage diagnostics are written separately to stderr. `auth login` instead emits a small non-secret status JSON object on success. Handled failures leave stdout empty and report a stable error category on stderr.

Canonical output identifies the schema version, source, operation, retrieval time, normalized Post items, and page state. Personal-collection output also includes the authenticated subject and may include a continuation token for an explicit later invocation.

## Safety and privacy boundaries

- Product authority is read-only; there are no commands for posting, deleting posts, liking, bookmarking, following, or other X mutations.
- `auth login` adds no X data-reading authority beyond the already accepted P0 scopes: `tweet.read`, `users.read`, `bookmark.read`, `like.read`, plus `offline.access` so the managed credential can be refreshed.
- Bookmarks and liked-Post history are treated as private activity data. Collection results are process-and-return by default and are not persisted by the collection implementation.
- Lifecycle persistence stores only the explicitly committed protected credential envelope; it does not persist collection payloads.
- Credentials, authorization headers, raw provider responses, callback secrets, PKCE verifier/state values, protected-blob bytes, and private collection contents are excluded from normal diagnostics and retained validation evidence.
- Provider errors fail conservatively and never trigger scraping, cookie automation, browser automation, internal GraphQL, or another unofficial fallback.
- Collection pagination is caller-controlled and bounded to one provider page per invocation. No command silently retrieves all pages.
- OAuth acquisition is bounded to one listener, one browser launch, one terminal callback, and at most one token exchange per invocation; it has no automatic retry loop.
- `auth login` resolves a supported secure lifecycle store before browser launch and performs at most one atomic credential replacement after successful acquisition and pre-commit validation. Unsupported default-store environments fail closed; there is no plaintext persistence fallback.
- Real-provider login/refresh/revoke qualification is separate from synthetic contract tests and remains human-gated.

## Development and validation

Run the current project test suite from the repository root:

```console
python -m unittest discover -s tests -v
```

The suite covers URL parsing, official provider boundaries, canonical output, CLI behavior, authenticated-subject binding, OAuth acquisition/bootstrap, credential lifecycle, secret redaction, Windows DPAPI integration, and validation-workspace policy. The real-DPAPI integration test runs only on Windows and is skipped on non-Windows hosts by design.

The repository is public. Hosted GitHub Actions run `.github/workflows/project-ci.yml` and `.github/workflows/policy-check.yml` on pull requests, with project CI validating the proposed PR head rather than GitHub's synthetic merge commit. Windows exact-head validation is used when evidence must exercise the real DPAPI boundary. Current workstream evidence is summarized in `PROJECT_STATUS.md`.

## Status and limitations

`x-context` remains experimental. Its current canonical Post representation is intentionally small, and provider availability, entitlements, limits, OAuth behavior, and pricing are external facts that may change and must be re-verified when relevant.

The first OAuth bootstrap CLI is intentionally narrow: it supports managed login only. There is still no end-user CLI for local credential status/deletion or provider revoke, and packaging/release/distribution are not established. Real-provider login/refresh/revoke qualification remains a separate human decision.

Licensed under the MIT License. See LICENSE.
