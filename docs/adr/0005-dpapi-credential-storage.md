# ADR-0005 — Use DPAPI CurrentUser protected local storage for OAuth credentials

- **Status:** Accepted for Issue #32 implementation
- **Date:** 2026-09-16
- **Related:** Issue #32, SPEC-0003

## Context

x-context needs to persist an OAuth 2.0 user-context token set on Windows so bookmarks/likes can stop depending on mandatory manual `X_CONTEXT_USER_ACCESS_TOKEN` injection. The stored unit can include an access token, optional refresh token, expiry metadata, granted scopes, and schema metadata. Refresh must replace that unit atomically.

Two Windows-native options were compared: Generic Credentials in Windows Credential Manager and a local file whose complete credential envelope is protected with Windows DPAPI.

## Provider and platform constraints

The current product is Windows-first CLI/desktop tooling. X OAuth credentials are application-defined secrets and may change shape/length over time. Refresh-token rotation/reuse behavior is not sufficiently documented to encode assumptions about old-token validity, so x-context must treat each successful provider response as new credential material and replace its persisted state atomically.

Microsoft documents Generic Credential `CredentialBlob` as application-defined data with a maximum size of 2,560 bytes. Generic credentials are readable/writable by user processes. Microsoft documents DPAPI `CryptProtectData` / `CryptUnprotectData` with current-user protection as normally decryptable only under the same user logon credentials and normally on the same computer; same-user processes remain inside that protection boundary.

## Decision

Use a **single versioned credential envelope encrypted as one DPAPI `CurrentUser` blob and stored in a local per-user file**.

The implementation must:

- use current-user scope, never machine scope;
- use the non-interactive DPAPI path;
- encrypt the complete serialized credential envelope before it reaches durable storage;
- store no plaintext sidecar containing token values;
- perform replacement by writing a protected temporary file in the same directory and atomically replacing the target;
- keep storage behind a small backend interface so tests use an in-memory/fake backend and future platforms can add another backend without changing lifecycle policy;
- treat decrypt/schema/corruption failures as fail-closed credential errors;
- keep deletion local and idempotent;
- avoid assuming that filesystem backup/restoration to a different machine will preserve decryptability.

The default durable path belongs under the current user's local application-data area rather than the repository, working directory, or roaming/synced project state.

## Why not Windows Credential Manager

Credential Manager is appropriate for many simple application credentials, but it is not selected here because:

1. A single Generic Credential blob is capped at 2,560 bytes. A versioned OAuth token-set envelope should not depend on current provider token lengths staying below that ceiling.
2. Splitting the token set across multiple credential entries would make access/refresh token replacement a multi-record operation without a natural atomic commit boundary.
3. Schema migration, corruption handling, and test fixtures are simpler when the complete logical credential state is one encrypted envelope behind a storage abstraction.
4. Generic credentials are still accessible to processes running as the same user, so choosing Credential Manager would not create a materially stronger same-user isolation boundary for this threat model.

## Security boundary

DPAPI CurrentUser is protection at rest, not process isolation. Any process executing with the same user credentials may be able to ask Windows to decrypt the blob. x-context therefore also relies on normal Windows account/process security and minimizes secret exposure in memory, diagnostics, logs, repr/debug strings, fixtures, and exceptions.

No client secret is introduced. No write scope is introduced.

## Atomicity and crash behavior

The protected envelope is the unit of replacement. A successful update is visible only after the protected temporary file is fully written and the final replacement succeeds. If protection, temporary write, flush, or replacement fails, the previously committed credential file must remain the authoritative state whenever the operating system permits that guarantee.

No implementation may intentionally truncate the existing target before the replacement blob is ready.

## Recovery implications

A missing file is equivalent to no persisted credential. An unreadable/decrypt-failed/corrupt file is not silently discarded or downgraded to plaintext; the caller receives a safe credential-storage failure and can explicitly re-authorize or delete the local state.

Because DPAPI normally binds current-user protected data to the user and machine context, cross-machine portability is not promised. Re-authorization is the normal recovery path after machine migration or unrecoverable DPAPI state.

## Portability

The lifecycle policy and storage interface remain platform-neutral where practical, but this ADR selects a Windows concrete backend for the current product. A future cross-platform backend requires a separate design decision; it must not weaken the current secret-handling contract.

## Consequences

Positive:

- no fixed small credential-blob ceiling in the application schema;
- one logical encrypted state and one atomic replacement boundary;
- straightforward schema versioning and corruption detection;
- easy fake backend for deterministic tests;
- no new third-party secret-store dependency.

Costs:

- x-context owns the file-format/version and atomic-file implementation;
- recovery after machine/user-profile loss normally requires re-authorization;
- same-user malicious processes remain outside the protection this design can provide.
