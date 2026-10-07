# SPEC-0007: Bookmark local persistence MVP

## Status

Draft

- **Issue:** #51
- **Base main:** `808b271015184c5eadcc86d39c57b003d9b52f4d`
- **Risk:** HIGH_IMPACT
- **Change-specific facets:** PRIVATE_DATA, SECURITY_BOUNDARY
- **Scope:** specification only; no product implementation or live private-data write in this work item

## 1. Purpose

Provide the first explicit local-persistence capability for the authenticated user's X bookmarks.

The capability exists so bookmarked Post content can be retained locally and later used by deterministic search/export/organization features without repeatedly depending on live X state.

This specification promotes one narrow P2 capability already identified by SPEC-0000. It does not change x-context's product-level read-only X authority.

## 2. Existing authority and behavior preserved

SPEC-0001 FR-003 remains the acquisition authority for bookmarks.

The existing `x-context bookmarks` command remains process-and-return by default and MUST NOT gain an implicit persistence side effect.

The persistence slice MUST consume the successful canonical bookmark envelope produced by the existing acquisition path. It MUST NOT introduce a second provider implementation, a direct persistence-specific X endpoint, scraping, browser-cookie reuse, internal GraphQL, or browser automation.

Credential acquisition, secure credential persistence, refresh, and revoke remain governed by SPEC-0002 through SPEC-0004 and are not bookmark-payload storage mechanisms.

## 3. User-facing MVP contract

Logical interface:

```text
x-context bookmarks
x-context bookmarks save [--max-results <n>] [--page-token <opaque-token>]
```

`bookmarks` preserves the existing no-persistence behavior.

`bookmarks save` is the explicit local-write operation. It reuses the same authenticated-subject resolution, page-size bounds, optional page token, one-page provider limit, canonical normalization, error mapping, and usage accounting already defined for FR-003.

There is no implicit `--all`, automatic pagination loop, background ingestion, scheduled ingestion, or provider mutation.

## 4. Local store authority

### 4.1 Default location

The MVP store is fixed to:

```text
%LOCALAPPDATA%\x-context\data\bookmarks-v1.json
```

No CLI path override is introduced in this slice.

The store MUST be outside the repository and MUST NOT be written beneath the repository/worktree as normal product behavior.

If `LOCALAPPDATA` is missing or empty, the save operation fails locally as `configuration_error` before credential resolution or provider traffic. A path that resolves syntactically but later proves unwritable may still fail during the persistence phase as `storage_error`.

### 4.2 At-rest protection boundary

The bookmark store is UTF-8 plaintext JSON.

This MVP does **not** claim cryptographic confidentiality for bookmark payloads at rest. It relies on the normal local OS/user-profile boundary. It does not add DPAPI encryption, custom ACL hardening, same-user process isolation, reparse-point hardening, cloud encryption, or a password-protected vault.

This is an explicit residual privacy risk, not an accidental implementation detail.

Credentials remain separate and continue to use their existing credential-lifecycle protection.

## 5. Store schema

The complete file is one versioned object:

```json
{
  "store_schema_version": "1",
  "source": "x",
  "collection": "bookmarks",
  "subject": {
    "id": "1234567890",
    "username": "optional-current-observation"
  },
  "created_at": "2026-10-08T00:00:00Z",
  "updated_at": "2026-10-08T00:00:00Z",
  "items": [
    {
      "id": "9876543210",
      "text": "synthetic example",
      "first_seen_at": "2026-10-08T00:00:00Z",
      "last_seen_at": "2026-10-08T00:00:00Z"
    }
  ]
}
```

`username` is optional exactly as in the canonical subject model.

The store MUST NOT contain:

- access tokens;
- refresh tokens;
- client secrets;
- Authorization headers;
- cookies;
- OAuth state/verifier/code values;
- provider raw response bodies;
- input or output pagination/page-token values.

### 5.1 Timestamp semantics

`created_at`, `updated_at`, `first_seen_at`, and `last_seen_at` are observation/persistence timestamps derived from the successful canonical envelope's `retrieved_at`.

They are **not** X bookmark timestamps and MUST NOT be presented as the time the user originally bookmarked a Post.

For a newly created store:

- `created_at = retrieved_at`;
- `updated_at = retrieved_at`;
- each new item's `first_seen_at = retrieved_at`;
- each new item's `last_seen_at = retrieved_at`.

For an existing item observed again:

- `first_seen_at` is preserved;
- `last_seen_at` becomes the current successful envelope's `retrieved_at`;
- the latest observed canonical `text` replaces the prior stored `text`.

The store does not preserve text-edit history in this MVP.

## 6. Subject isolation

One store represents one authenticated X subject.

The store's `subject.id` is established from the successful canonical bookmark envelope.

On later saves, the incoming canonical subject ID MUST exactly equal the stored subject ID before any replacement write occurs.

A mismatch fails closed as `subject_mismatch`. The existing store MUST remain unchanged.

The caller cannot override the subject ID.

A change in observed username does not create a new subject because the numeric subject ID is authoritative. The stored optional username may be replaced by the latest canonical subject representation.

Multi-account merging, switching between multiple local stores, and user-selectable store IDs are outside this MVP.

## 7. Merge and deduplication semantics

Post ID is the stable deduplication key inside one subject-bound bookmark store.

When a page is saved:

1. resolve and validate the fixed local store configuration;
2. if a store exists, read and validate it before credential resolution/provider traffic;
3. obtain one successful canonical bookmark envelope through the existing FR-003 path;
4. verify the incoming/stored subject boundary;
5. merge items by Post ID;
6. build the complete next store image in memory;
7. immediately before replacement, re-read the current store state and require it to match the preflight state byte-for-byte (including the same absent/present state);
8. replace the durable file atomically as one unit.

The pre-provider store read is validation only. Directory creation, temporary-file creation, and payload writes occur only after successful FR-003 acquisition. Therefore a missing/empty `LOCALAPPDATA` or an already malformed/unsupported existing store consumes zero provider requests.

For a Post ID not present in the store, append one new item.

For a Post ID already present, do not create a duplicate. Preserve `first_seen_at`, update `last_seen_at`, and replace `text` with the latest observed canonical text.

Existing item order is preserved. Newly observed items are appended in the canonical page order. The MVP does not infer chronology from X Post IDs and does not sort by provider-specific ID semantics.

Repeated saving of the same page is therefore idempotent with respect to item cardinality, though observation timestamps may advance.

## 8. Absence, retention, and deletion semantics

A missing Post in a later fetched page is **not** evidence that:

- the bookmark was removed;
- the Post was deleted;
- the Post ceased to exist;
- the local copy should be removed;
- the historical collection is complete.

The saver MUST NOT delete or mark an item absent merely because it does not appear in a later page.

Saved items remain in the local store until the whole store is deliberately removed outside this MVP or a future deletion/synchronization capability is separately specified.

This MVP provides:

- no retention expiry;
- no automatic pruning;
- no per-item delete command;
- no whole-store delete command;
- no automatic X deletion/unbookmark synchronization;
- no provider-side mutation.

Manual removal of the store file by the operator is outside x-context's product command surface for this slice.

## 9. Export behavior

No Markdown, Obsidian, CSV, database, search-index, backup, or AI-enrichment export is introduced.

The UTF-8 JSON store itself is the only durable persistence artifact in this MVP.

Future Markdown/Obsidian or other exporters MUST consume the canonical/local store model and MUST NOT introduce their own direct provider acquisition path.

Direct file copying by the operator is not an x-context export feature and is outside this specification.

## 10. Atomicity, corruption, and recovery boundary

The implementation MUST NOT truncate or update the existing store in place.

A save uses a temporary file in the same store directory and a whole-file replacement operation.

Before replacement, the complete next store image MUST pass the same schema validation required for an existing store.

If the existing store is malformed, unreadable, unsupported, has duplicate Post IDs, has invalid subject/timestamps/items, or otherwise fails the store contract:

- fail as `storage_error`;
- do not overwrite, repair, normalize, or delete the existing store automatically;
- do not emit successful canonical output for `bookmarks save`.

If serialization, temporary-file creation/write, validation, flush/close, or final replacement fails:

- report `storage_error`;
- do not claim persistence success;
- suppress raw OS exception prose from normal diagnostics;
- preserve the previously committed store whenever failure occurs before a successful replacement.

Immediately before replacement, the implementation MUST perform a freshness check against the pre-provider store snapshot. If the file appeared, disappeared, or its bytes changed since preflight, fail closed as `storage_error` and do not replace it. This prevents the save operation from knowingly overwriting a concurrent/manual update observed after the provider round trip.

The freshness check is lost-update detection, not a general file-locking or hostile-process security guarantee.

The MVP does not claim crash-consistent durability against every filesystem/hardware failure mode. Its invariant is fresh-state-checked whole-file replacement rather than in-place mutation.

## 11. Concurrency boundary

The first persistence slice is single-process/single-writer.

Concurrent saver processes are unsupported and the implementation MUST NOT claim general merge safety under concurrent writes. The pre-effect freshness check in Section 10 MUST block replacement when another writer changes the store between preflight and replacement, but it is not presented as a full locking protocol.

This MVP does not add file locking, a database, a daemon, or distributed synchronization solely to solve concurrency.

A later requirement may introduce locking if real usage demonstrates the need.

## 12. CLI success and diagnostic behavior

A successful `bookmarks save` emits the existing canonical bookmark envelope to stdout only **after** the local store replacement succeeds.

This preserves the existing canonical output, including the caller-visible continuation token when one exists.

The continuation token remains private operational data:

- it may appear only in the canonical caller output already defined by FR-003;
- it MUST NOT be copied into the bookmark store;
- it MUST NOT be copied into normal diagnostics, controlled exceptions, CI artifacts, or durable validation evidence.

The save operation may emit a structured storage diagnostic to stderr containing only non-secret facts such as:

- operation name;
- persistence attempted/succeeded;
- new-item count;
- existing-item update count;
- resulting item count.

Diagnostics MUST NOT include Post text, Post IDs, subject ID/username, page-token values, credential values, raw provider bodies, raw local store content, or raw OS exception prose.

If provider acquisition succeeds but persistence fails, the overall `bookmarks save` command fails non-zero and MUST NOT emit a successful canonical envelope to stdout.

## 13. Error model extension

Existing acquisition errors remain unchanged.

The persistence slice adds one stable local category:

- `storage_error` — malformed/unsupported existing store, serialization/write/replace failure, or another failure of the local persistence boundary after configuration is otherwise usable.

Existing categories remain applicable, including:

- `configuration_error` for unusable local configuration such as absent `LOCALAPPDATA`;
- `subject_mismatch` for incoming/store subject disagreement;
- provider/authentication/authorization/rate/usage errors from FR-003.

No local storage failure triggers provider retry, scraping, unofficial fallback, automatic repair, or destructive cleanup.

## 14. Privacy and evidence boundary

Actual bookmark payloads are private local runtime data.

Real bookmark contents MUST NOT enter:

- the Git repository;
- Issues or PR text;
- CI fixtures/artifacts;
- durable validation logs;
- normal diagnostics;
- retained review evidence.

Automated tests use obvious synthetic subject IDs and synthetic Post content only.

The new durable bookmark store is private actual data and is not a repository artifact.

## 15. Explicitly out of scope

This specification does not introduce:

- implicit/automatic fetch-all;
- background or scheduled ingestion;
- pagination cursor persistence;
- automatic reconciliation with X-side unbookmark/delete state;
- likes persistence;
- own-post persistence;
- arbitrary-user persistence;
- multi-account store management;
- path override;
- database/search index;
- Markdown/Obsidian/CSV export;
- AI summarization/tagging/classification;
- cloud synchronization/backup;
- encryption at rest beyond the normal user-profile boundary;
- custom filesystem ACL hardening;
- same-user malicious-process isolation;
- X mutation of any kind.

## 16. Acceptance criteria

### AC-BMSTORE-001 — Explicit opt-in

Plain `x-context bookmarks` retains its current process-and-return behavior and creates/modifies no bookmark payload store.

Only the explicit `x-context bookmarks save` path may persist a bookmark payload under this specification.

### AC-BMSTORE-002 — Existing acquisition/cost boundary reused

`bookmarks save` reuses FR-003 authenticated-subject resolution and one-page retrieval.

Default/allowed page sizes, explicit page-token handling, provider request accounting, error mapping, and no-fetch-all behavior are unchanged.

The persistence feature introduces no additional X content request, provider endpoint, scope, retry loop, or mutation.

### AC-BMSTORE-003 — Fixed private local store

Successful persistence targets exactly the MVP default under `%LOCALAPPDATA%\x-context\data\bookmarks-v1.json`.

No repository/worktree path or caller-supplied alternate path is accepted.

Missing/empty `LOCALAPPDATA` fails locally as `configuration_error` with zero credential/provider requests. An existing malformed/unsupported store is also rejected before credential/provider traffic. A later filesystem writeability/replacement failure is `storage_error`.

The stored representation is UTF-8 plaintext JSON and does not claim cryptographic at-rest protection.

### AC-BMSTORE-004 — Exact schema and private-value exclusions

A successful store conforms to Section 5, with `store_schema_version="1"`, `source="x"`, `collection="bookmarks"`, one canonical subject, valid UTC observation timestamps, and unique Post-ID items.

Credential material, authorization material, raw provider payloads, and page-token values are absent from the store.

Malformed or unsupported existing stores fail closed as `storage_error` and are not rewritten.

### AC-BMSTORE-005 — Subject isolation

The first successful save establishes the store subject from the canonical envelope.

Every later save requires exact incoming/stored numeric subject-ID equality before replacement.

Mismatch => `subject_mismatch`, non-zero exit, no successful canonical stdout, and byte-for-byte unchanged prior store.

### AC-BMSTORE-006 — Idempotent merge

Saving new Post IDs adds one item per ID.

Saving an already stored ID creates no duplicate, preserves `first_seen_at`, updates `last_seen_at`, and replaces stored `text` with the latest observed canonical text.

Existing order is preserved; new items append in canonical page order.

Repeated saving of the same page does not increase stored item cardinality.

### AC-BMSTORE-007 — No deletion inference

Absence from any later fetched page never deletes, expires, hides, or marks a stored item as unbookmarked.

No automatic retention expiry, pruning, provider-side mutation, per-item delete, or X-state reconciliation occurs.

### AC-BMSTORE-008 — Whole-file fail-closed replacement

The saver constructs and validates a complete next store image before durable replacement.

It does not truncate/update the committed store in place.

A simulated serialization/write/replace failure produces `storage_error`, no success output, and preserves the prior committed store whenever the replacement did not succeed.

If the store's present/absent state or bytes differ from the preflight snapshot immediately before replacement, the operation fails as `storage_error` without replacing the newer/current store.

### AC-BMSTORE-009 — Safe output and evidence

Successful stdout remains the canonical bookmark envelope and is emitted only after persistence succeeds.

Normal/durable diagnostics may include safe counts but exclude bookmark text, Post IDs, subject identity, page-token values, credentials, raw provider bodies/store bytes, and raw OS exception prose.

Synthetic tests and retained CI/review evidence contain no actual bookmark payload.

### AC-BMSTORE-010 — Deferred integration scope

The MVP creates only the local JSON store.

No Markdown/Obsidian/export/search/AI capability, pagination cursor persistence, scheduled ingestion, database, locking framework, or multi-account management is implemented under this specification.

## 17. Planned test mapping

Before implementation, tests MUST be derived from the acceptance criteria and include at least:

- unchanged no-persistence behavior of existing `bookmarks`;
- explicit `bookmarks save` composition over the existing canonical acquisition boundary;
- fixed LOCALAPPDATA path and zero repository writes;
- first-store creation;
- exact store schema validation;
- malformed/unsupported existing store refusal;
- credential/page-token/private-value exclusion from store and diagnostics;
- subject mismatch preserves prior bytes;
- new-item merge and existing-item update;
- duplicate ID rejection in pre-existing stores;
- repeated-page cardinality idempotence;
- no deletion from later absence;
- atomic replacement and injected write/replace failure;
- pre-effect freshness/readback: store appeared/disappeared/changed after preflight => no replacement and no lost update;
- no successful canonical stdout before persistence commit;
- one-page/no-extra-provider-request regression;
- synthetic real-Windows filesystem smoke using a temporary LOCALAPPDATA root.

The synthetic Windows filesystem smoke establishes the new local-storage boundary without requiring actual bookmark contents.

A future end-to-end save using live private bookmarks is a separate explicit human-authorized qualification and is not required merely to merge this specification.

## 18. Work order and human gate

Required order:

1. specification;
2. TEST_MATRIX mapping;
3. tests;
4. minimal implementation;
5. adversarial review;
6. exact-head validation;
7. L2 independent review;
8. applicable real-boundary filesystem smoke;
9. Draft PR / human comprehension review;
10. human Ready / merge.

Because the implementation will create a durable private-data boundary, the owner should be able to explain at C2 level:

- where bookmark data is stored;
- that it is plaintext under the local user-profile boundary;
- that normal `bookmarks` remains non-persistent;
- how one-subject isolation and Post-ID deduplication work;
- why absence does not cause deletion;
- how atomic replacement/fail-closed corruption works;
- what is explicitly deferred.

Ready and merge remain human-final.
