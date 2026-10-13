# ADR-0006 — App-scoped Google Drive publishing for synthetic fixtures

- Status: Proposed for Issue #62; live bootstrap/acceptance await owner
- Date: 2026-10-13
- Related: SPEC-0008 unattended addendum, Issue #62, ADR-0004/0005

## Decision

Use a distinct user-owned Google Desktop OAuth public client with drive.file
only. Reuse existing publisher/connector body and revision checks; retain
Issue60's original complete-folder contract. AppBackend creates a fresh private
folder and binds exact file IDs to appProperties and local registry. Complete
files.list is app-visible all-MIME pages only, not proof excluding hidden owner
additions. The owner must keep this folder dedicated. Unknown visible files block.

Create native Docs empty in the verified private folder through Drive files.create,
then read/write through Docs requiredRevisionId. CURRENT-last is not a multi-file
transaction. A persistent pending-effect journal stops subsequent processes after
ambiguity. No automatic retry/adoption/rollback/delete/sharing change. One writer
is the supported contract, not a lock. Registry loss requires manual recovery.

Reuse DPAPI CurrentUser primitives for a separate whole Google envelope under
%LOCALAPPDATA%/x-context/google-drive/credential-v1.dpapi; never the X store.
Initial consent uses system browser, loopback state/S256 PKCE. Refresh-before-use
has no browser fallback and preserves old credentials on failure. Google refresh
token omission retains prior refresh token per Google's contract; X lifecycle's
different policy remains unchanged. No plaintext token.json. Same-user processes
remain outside DPAPI protection. Downloaded Desktop config stays outside Git.

## Alternatives and tradeoffs

Broad drive/metadata/documents scopes expand authority and are not requested.
ChatGPT connector token transplantation is unsupported/forbidden. No service
account, server, daemon, MCP bridge, sync service or scheduler is introduced.
Standard-library REST/OAuth retains the repository's no-dependency deployment.
The tradeoff is owning security-sensitive parsing/callback/provider contracts;
independent L2 and synthetic tests are required. Google's recommendation to use
OAuth libraries is acknowledged. SDK adoption needs dependency/version/update
review and is not an implicit bootstrap requirement.

## Qualification and recovery

Pre-implementation independent design L2: separate Codex agent, CRITICAL0/MAJOR0.
Fake APIs do not qualify live scope/permission fields/native rendering/lifetime.
Stop before project/client creation, first consent or real token saving. Owner
must select account/project and approve the addendum plan. External Testing
refresh grants for drive.file expire after7 days; production status/scheduling
are separate choices and no refresh token is permanent. Revoke through Google's
third-party access settings; local deletion alone is not revocation. Inspect
pending journal IDs and remote objects before explicit operator reconciliation;
no cleanup/recovery executor is added. This Google synthetic write authority does
not change ADR0004's X read-only boundary or blocked real-X cloud sharing.
Official Google sources are linked in the unattended addendum.
