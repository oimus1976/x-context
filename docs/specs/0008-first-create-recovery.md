# PR #63: empty first-C001 recovery executor

Status: implemented injected executor, fake-tested; live use requires separate
owner approval. No credential loader, new CLI, generic recovery or ordinary
publisher bypass is included. Risk HIGH_IMPACT: EXTERNAL_WRITE, PRIVATE_DATA,
SECURITY_BOUNDARY and PLATFORM_DEPENDENT; credential lifecycle is unchanged.

Reviews:
- https://github.com/oimus1976/x-context/pull/63#pullrequestreview-5528374222
- https://github.com/oimus1976/x-context/pull/63#pullrequestreview-5532355581

## Incident and source/test correction

The review/operator reports a separately approved live publish stopped after
C001 files.create: PARTIAL_UNPUBLISHED, registered blank native Doc, no CURRENT.
Google's tabId t.0 was rejected by a Drive-file-ID validator. Starting HEAD
69395fa560a87c3f16b70c3df746fed94a53f581 corrected the compatibility bug and
added read-only inspection. Its 390 Windows tests/CI/L2 are historical evidence
for that head, not evidence for this executor. The original state diagnosis was
read-only in the preceding task: one C001 and the ordered two-event pending
CREATE_ATTEMPT then matching CREATED_EMPTY_UNVERIFIED. This task does not read
actual registry/credentials or access Google. Remote incident observations remain
operator/review evidence, not new live measurements or completed recovery.

TabProperties documents tabId as an immutable string without a published grammar.
The supported local subset is 1..200 ASCII alphanumeric/underscore/hyphen segments
separated by single dots. It accepts observed t.0 and undotted fixtures, rejects
hostile/missing shapes, and is used unchanged only in JSON. Strict Drive-ID/HTTP
path validation, single-tab plain text and requiredRevisionId remain unchanged.
Primary sources checked in the previous correction:
- https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#TabProperties
- https://developers.google.com/workspace/docs/api/how-tos/tabs

## Entry points and authority

`plan_first_create(transport, state_store)` reuses `inspect_first_create` and
returns an observation bound to the baseline fixture digest, entire original
state digest, owner/folder/ID/body/revision snapshot. It grants no authority.
The existing inspector accepts only one C001, blank application body (only the
provider structural final LF), no CURRENT, exact original two-event sequence,
namespace/roles/app authorization, owner-only permissions, same parent and
complete APP_VISIBLE inventory. It rereads remote and local observations.

`resume_first_create(transport, state_store, journal, plan, approved=True,
approval_reference=...)` is a separately invoked API for an already authorized
caller. Approval must be exactly True with a bounded nonsecret owner-reference;
it is not authentication or a claim that the owner already approved live use.
The function rejects absent approval before any state/journal/transport access.
Only compiled baseline is supported. It rereads the current plan and requires
exact equality, including revision and fixture intent. No arbitrary text input.

No existing publish/init/login CLI mode calls the executor. A future live caller
must be separately reviewed/approved with exact paths/account/IDs and a fixed
sidecar location. Do not issue live commands from this document. Implementing the
injected executor does not authorize credential load/refresh or remote effects.

## Persistent history and ordered effects

The original v1 publication registry is read-only for the entire operation,
including success. `Journal(explicit_absolute_jsonl_path)` exclusively claims a
new sidecar with xb. Existing, empty, malformed, partial or completed files block
re-entry. The sidecar is bounded append-only JSONL; each write flushes/fsyncs and
rereads. It never truncates/replaces prior history. Storage errors are terminal;
no automatic recovery of torn append, cleanup, rollback or retry is attempted.

BEGIN contains the original complete logical registry/pending, original-state
and fixture digests, initial revision and owner approval reference. The original
file itself remains byte-for-byte unchanged and remains the incident record.
All sidecar IDs/revisions/manifest are local operational data, not normal logs,
PR text or CI artifacts. Caller must choose a private local folder, quiesce the
single publisher and preserve this one sidecar; do not pick a new file to evade
a failed claim. No concurrent-writer lock or hostile same-user tamper protection
is claimed. Path checks reject symlinks/junctions and unsupported filenames.

For EACH effect: compare original state and journal; fresh folder/whole visible
inventory/metadata/owner/parent/revision/body checks; append INTENT durably;
repeat those checks; invoke the remote operation once. Before the original C001
write, also rerun inspect_first_create after INTENT and require the original plan.
C001 is written at its exact registered ID with requiredRevisionId and observed
tabId. No C001 create/delete/move/rename is possible in the executor.

For each of the four remaining roles: create empty native Doc in the same folder,
persist the returned ID in CREATED before another remote request, check exact
empty body/privacy/namespace/parent and inventory, then conditionally insert the
compiled body. Read back and persist VERIFIED (ID/revision/body digest) for each.
A create that returns an unknown/duplicate/unsafe ID stops without adoption.

Only after all FIVE records have exact verified bodies and fresh metadata does
the executor construct CURRENT from those verified IDs/URLs/digests. CURRENT is
created empty last; it contains no COMPLETE index while records are incomplete.
Its conditional text insertion is the final remote write. Revalidate all six
bodies/revisions/permissions/parents/inventory, append and verify COMPLETE with
the final manifest, and only then return COMPLETE. Successful fake run performs
11 mutation attempts: existing C001 text, four creates plus text, CURRENT create
plus text. One fake successful run observed 1,241 HTTP requests (273 Docs GETs,
962 Drive calls) and 29 journal writes. These are fake counts, not live quota,
latency or permission qualification; the future owner must approve a real request
budget before execution. Provider throttling stops without retry. It never creates a replacement sandbox, shares, deletes or calls X.

## Failure/recovery semantics and limits

Any exception stops the one-shot call. Once a remote operation was attempted,
return PARTIAL_UNPUBLISHED; otherwise BLOCKED. Append STOPPED only if the current
sidecar still equals the in-memory history; a persistence error can prevent even
that append, so absence of STOPPED is not success. Never retry in the same call.
Any existing sidecar blocks subsequent invocations before remote inspection.
Original pending remains; ordinary AppBackend/publish always blocks it.

A crash/error after CURRENT promotion can leave a remote COMPLETE index with an
unresolved local completion record. The function cannot make those two systems
atomic. A failure at final readback or COMPLETE append returns PARTIAL even when
the append itself may have reached disk. A future reconciliation must independently
inspect exact final IDs/revisions/bodies and preserve history without recreating
objects. That broader reconciliation and later normal-publish reactivation are
outside this incident executor. No automated resume of an interrupted recovery.

Permissions/parent and Docs revision are different Google authorities and cannot
be checked atomically with one text write. Fresh checks bound the window;
requiredRevisionId protects native text concurrency. APP_VISIBLE inventory still
does not prove absence of hidden owner-added files under drive.file. The owner
must retain a dedicated folder and single writer. Fake tests establish contracts,
not real scope/metadata/rendering/quota/refresh qualification or live success.

## Owner C2 and separate real-machine approval

The registry owns original IDs/attempt history; Google owns current object facts;
the sidecar owns this explicit recovery attempt's intent and observed completion.
Pending is evidence and is never erased. Successful recovery means six verified
remote Docs plus durable completion evidence; it does NOT reactivate normal
publish. A later operation needs separately specified registry reconciliation.

Before real use, the owner must approve the exact account/folder/C001 ID, compiled
baseline/state digest, reviewed caller and sidecar path, allowed eleven mutations,
quota/request budget, single-writer window and ambiguity stop plan. No such live
approval is consumed by this implementation, tests, PR update or review. Ready,
merge and cleanup are separate human-final effects and remain unperformed.

## Requirements and AC (frozen before RED; review #5532355581)

This slice provides an injected `plan_first_create` / `resume_first_create` API.
It does not load credentials or add a live CLI. A separately approved caller must
supply the existing authorized Transport, exact State and explicit Journal path.
Only the compiled baseline is supported. No interrupted recovery is resumed.

| Requirement | AC | RED test contract |
|---|---|---|
| R1 exact incident/approval | REC-01 | No approval => no reads/writes; fresh inspect_first_create must equal the approved plan; changed fixture intent/state/revision/owner/parent/body blocks |
| R2 preserve existing C001 | REC-02 | Same C001 ID/URL, conditional text update with t.0; no C001 create/delete/move; five creates total (four records plus CURRENT) |
| R3 durable evidence | REC-03 | Exclusive versioned append-only sidecar preserves original state/pending, bound state/fixture digests and owner reference; intent before every remote effect, returned IDs before further requests, verified receipts, completion manifest last |
| R4 ordered completion | REC-04 | All five record bodies/IDs/privacy/revisions verified before CURRENT create/text; final whole-set readback precedes durable COMPLETE and return COMPLETE |
| R5 stop on uncertainty | REC-05 | Inject failure before/after every fake HTTP request and journal write; no later remote write, no automatic retry, repeat blocked by existing sidecar; failure at/after final remote effect or completion save cannot report success |
| R6 retain ordinary barrier | REC-06 | Original v1 registry bytes and pending remain untouched on success/failure; AppBackend/normal publish stay blocked, including after recovery COMPLETE |
| R7 narrow persistence | REC-07 | Exclusive claim, no overwrite on re-entry, bounded corrupt/symlink/junction/read/save failures block; separate fresh instances see retained events; no credentials/private fixture import |

The original design's proposed v1-to-resolved-history migration (step 6) is
explicitly deferred from this narrow implementation. The sidecar completion
record resolves this attempt for audit; it does not remove/override v1 pending.
Normal publishing remains blocked even after successful recovery. Enabling later
edit/no-op operations requires a separately specified registry reconciliation;
never remove pending manually. This narrower boundary prevents completion from
becoming an implicit ordinary-publish bypass.

Success means remote six-document completion plus a durably verified sidecar
COMPLETE receipt. It does not mean real-provider qualification, ordinary-publish
reactivation, Ready, merge or permission to execute in a real account. The parent
registry remains the original incident record. A partial sidecar, even one whose
last COMPLETE append may have reached disk, requires manual inspection; no second
executor invocation is authorized. Sidecar is local operational data, never a
normal log, repository fixture, CI artifact or PR body. Do not print its IDs.
