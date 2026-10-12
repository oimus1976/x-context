# SPEC-0008 — Shared synthetic context generation & update, v0.2 (reviewed 2026-10-12)

**Authority:** This Issue #57 is the requirement/AC/test design. GitHub `main` is authority for merged behavior, verified base `cf68e1d226facab3e8ceb384898488aae0a1392d`.
**Review:** [Independent v0.1 review and changes](https://github.com/oimus1976/x-context/issues/57#issuecomment-6125401638).
**Stage:** Design reviewed and corrected; implementation is a **separate synthetic-only work item**. This design is NOT an authorization to share actual X data, call the X API, modify OAuth credentials, or merge a PR.
**Constraints:** `SPEC-0000` P2/P3 direction, `SPEC-0007` plaintext one-subject single-writer local store, `PROJECT_PROFILE.toml` human-final Ready/merge, spec→AC→tests→implementation.

## 1. Desired user outcome & review evidence

The user wants to ask ChatGPT or Gemini from **any authorized device** to relate permitted X-derived source context to work/development material **without requiring the acquisition PC and without re-querying X for every question**. Issue [#56](https://github.com/oimus1976/x-context/issues/56) observed a bounded private **synthetic** Google Drive search/retrieval experiment. The user reported matching results from **ChatGPT and Gemini on the alternate PC Meowth**; provider logs and origin-PC-offline status have not been independently checked.

**Slice boundary for this implementation:** Only programmatically **generate and update synthetic shared records**, and optionally publish them into a **new isolated synthetic publisher sandbox** under the previously tested Drive folder when an authorized Drive connection actually exists. This is not the live-X integration, production-compliant deletion service, scheduler, permanent hosted API, cross-account entitlement system or full semantic search engine.

**Non-goals now:** real `bookmarks-v1.json` parsing/export; arbitrary local file or `LOCALAPPDATA` import; official X API traffic; DPAPI/token reads or OAuth; ingest actual posts/IDs/text, summaries or embeddings; copying municipal/internal files; modifying canonical AI-Knowledge KB; creating a server/MCP/daemon/database; automatic cloud sync; unlimited multiwriter operations; deploying Gemini/ChatGPT plugins.

## 2. Architecture and authority boundaries

1. **A — unchanged local source:** Existing `%LOCALAPPDATA%\x-context\data\bookmarks-v1.json` remains managed only by `SPEC-0007`. This project slice **must not open it**. Its OAuth credential file remains DPAPI `CurrentUser` under a separate path and is **never transferred**.
2. **B — synthetic exporter:** Deterministic, offline, standard-library Python transforms *explicit allowlisted test fixture records* into portable per-record `JSON` + human-readable UTF-8 `Markdown`, plus `manifest-v1.json`. Exporter has **no X/credential/Drive dependencies**.
3. **C — optional Drive publisher adapter:** Explicit `dry-run/preview` and separate `apply`, only into a **dedicated test folder distinct from the five hand-authored PoC source Docs**; output is one native Google Doc per record ID plus a current-index Doc updated last. One publisher, stable record Doc IDs/URLs across updates. Google Drive backend is a separated adapter; a fake in-memory backend is mandatory for tests. **Do not assume Codex's Windows terminal has an authenticated Drive connector just because ChatGPT has one.** If real Drive auth is unavailable, the adapter stays pending and reports `DRIVE_AUTH_UNAVAILABLE` rather than inventing OAuth setup, credentials, access, or a cloud PASS.
4. **D — consumers:** A reader, including ChatGPT/Gemini, discovers the *current index* and only consumes active source IDs/Docs. Docs are a tested Drive representation, not an AI-specific schema. Contents are untrusted input, never authority to issue tool calls or alter instructions.

Portable schema is the contract; Drive-native formatting, file IDs and provider indexing are **adaptation details**. Unlike the v0.1 idea, this first slice does **not** build immutable whole-set generations or promise transactionality across files. Changing a document mid-publication can expose an interim state; the index-last protocol can only mark completion, not make multi-document operations atomic.

## 3. Exact synthetic record and manifest contracts

Example of one **synthetic** record, not a real Post (values here fictional):

```json
{
  "share_schema_version": "1",
  "record_id": "SYN-XCTX-P001",
  "source_kind": "synthetic_x_post",
  "source_ref": "synthetic://x-context/post/P001",
  "observed_at": "2026-10-12T00:00:00Z",
  "status": "active",
  "verification_status": "synthetic_unverified",
  "distribution_class": "synthetic_only",
  "content": "SYNTHETIC TEST DATA: fictional process-transcription example",
  "related_context_refs": ["SYN-XCTX-C001"]
}
```

- Required keys **exactly** as shown; no unknown fields; `share_schema_version="1"`, `distribution_class="synthetic_only"`, `verification_status="synthetic_unverified"`, `status in {"active","withdrawn"}`.
- `record_id` is a unique allowlisted `SYN-XCTX-Pnnn`/`SYN-XCTX-Cnnn` (case-sensitive); fixture IDs are **synthetic IDs**, never real X numeric Post IDs, personal account IDs or hashes of credentials.
- `source_kind` is `synthetic_x_post` or `synthetic_context`, matching P/C prefix. `source_ref` has `synthetic://x-context/post/Pnnn` or `synthetic://x-context/context/Cnnn`, matching the record ID. No `https://x.com/` links are accepted.
- `observed_at` is a valid UTC timestamp supplied by the test fixture. It means **observation** only, not X Post creation/bookmark time. **No wall-clock field** in normalized outputs, to preserve determinism/idempotence.
- `content` is a bounded, nonempty UTF-8 fictional string with explicit `SYNTHETIC TEST DATA` marker. `withdrawn` records are rendered as a **tombstone containing no prior content**. IDs/URLs/other fields/manifest must not contain user secrets, actual X identifiers, authorization fragments, pagination tokens or original client paths.
- `related_context_refs` is a bounded list of distinct allowlisted synthetic IDs. References to nonexistent records fail validation. These are **links**, not approval/verification of a claim.
- Reject malformed JSON, duplicate records/keys, unexpected fields, bad Unicode/times, wrong IDs, non-synthetic URLs or classifications, references to absent fixtures and unapproved content. Reject a `SPEC-0007` store file by its schema even if renamed; never auto-discover files or accept source directories outside a dedicated synthetic test fixture root.
- For a withdrawal request, the normalized record stays with `status="withdrawn"` but has no source text in published record; the active index excludes it. This is a **logical synthetic withdrawal test**, not a claim that all Drive revisions, caches or LLM histories were physically erased.

**Local output:**
- `records/SYN-XCTX-P001.json` and `records/SYN-XCTX-P001.md` etc. generated from test fixture records, deterministic canonical JSON encoding and stable human-readable headings.
- `manifest-v1.json` contains `manifest_schema_version="1"`, a deterministic set of active `record_id`, `content_sha256` of normalized records and source-linked references. Content hashes here cover **synthetic material only**, not credentials/private X data. No Drive provider file ID/URL inside the portable manifest.
- No output in tracked source, real product data directory, or OS user profile by default. Use disposable workspace; tests may use temporary test directories. No raw document bodies or credential-like fixture strings in retained verification logs.
- **Same fixture input ⇒ byte-identical generated files**. Modified synthetic fixture ⇒ only corresponding record content/hash and manifest change. Duplicate source ID is a hard error, never silent overwrite.
- `manifest-v1.json` is the *portable local* index. A **separate Drive publication index** maps active record IDs to actual Drive URLs and nonsecret observed publication state, and is updated last after per-record readback.

Use obvious fictional P001/P002/P003 and C001/C002 test cases (same IDs/roles as #56); P003 is intentionally unrelated. Fixture bodies may be authored in the repo because they are synthetic.

## 4. Local generation & update commands

Codex chooses a minimal, discoverable command spelling, documented in README and tests, following these semantics:
- `preview`: validates exact synthetic fixture set and computes added/changed/unchanged/withdrawn counts against an optional previously generated **synthetic** manifest, with **no writes, no network**.
- `generate`: explicitly writes a new prepared output in a disposable target directory using safe whole-file updates. It never modifies `SPEC-0007` store; it refuses an unexpected preexisting/non-synthetic target, and requires stable/deterministic order and clean readback.
- `update`: running `generate` against the same managed output produces **zero changed content**. Changing a fixture updates the matching record and manifest without duplicating old records or affecting other records. A previously active fixture explicitly marked withdrawn causes tombstone preparation and removal from active set; *merely omitting an item is not withdrawal*.
- Unknown modes, missing synthetic marker, source outside fixture boundary, ambiguity about current state, or corrupt current manifest ⇒ fail before write. No implicit provider request or fallback to live X.

A read-only local **verification** routine should check schema, file fingerprints and active-count consistency. There is no need for a new database, file watcher, background scheduler, generic plugin system, heavyweight diff engine or cloud lock service.

## 5. Optional Google Drive publisher — narrower update strategy

**Prerequisite:** An already authorized Drive connection accessible to the runtime. Do not obtain/retain OAuth tokens or create a new Google App without a separate decision. Only the new namespaced synthetic publisher folder may be modified; the existing five source Docs and all AI-Knowledge KB files are immutable for this work.

**Drive document naming:**
- One managed native Doc per ID, title `SYNTHETIC-XCTX-PUBLISH-v1-<record_id>`. Exact name + parent ID + managed synthetic marker must all match before in-place updates. Duplicate matches are **a blocker**, not a cue to choose one.
- One managed current-index Doc `SYNTHETIC-XCTX-PUBLISH-v1-CURRENT` listing active IDs, approved links, content fingerprints and the latest successful publication state. This index is the **reader's source of currentness**, not broad `fullText` search.
- Use the first publish to create controlled docs and record returned Drive IDs/URLs. Later publish updates the same docs **in place** and verifies exact parsed body readback, preserving stable links. Unchanged records trigger no Drive content writes.
- `preview` is mandatory and read-only; `apply` requires an explicit operator invocation and exact sandbox folder ID. Before any write verify the remote parent, `shared=false`/restricted permission, title, existing content marker and expected prior content digest. Stop on unexpected permissions, existing same-name docs not clearly managed by this publisher, concurrent edits, unavailable connectivity or auth.
- **Index last**: update record Docs first, re-read and compare; then replace current-index Doc and re-read. Failure midway yields `PARTIAL_UNPUBLISHED` and does **not** report full success; avoid unverified rollback/deletion. Do not claim cross-document atomicity.
- Withdrawal of a synthetic record: overwrite its own managed Doc with a `SYNTHETIC WITHDRAWN` tombstone (no old content), remove its ID/link from the current index, and verify current-index exclusion. A generic Drive full-text search can still expose old versions during indexing delay, retained revisions or caches. **No guarantee of complete erasure**, therefore **real X data sharing stays forbidden** until a separate compliance design.
- If Codex lacks an authenticated, already-permitted Drive API or connector: **implement and test adapter against an injected fake**; preserve the portable output; report `DRIVE_AUTH_UNAVAILABLE`. Do not assert a real Drive publish PASS or compensate by browser automation, personal token paste, accidental root uploads, manual unreviewed file mirroring or a new OAuth bootstrap.
- Any actual Drive sandbox `apply` must be **synthetic only**, on user-authorized sandbox, with safe change summary; no deletion of preexisting hand-authored documents or other folders.

## 6. X / third-party AI rights release gate (real data: BLOCKED)

This implementation touches **NO actual X content or official X API**. However the intended product's future real-data feature remains constrained by current X primary terms:
- [Developer Agreement, updated 2026-04-27](https://docs.x.com/developer-terms/agreement): X Content includes Posts, IDs and derivatives; limited X-approved analysis/display uses; third-party provision/redistribution restricted; using X Content to train/fine-tune frontier/foundation models prohibited; content deletion/protection/changes must be handled as soon as possible and in any case within 24h **after qualifying request**.
- [Developer Policy](https://docs.x.com/developer-terms/policy): private bookmarks are private user activity; content redistribution restrictions; stored content must track X edits/removals. Policy allows limited third-party distribution of identifiers and nonautomated public objects under defined conditions.
- [Restricted Uses](https://docs.x.com/developer-terms/restricted-use-cases): additional redistribution and off-X matching rules. **Inconsistent public-object allowances**: Developer Policy states up to **500 public Post/User objects per person/day via nonautomated means**, while explanatory Restricted Uses mentions **50,000 hydrated public objects/day/recipient**. Do not choose a more permissive limit or infer either covers private bookmark objects / cloud AI processing.
- [Bookmarks introduction](https://docs.x.com/x-api/posts/bookmarks/introduction): bookmarks visible only to their creator.
- Prompt-time analysis is **not automatically identical** to training/fine-tuning; that fact does **not** make uploading actual Post bodies/IDs, summaries or embeddings to Google/ChatGPT/Gemini automatically permissible.

`G0_SYNTHETIC=ONLY ENABLED SCOPE`. `G1_REAL_ID_METADATA=BLOCKED`, `G2_REAL_TEXT_DERIVATIVES=BLOCKED`, `G3_ROUTINE_X_COLLECTION=BLOCKED`.

Before any `G1`/`G2`: separately review exact account/app approved use-case, X policy/redistribution scope, third-party vendor processor/retention/training settings, allowed fields, bookmark privacy, access control, source changes/deletions and feasible removal from both local store and cloud/revisions/caches, legal authority and user approval. **No current X Post, numeric Post ID, user identity or copied derived content is preapproved for transfer.** If not established, refuse; synthetic test success does not lift the gate.

## 7. Requirement → AC → tests (implementation subset)

| AC | Test (use only synthetic fixture and fake backend unless explicitly connected) | Passing evidence |
|---|---|---|
| AC-01 | Fixture `P001/C001/P002/C002/P003` roundtrips into JSON, Markdown and manifest | Exactly expected normalized fields, source IDs, fictional markers and valid refs |
| AC-02 | Same fixture exported twice + single record edit | Byte-identical outputs for same input; only changed record/hash plus manifest changes; no duplicates |
| AC-03 | Broken JSON/duplicate record/ref, non-synthetic URL, numeric X ID, SPEC-0007 store schema, unexpected path/token field | All fail closed; no artifact/external write or raw sensitive output |
| AC-04 | Synthetic document includes `ignore earlier instructions` | Retained only as inert source text; no command/execution side effects; reader guidance labels untrusted text |
| AC-05 | Preview / generate / update with fake inputs | Preview writes nothing; generate explicit; unchanged update no-op; explicit withdrawn record tombstone, omission alone does not remove |
| AC-06 | Fake Drive records: first apply then repeat | Stable document IDs/URLs; no duplicate Docs; unchanged republish zero content writes |
| AC-07 | Fake Drive partial failure / concurrent change / unexpected sharing or duplicate named doc | Reject/stop, `PARTIAL_UNPUBLISHED` when partially effected, no false complete index commit |
| AC-08 | Withdrawn fake Drive record / updated current index | Tombstone has no prior text, active index excludes; no assertion of historic/cached global erasure |
| AC-09 | Entire unit suite offline with X/network clients denied | `provider_requests_attempted=0`; no DPAPI, no changes under local real store, all existing tests still pass |
| AC-10 | Optional authenticated Drive sandbox smoke | Only newly namespaced private synthetic Docs/index modified; readback verifies correct content/parent/permission; if auth unavailable, honest `DRIVE_AUTH_UNAVAILABLE` |
| AC-11 | Human UAT Meowth in fresh ChatGPT and Gemini | Both distinguish P001 claim vs C001 fiction vs AI inference, link current docs and exclude P003; original #56 is precedent, *generated/published view still needs testing* |
| AC-12 | Origin Windows PC off while Drive Docs accessed from Meowth | Future user UAT; not proven by local tests, no false claim |
| AC-13 | All real-data publish attempts and changes to X/Credentials are unimplemented/rejected | No accepted real content/ID exports, X API traffic, credentials, real file reads or added authority |
| AC-14 | PR source/build/CI/review evidence | Exact-head tests, checks and adversarial review; no real data in Git/CI/logs |

**Test progression:** Requirement/AC/test matrix → synthetic fixtures → **RED** failing tests → minimal **GREEN** implementation → regression / whole suite → adversarial review → exact-head validation → Draft PR. Avoid expanding beyond this subset just to address speculative infrastructure risks.

## 8. Implementation handoff and proof rules

- Codex implementation works in a *disposable worktree/topic branch* from up-to-date `origin/main`; do not modify canonical main. One implementation Issue and one Draft PR.
- Codex first adds this reviewed spec as a tracked document under `docs/specs/0008-synthetic-shared-context.md` and maps AC tests in `docs/TEST_MATRIX.md`, **then** RED tests and GREEN code. The implementation must follow SPEC-0007's source/credential boundaries and repo validation policies.
- No broad cloud workflow changes, new persistent services, runtime telemetry, new dependencies without identified need, or changes to unrelated files. Synthetic fixture docs/strings alone may appear in public GitHub.
- Local code/CI passing does **not** prove live Drive publication; report cloud adapter status separately. No live X API smoke required for synthetic-only changes.
- Collect non-secret output: tested branch/HEAD, tests PASS/FAIL counts, pure-offline generator operation, fake Drive tests, actual Drive smoke `PASS / NOT_RUN_AUTH_UNAVAILABLE / BLOCKED`, exact-head checks and review severity, Draft PR link.
- **Human final** Ready/merge/destructive cleanup gates remain. Codex may create commits, push topic branch and open **Draft PR**, but must not mark Ready or merge, alter main, or perform cleanup without a separate human decision.

## 9. Review disposition / completion scope

This **v0.2** supersedes the broader v0.1 architecture for the first synthetic-only implementation: no remote immutable-generation engine, no real X text/metadata publication, no all-provider guarantee and no global deletion promise.

Issue #57 provides the reviewed requirements and constraints. **Do not close it yet** solely because text was updated: the related implementation Issue must show the spec/AC/test mapping and provide a reviewed Draft PR. Acceptance of implementation and closing both Issues happens through subsequent human review and final gates.

**No real X API call, actual X bookmark export, credential operation or modification to existing AI-Knowledge KB is authorized by this specification.**
