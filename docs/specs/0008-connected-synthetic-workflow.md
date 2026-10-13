# SPEC-0008 Issue #60: bounded connected synthetic workflow

Requirement authority: [Issue #60](https://github.com/oimus1976/x-context/issues/60),
[capability observation](https://github.com/oimus1976/x-context/issues/60#issuecomment-6133391331),
[handoff](https://github.com/oimus1976/x-context/issues/60#issuecomment-6133413233).
Base: merged PR #59, `327bee86e917be250f19cb5a77127d6c8f5eaa05`.
Risk: HIGH_IMPACT (EXTERNAL_WRITE, SECURITY_BOUNDARY, PLATFORM_DEPENDENT).

## Scope and acceptance contracts

This amendment permits an **initially empty native Doc** to be created in root,
then moved and verified before any synthetic text insertion, exclusively in
the Issue #60 sandbox. It does not relax the general in-folder-create contract
for other adapters, and cannot be used for real X material. The adapter accepts
only the five existing reviewed fixture IDs/bodies after `core.verify` of the
actual generated portable directory. Python does not acquire credentials or
call cloud APIs; an already-authorized connected transport must be supplied.
The product CLI's `publish --apply` remains DRIVE_AUTH_UNAVAILABLE.

| Contract | Requirement / test obligation |
| --- | --- |
| CW-1 | Exact sandbox/PoC parent allowlist; native MIME, shared=false, complete owner-only permission metadata and same owner across folder/docs; no inferred permission success. |
| CW-2 | Before any effect require explicit complete **all-type**, direct-child inventory. Missing completeness, pagination, unknown children or duplicate identities fail closed. The exact historical sentinel is permitted only as an immutable observed exception; never returned as a managed record. Freshly verify it before every effect. |
| CW-3 | Create initially empty root Doc; record its returned ID immediately; verify empty body, owner-only permissions and exact observed root parent; move; verify exact sandbox parent, stable identity/title and empty body; only then insert generated text. No blind retries, deletion or adoption. |
| CW-4 | Native text canonicalization changes CRLF to LF only. Reject lone CR and non-text/oversized bodies. No trimming, Unicode normalization, blank-line collapse or removal of a terminal paragraph. Transport parses the full single-tab plain-text Doc including its terminal newline; unsupported tables/multiple tabs fail. |
| CW-5 | Delegate stable IDs, prior-body checking, idempotence, tombstones, CURRENT-last and final comparison to existing `drive.preview/apply`. Transport updates require revision-conditional writes after fresh metadata/text read; exact readback follows. Any attempted write failure is PARTIAL_UNPUBLISHED. Preserve a local owner-only stage journal and stop; do not auto-delete or adopt orphans. |
| CW-6 | Consume `core.verify(output)` rather than arbitrary supplied bodies or a manifest alone. No X/OAuth imports, credential discovery, new authentication configuration or product-store reads. |

`connector.Backend` is a small injected adapter, not an authenticated bridge.
Its transport must resolve root from the authorized connection, enumerate all
child types through all provider pages (including empty filtered pages), reject
incompleteSearch, and return a true completeness observation only at exhaustion.
`list_folder(top_k)` and typed-only `search` are insufficient. A caller-supplied
boolean is a contract for a trusted transport, not proof from an untrusted file.
Unknown metadata or unavailable revision checks block. Do not represent a fake
transport or the mere presence of ChatGPT tools as Python authorization.

The adapter's public `read` captures the document/revision receipt used by
the outer `drive.preview/apply` snapshot comparisons. Internal fresh listings
never replace that receipt. `update` must match it before using a conditional
revision write. These receipts depend on the trusted outer publisher; calling
`read` arbitrarily is not independent publication approval.

Provider references checked 2026-10-13: [Drive files.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list)
exposes nextPageToken/incompleteSearch; [Docs batchUpdate](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate)
provides requiredRevisionId write control. These APIs establish provider
capabilities, not their availability through this particular connector.

## Operator sequence and recovery

1. Generate and verify a named fixture under the existing disposable output
   root. Choose baseline for the initial set, then edited/withdrawn explicitly.
2. Supply an already-authorized supported transport, a local stage journal
   callback (nonsecret ID/phase only), and the exact sandbox. Read-only
   `connector.prepare(backend, output)` returns verified records and a plan.
3. Review the target/actions. Explicitly call existing `drive.apply` with that
   same backend, output records and plan. Preserve every stage journal entry
   before further effects. No journal, no writes. A failed journal can leave
   an ambiguous root create; preserve the returned ID in `backend.stages`, stop
   and inspect the connection's recent creations. Never retry a create blindly.
4. Verify final snapshot, active index and stable URLs before reporting COMPLETE.
   Any failure preserves all objects, reports PARTIAL_UNPUBLISHED/BLOCKED and
   requires inspection of the recorded ID, parent, permissions and text. A stale
   CURRENT can reference an intermediate record state; there is no transaction.
5. A second identical set must make zero writes. Edit and withdrawal should
   change only P001 plus CURRENT and preserve all document identities. Meowth
   ChatGPT/Gemini and deliberately offline-origin retrieval are separate UAT.

No code in this adapter changes permissions. Sentinel and original five #56
Docs are immutable. Final-check races, uncertain provider outcomes, revision
history/caches and complete erasure remain limitations. Single publisher only.
Keep Issue #60 open through live publication/UAT and independent review.

## Observed boundary / feasible connection

2026-10-13: connected metadata independently confirms exact sandbox parent and
owner-only permissions and the original sentinel identity. `list_folder` exposes
only a bounded scan. Legacy raw-parent search returned results without a
pagination/completeness receipt; typed search exposes pagination but filters
types. Neither establishes complete all-type inventory. No local Python bridge
is provided by these tools. **AC-D3/D4 live: NOT_RUN_UNSUPPORTED_INVENTORY_AND_BRIDGE**.
AC-D1/D2 remain prior connected-tool smoke evidence, not this adapter's PASS.
AC-D5/D6: PENDING; AC-D7: no X/OAuth requests or actual-data transfer.

Feasible next route: the existing authorized connector must expose a supported
all-type `files.list` transport with complete pagination/incompleteSearch and
metadata/body/revision readback, callable by the orchestration runtime. Then
bind these operations to this adapter and run the bounded synthetic smoke.
Until such a supported bridge exists, use this reviewed workflow as a manual
handoff, **without claiming it satisfies complete-inventory publication**.
An independently owner-configured Drive API connection is an alternative future
decision, not authorized setup here. Do not reuse connector OAuth tokens in
Python, add a service/app/daemon, or infer permissions from search results.
