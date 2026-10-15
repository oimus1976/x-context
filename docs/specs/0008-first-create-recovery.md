# PR #63: registered empty first-document recovery design

Status: proposed owner-gated continuation design, not a recovery executor.
Review: https://github.com/oimus1976/x-context/pull/63#pullrequestreview-5528374222
Risk: HIGH_IMPACT (EXTERNAL_WRITE, PRIVATE_DATA, SECURITY_BOUNDARY,
PLATFORM_DEPENDENT; inherited credential handling stays unchanged).

## Incident and implemented correction

The operator/review reports a separately approved real publish stopped after the
first native Doc create: PARTIAL_UNPUBLISHED, one registered C001, blank body,
no CURRENT. Google returned tabId `t.0`; parse_document incorrectly applied the
Drive-file ID alphabet. Tests previously used `TAB` and missed this boundary.

Docs TabProperties documents tabId as an immutable string, with no published
alphabet/length contract. `_tab_identity` implements our supported bounded ASCII
subset: 1..200 characters, alphanumeric/underscore/hyphen segments separated by
single dots. It accepts observed `t.0` and undotted fixtures, rejects missing,
nonstring, whitespace, controls, URL/path/encoding delimiters and empty segments.
It is not a claim about every possible provider-generated tab ID. IDs are used
unchanged only in JSON tabId fields. Drive file IDs, registry IDs, HTTP paths,
fixed endpoints, single-tab/plain-text rules and revision checks are unchanged.
Unknown future tab formats require another explicit compatibility review.

Public primary sources checked 2026-10-15, without authenticated product calls:
- https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#TabProperties
- https://developers.google.com/workspace/docs/api/how-tos/tabs

## Read-only diagnosis in this correction

The real local publication state was read without loading/decrypting credentials
or calling Google product APIs. Its schema validated; one C001 role is registered,
no CURRENT, and exactly two pending events exist in order:
`('', CREATE_ATTEMPT)`, `(registered_document_id, CREATED_EMPTY_UNVERIFIED)`.
The created-event ID equals the registered ID. Folder/parent/owner/namespace are
initialized. Bytes were unchanged across the diagnostic read. No IDs, private
paths, credentials or private payload are retained in this document.
Remote emptiness, same-folder placement and owner-only access are review/operator
observations, not newly measured live facts in this correction. Registry-to-live
ID agreement must be independently rechecked at the future approved inspection.

## Implemented inspection contract (no writes)

`google_recovery.inspect_first_create(transport, state_store)` is an injected
read-only primitive, tested only with a fake provider here. It has no CLI,
credential loader, refresh path, write method or automatic call from publish.
A caller must separately obtain authorization for live inspection; the ordinary
CLI continues to block pending before credential access/refresh/network.

It accepts only the incident-specific first C001 role, one registered exact ID,
and the exact two-event journal above. An unknown create result, additional or
reordered events, CONTENT_ATTEMPTED/UPDATE_ATTEMPT, another role, missing ID or
CURRENT require another recovery design. No candidate search by title is allowed.

It reads exact registry folder/document IDs and requires:
1. Exact Drive response IDs, app authorization, namespace, role and synthetic-v1
   appProperties for both objects; no adopted same-name object.
2. Exact stored folder parent/title/type, owner-only single user-owner permission,
   unshared/untrashed folder and document, same registered owner, and document's
   sole parent equal to that folder. A recreated/moved/stolen/shared object blocks.
3. Complete APP_VISIBLE all-MIME paginated inventory containing exactly that one
   registered document, no CURRENT or unknown/hidden-by-type child. drive.file
   cannot establish a global inventory; the dedicated-folder owner contract stays.
4. Native single-tab plain text, valid revision, empty application body (exactly
   the structural final LF remotely). An extra blank paragraph is not empty.
5. Repeated full snapshots and a final local state read agreeing with the initial
   state. Concurrent changes, unsupported structure or any failed read block.

The receipt holds the state digest and observed folder/document/revision in
memory, suppresses them from repr, and explicitly says NOT_AUTHORIZED. It does
not prove future freshness, protect against same-user tampering, authorize a
write, clear pending, or make ordinary preview accept a partial set.

## Proposed separately approved resume protocol

No executor is shipped or run by this correction. Before implementing/using this
protocol, obtain owner approval for the exact account, existing folder/document
IDs, compiled baseline fixture digest, allowed operations, request budget and
stop conditions. Consent to the original attempt does not authorize recovery.
Do not copy the real registry into tests, publish its IDs, or change credentials.
A future executor needs its own tests and exact-head L2 review.

1. Quiesce the single publisher. Preserve the original registry bytes and pending
   history in an access-restricted, non-Git local recovery record. Do not delete,
   truncate, replace with pending=[] or synthesize a successful commit. Use a
   versioned recovery journal with an incident identity, original-state digest,
   owner authorization reference, baseline digest and immutable observed IDs.
   Schema v1 has neither intent digests nor recovery event types; do not overload
   it or bypass validate_state. A sidecar/versioned migration must preserve v1
   pending evidence verbatim until verified completion.
2. Freshly run the inspection contract immediately before effects. Compare the
   entire local state/digest and current remote snapshot to the approved plan.
   No CURRENT exists. If changed, stop without writing. A cached inspection
   receipt is evidence only. Recheck owner/namespace/parent/privacy/inventory and
   revision before each subsequent effect; requiredRevisionId guards text races,
   but cannot atomically guard independent Drive permissions/parent changes.
3. Persist a durable recovery-intent entry BEFORE touching the existing C001:
   exact ID, old empty-body digest/revision and approved baseline-body digest.
   Insert compiled C001 text into THAT SAME ID with requiredRevisionId from the
   fresh read and observed `t.0` in JSON. Do not call files.create for C001; no
   delete, rename, move, sharing change, title-based adoption or replacement ID.
   Read back exact ID/title/parent/owner/permissions/body/new revision and record
   the verified result. Never infer success from HTTP success alone.
4. Resume the remaining four fixture roles as individually journaled creates in
   the SAME folder, recording each returned ID durably before writing its text.
   Read back each exact body and identity. Only a recorded success permits the
   next step. An ambiguous create stops: never create a second candidate. A
   CONTENT_ATTEMPTED or unknown-response interruption is outside the narrow
   empty-first-create inspector; inspect exact IDs and write outcomes under a
   separately reviewed reconciliation path, rather than automatic retry.
5. Keep CURRENT absent while any record is incomplete. After all five exact IDs,
   bodies, digests, revisions and privacy checks pass a fresh complete inventory,
   journal CURRENT creation and bind its returned exact ID. If an incomplete
   CURRENT body is used during staging, its status must be RECOVERY_IN_PROGRESS,
   which normal parse_index rejects; no COMPLETE links may be exposed early.
   Promote to the canonical COMPLETE index only as the final conditional remote
   write, using links/digests constructed from the five VERIFIED documents.
   Verify its exact body and the entire set again. Only then report COMPLETE.
6. Durably commit a recovery-completion record referencing the original history,
   evidence and final manifest. Transition active pending to resolved history in
   the new schema only after that durable commit, preserving original events.
   Future normal publish must verify that resolution and final CURRENT snapshot;
   merely erasing old events is never an entry condition.

A multi-file remote write and local journal commit are not an atomic transaction.
A crash after final CURRENT promotion can leave remote COMPLETE with local
unresolved history. Report the attempt PARTIAL/REQUIRES_INSPECTION, never claim
local recovery complete or retry; explicit reconciliation must confirm exact
final bodies/IDs/revisions and record completion without repeating creates.
Likewise an interrupted final journal save cannot authorize a fresh publication.
Readers have a last-written remote index, not proof of local journal completion.
This residual limitation must be included in owner approval, not hidden by tests.

## Required future executor acceptance tests

Use fictional IDs and Google-shaped t.0 responses. Demonstrate the existing C001
ID/URL survives, exactly four remaining records plus CURRENT are created in the
same folder, and no CURRENT COMPLETE is written before all record readbacks.
Inject failure before/after every request and durable journal save, including
ambiguous create/text/final-CURRENT outcomes and local commit failure. Require
retained history, zero blind retry/recreation, no ordinary publish while pending,
fresh requiredRevisionId, state-digest checks, and refusal of moved/shared/
nonempty/replaced IDs, unknown children, stale receipts and changed fixture intent.
The implemented inspection tests establish prerequisites only; they do not claim
an executable resume, successful live recovery or atomic publication.

## Owner C2 checkpoint

The registry owns expected IDs and historical attempts; Google owns current
object/revision/permission facts. Both must agree. Pending is unresolved evidence,
not a disposable error flag. Exact ID recovery preserves links; a duplicate create
would hide the incident. CURRENT is the final reader entry point and stays
incomplete until records are verified. The next decision is whether to authorize
the separately reviewed recovery implementation/live plan. Ready, merge and
cleanup remain human-final and are not performed here.
