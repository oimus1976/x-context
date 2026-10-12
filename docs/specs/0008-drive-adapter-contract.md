# SPEC-0008 implementation choices and disconnected Drive contract

Requirement: [Issue #57 v0.2](https://github.com/oimus1976/x-context/issues/57).
Implementation: [Issue #58](https://github.com/oimus1976/x-context/issues/58).
Risk: HIGH_IMPACT (SECURITY_BOUNDARY, EXTERNAL_WRITE, PLATFORM_DEPENDENT).

## Narrow input and local authority

`--synthetic-fixtures` is an enum of bundled sets, not a filename or directory.
Five IDs P001/P002/P003/C001/C002 and per-ID approved fictional content are
allowlisted in `fixtures.py`. `core.normalize` also rejects arbitrary marked
content. Edits/withdrawal/injection use separately reviewed fixture variants.
Bounds: 5 records, 4096 UTF-8 bytes of content, 5 distinct related refs, exact
second-precision UTC timestamp. Reordering does not change normalized bytes.
The normalized tombstone uses the exact same ten record keys with content
`SYNTHETIC TEST DATA: SYNTHETIC WITHDRAWN`.

Local manifest records include all managed IDs/status/source refs/hashes; only
`active_ids` are current active sources. Hashes cover canonical JSON bytes
(sorted keys, two-space indentation, LF, trailing newline, UTF-8 without BOM).
There are no Drive identities in this portable manifest. Existing output is
accepted only if every file equals regeneration from its allowlisted records;
unexpected files/directories or altered Markdown fail. Omission retains prior
records locally; a Drive apply must provide the full prepared local record set.
No filesystem discovery of product data or credential configuration exists.

## Injectable connected-tool boundary (not implemented live)

`drive.Backend` is a small synchronous interface. A supported connected-tool
bridge can implement it later using the already-authorized Google Drive tools:

| Method | Required connected-tool operation and observation |
| --- | --- |
| `folder(id)` | `get_file_metadata` of the exact newly authorized sandbox ID; require native folder, expected parent in tested PoC area, `shared=false`, restricted permission inventory (no anyone/domain/group/unexpected grantee), ownership/capability to edit. Return `(id, True)` only after actual verification. Never select root/KB/old PoC by name. |
| `list(id)` | Complete paginated direct-child inventory plus metadata and native-Doc parsed text; list-folder partial results cannot prove complete inventory. On incomplete pagination or unavailable permission fields fail. |
| `read(doc_id)` | Get actual Doc ID/URL/name/parent/MIME/restricted permissions and parsed full native Doc body. Canonical body comparison is exact text, not rendered layout. |
| `create(id,title,body)` | Create native Doc **in that sandbox**, populate its text, then read actual metadata and body. A connector unable to create in an explicit parent safely is unsupported. |
| `update(doc_id,body)` | Replace parsed Doc text in place on that exact ID after fresh expected-content/metadata/permission comparison; read metadata and full text back. No copy/delete/permission operation. |

`Document` is the observed metadata/text snapshot, including exact single
parent ID, actual canonical Docs URL and native MIME. Unknown/inherited/expanded
permissions must never be guessed safe. The existing connector's create-native-
Doc tool only supports a parent for service-account mode; this is not evidence
of a usable Python connection or supported sandbox-native create path here.
No credential or new permission setup is part of this change.

`preview(backend, sandbox, normalized_records)` performs zero writes and returns
an immutable `Plan` snapshot. `apply(backend, same_sandbox, same_records, plan)`
revalidates it, checks the inventory before each effect, updates each per-ID
Doc with exact readback and writes CURRENT last. Stable names alone do not
authorize adoption: title, parent, native MIME, restricted permission, synthetic
marker, prior body, stored digest and identity must agree. Duplicate names,
unexpected children, orphan/partial state and concurrent edits block.

The current index stores all managed identity/digest receipts (including
tombstones) separately from `active_ids`/`active_links`. Readers consume only
active links. An unchanged repeat performs zero content writes. Any write
attempt followed by failure yields `PARTIAL_UNPUBLISHED`, including ambiguous
provider failures. Earlier index remains unchanged until index write; an error
after index write can leave an unverified index effect. Preserve and inspect;
no automatic rollback, retry adoption or deletion. Concurrent provider edits
between final check and write remain possible; no multi-document transaction,
provider lock, global deletion, cache purge or search-currentness guarantee.

## Runtime result and next human gate

This repository's Python runtime has no configured authenticated Drive backend.
CLI `publish --dry-run` reports `DRIVE_AUTH_UNAVAILABLE` and describes titles,
IDs and fingerprints; it is **not** a remote snapshot and cannot be passed to
`apply`. CLI `--apply` fails closed. The fake uses visibly `FAKE-*` identities;
its PASS does not establish live Drive success.

AC-10: NOT_RUN_AUTH_UNAVAILABLE. AC-11/12: PENDING human UAT using generated,
actually published records and proof that the originating PC is offline.
The owner must govern the connected sandbox and real-data release gates.
Ready/merge remain human-final; this implementation ends at Draft PR.
