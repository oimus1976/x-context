# Issue #62 — Requirement / AC / RED / GREEN checkpoint

Base: 440073d52584d7a9a6c1fd9960795d5999db8f69 (merged #61).
Branch: codex/issue-62-drive-api. Risk HIGH_IMPACT: CREDENTIALS,
EXTERNAL_WRITE, SECURITY_BOUNDARY, PLATFORM_DEPENDENT. Owner C2 required.
Read current Issue60/62, merged59/61, SPEC0008, ADR0004/0005.

Requirement/AC addendum and TEST_MATRIX precede tests/code. Initial RED:
one import failure for missing google_api, NOT18 observed behavioral failures.
GREEN: initial18 PASS. Initial regression: 360 PASS, failures/errors/skips0,
90.813s, Windows11 10.0.26300 / Python3.12.10 / IsUserAnAdmin=False,
baseline/diff PASS. Seven added abuse/process contracts give new25 PASS.
Independent separate Codex design L2 before implementation: CRITICAL0/MAJOR0.
Implementation L2, final exact-head regression/hosted CI are separate evidence.

API tests show writes6/0/2/2/2 for first/no-op/edit/withdraw/restore, stable IDs,
CURRENT last. Five fresh Python subprocesses load persisted fake cloud/registry/
credential state and refresh expired fake access with no browser; each COMPLETE,
refresh exactly1, IDs unchanged. No external HTTP. Fake CLI flow covers all modes.
Permissions/pages/unknown IDs/revisions/text/readback/journal failures fail closed.
Unicode/UTF16/application LFs preserved. Windows real DPAPI writes TEMPORARY
FAKE credentials only, proves roundtrip/plaintext absence and protect-failure
preservation; this is not real Google credential persistence/consent/lifetime.
Existing synthetic X DPAPI regression is retained.

LIVE_GOOGLE_AUTH_PENDING: project/client/first consent/real credential saving and
live Python publish NOT_RUN. No actual X/bookmark/private source read or sharing,
original PoC/sentinel mutation, Ready/merge/cleanup/scheduler. Meowth/PC-off are
OPTIONAL/DEFERRED, never PASS. Owner must approve concrete account/project/scope/
storage/revoke plan before bootstrap; code/fake tests do not grant that authority.

## Exact-head review and validation checkpoint

At 960ad4c4623d0bf0557f57431efc55c455d726a3, parent independently ran all
367 tests PASS (100.344s), no failures/errors/skips; baseline/diff PASS, clean
topic and canonical main. Separate Codex implementation L2: CRITICAL0/MAJOR0/
MINOR1; independent Google25 and shared-context52 tests PASS. MINOR1 identified
missing approved-bootstrap fake integration coverage, with no observed bug.
Four added fake server/browser/token/store tests now cover success, wrong-state
then success, denied/wrong-state timeout, widened/missing initial scope, missing
refresh, exchange and persistence failures. They perform no HTTP/browser/real
auth. New29 PASS. No implementation change; final relevant exact-head suite and
independent delta review are recorded in the Draft PR after the new commit.

Fake API observed first publication uses231 Docs GETs and859 Drive calls.
Quota/cost qualification is documented using current official limits: project
quotas may vary; avoid rapid successive invocation; no blind mutation retry.
Live latency, quota behavior, token exchange and native metadata remain NOT_RUN.

## PR #63 review #5505171117 — official Desktop auth_uri compatibility

Date: 2026-10-14 JST. Starting exact head:
`e061e20ca732431fa9dca634089d23c7d87f8bbc`; same existing branch
`codex/issue-62-drive-api`. Risk HIGH_IMPACT: CREDENTIALS, SECURITY_BOUNDARY;
GitHub publication is an authorized EXTERNAL_WRITE. Scope is the metadata
compatibility correction, tests and requirement/evidence documentation only.

1. Requirement: A02 addendum and TEST_MATRIX bind accepted metadata to exactly
   Google's official legacy/v2 URLs, actual authorization to compiled v2, token
   metadata to the existing exact URL and invalid metadata to zero auth effects.
   Google's public installed-client example and native-app guide were checked;
   no downloaded real client file was inspected.
2. RED before production edits:
   `python -m unittest discover -s tests -p test_shared_context_google.py -k bootstrap_official_auth_uri_metadata -v`
   ran one test with one failed legacy-URI subtest:
   `AssertionError: 'GOOGLE_BOOTSTRAP_FAILED' is not None`. The v2 subtest passed.
   A preceding sandbox attempt failed on temporary-directory ACLs and is NOT
   behavioral RED evidence. The recorded RED/GREEN runs use normal non-admin
   Windows execution outside that sandbox restriction.
3. GREEN after the explicit two-entry tuple allowlist:
   `python -m unittest discover -s tests -p test_shared_context_google.py -k bootstrap -v`
   passed all 8 tests in 0.999s. Three new test methods cover both accepted
   literal URLs, missing/non-string/hostile auth metadata and nonexact token
   metadata. Fake server/browser/exchange and in-memory save assertions prove
   invalid metadata has zero authorization effects. Existing bootstrap tests
   now default to literal provider-shaped legacy metadata instead of copying
   production constants. Success asserts actual v2 destination and exact scope.
4. Regression before commit: `python -m unittest discover -s tests` passed
   all 374 tests in 100.102s, zero failures/errors/skips. Baseline
   `python scripts/verify_repo.py --repository oimus1976/x-context` and
   `git diff --check` passed. No existing test was removed or weakened.

Environment: Windows 11 10.0.26300, Python 3.12.10, IsUserAnAdmin=False.
Only temporary fictional JSON, fake tokens and existing synthetic fixtures are
used. Actual Google authentication, actual credential read/save and Drive API
traffic are NOT_RUN. Ready, merge and destructive cleanup are not performed.
Final exact-head tests, hosted CI and independent delta L2 are recorded in the
Draft PR against the published commit, separately from this pre-commit checkpoint.

## PR #63 review #5518750357 — RFC 9207 callback issuer

Date: 2026-10-14 JST. Starting exact head:
`2505229003cfeff382eb0388097e30dc4f278e0d`, existing branch
`codex/issue-62-drive-api`. HIGH_IMPACT: CREDENTIALS, SECURITY_BOUNDARY,
PLATFORM_DEPENDENT; authorized GitHub publication is EXTERNAL_WRITE.

Requirement: the A02 addendum/TEST_MATRIX require exactly one form-decoded
`iss=https://accounts.google.com`, no normalization, and reject missing issuer
because Google's public metadata declares support. RFC 9207 section 2.4 and the
public Google discovery document were checked; no actual client JSON or prior
callback URL/code/screenshot was read or copied. Every supplied key must be
single-valued; unknown keys remain forbidden even when blank/bare.

RED before production edits:
`python -m unittest discover -s tests -p test_shared_context_google.py -k bootstrap_google_issuer_callback -v`
ran 1 test in 0.020s, FAIL with
`AssertionError: 'GOOGLE_BOOTSTRAP_FAILED' is not None`.
The literal fictional callback includes issuer, scope, authuser and prompt, and
uses only a fake server/browser/token exchange/in-memory store. This reproduces
the old rejection without reusing any operator OAuth response.

GREEN after the issuer check and blank-preserving parse:
`python -m unittest discover -s tests -p test_shared_context_google.py -k bootstrap -v`
passed 12 tests in 0.829s. Four new methods cover the Google-shaped success,
missing/blank/hostile/nonexact issuer, duplicates of every allowlisted key
(including blank duplicates and percent-encoded key names) and unknown nonempty,
empty and bare keys. Every rejected callback asserts HTTP 400, zero exchange,
zero save and only the safe failure category. Existing state/PKCE/token/scope
and persistence assertions remain; valid fixtures now include literal issuer.

Pre-commit full regression: `python -m unittest discover -s tests` passed all
378 tests in 91.704s, zero failures/errors/skips. Baseline
`python scripts/verify_repo.py --repository oimus1976/x-context` and
`git diff --check` passed. No pre-existing test was removed or weakened.

Environment: Windows 11 10.0.26300, Python 3.12.10, IsUserAnAdmin=False.
Normal non-admin execution was used for RED/GREEN. No real Google login retry,
actual credential read/save, Drive write, Ready, merge or cleanup is performed.
The operator's earlier HTTP 400 report does not establish token/save/CLI outcome.
Committed exact-head verification and independent delta L2 belong to the final
Draft PR evidence, not this pre-commit RED/GREEN checkpoint. The validation
runner that automatically removes its temporary worktree is deliberately not
used: exact-head checks run on the clean committed topic worktree, preserving
all existing worktrees/branches as requested.


## PR #63 review #5528374222 - t.0 and registered-empty-first-create

Starting HEAD: 4209f4bb3a9fad8c4ae33aa0f0c2ed4fa218279a,
branch codex/issue-62-drive-api. Risk HIGH_IMPACT: external writes, private
publication state, security boundary and Windows platform behavior.

RED (before production edit):
`python -m unittest discover -s tests -p test_shared_context_google_tab_ids.py -v`
ran 5 methods in 0.020s, FAILED (errors=4): three Google-shaped empty/Unicode/LF
subcases and replace_text raised UNSUPPORTED_NATIVE_TEXT for literal t.0.
Hostile/file-ID guards and interrupted-create journal preservation passed.
No real provider response or actual state file was copied into fixtures.

GREEN after the dedicated tab validator: the same initial five methods passed
in 0.013s. Two later boundary/revision methods also passed: final tab-ID suite
7/7 in 0.013s. Read-only recovery-inspection suite 5/5 in 0.028s. Existing
FakeAPI now returns t.0, exercising baseline/edit/withdraw/restore/stable-ID
and CURRENT-last through that actual-shaped field. New native response fixtures
use real-shaped paragraph boundaries and Japanese/astral UTF-16/LF indexes.
Drive file/path IDs still reject dots before token access.

Pre-commit Windows regression (before the final two added boundary methods were
loaded): `python -m unittest discover -s tests -v`, 388/388 PASS, 118.345s,
failure/error/skip 0. The final seven-method focused tab suite passed afterward.
Baseline verify_repo, compileall and diff-check passed. Final committed exact-head
full regression/CI/L2 results must be read from the PR's final evidence comment;
this checkpoint is not substituted for those results.

Read-only local diagnosis: valid schema, one registered C001, no CURRENT,
exactly CREATE_ATTEMPT then CREATED_EMPTY_UNVERIFIED, latter ID matches registry;
folder/parent/owner/namespace initialized, bytes unchanged across the read.
No IDs, private paths, tokens, DPAPI contents or private document payload are
included here. Remote blank/private/folder facts remain review observations.
No Google product API call, credential read/refresh, actual state mutation,
publication retry, Ready/merge or cleanup was performed by this correction.
The explicit current instruction forbidding real Drive changes also means KB
updates must remain a local unsent summary for this turn.

The recovery deliverable is a DESIGN plus a fake-tested read-only inspector,
not a resume executor. See docs/specs/0008-first-create-recovery.md for the
four owner criteria, retained journal design, exact-ID conditional continuation,
CURRENT-last rule, failure injection requirements and remote/local commit gap.
Ordinary pending barriers, partial-set rejection and no automatic retry remain.
As in the previous correction, committed exact-head checks use the retained clean
topic checkout; the runner that removes a temporary worktree is not invoked.


## Review #5532355581 - first-create executor requirement-first RED/GREEN

Starting HEAD 69395fa560a87c3f16b70c3df746fed94a53f581 on the existing branch.
REC-01..07 were written in the recovery spec before tests/production changes.
RED: `python -m unittest discover -s tests -p test_shared_context_google_resume.py -v`
ran nine tests in 0.033s, errors=9 because plan_first_create/resume_first_create/
Journal did not exist. This is a missing-feature RED, not a reproduced new
provider bug. No old test was removed or weakened.
GREEN: the same nine passed in 63.161s after implementation. Two additional
focused methods for unsafe paths/corruption/fsync and post-effect body/ID/
metadata mismatches passed separately (0.054s / 0.024s). The full final suite
includes all eleven methods and all existing tests.

HTTP fault injection enumerates all 1,241 fake requests in the successful path,
before and after each request (2,482 interruption points). Journal injection
covers 29 writes before/after (58 points), including exclusive claim, each
intent/returned ID/verified receipt and completion save. Each asserts stopped
subsequent effects, unchanged original state and no automatic re-entry/retry.
Temporary real-file tests verify append-only/exclusive/fresh-instance readback,
original registry bytes unchanged, corrupt/oversized/junction/path rejection and
fsync error retention. All fixtures, IDs and approval references are fictional.

One fake successful continuation performs 11 mutation attempts: same-ID C001
text, four remaining creates/text and CURRENT create/text last. The final index
has five records bound to stable C001 ID. Original v1 pending is never modified;
ordinary publish stays blocked even after sidecar COMPLETE. The sidecar records
original state/digests, approval reference, intent, returned IDs, verified body/
revision receipts and final manifest. No generic interrupted-run reconciliation,
registry migration, credential loader or live CLI is added.

Full Windows, committed exact-head CI and independent L2 are later checkpoints
and must not be inferred from this focused GREEN record. No real registry read
or mutation, credential read/save, real Google access, Ready/merge/cleanup or
live recovery is performed. Local KB updates remain unsent under the current
explicit prohibition on actual Drive changes.


Pre-commit Windows full regression: 401/401 PASS in 185.590s, failures/errors/
skips 0. This run loaded the eleven new methods before the final aggregate-size
precheck and returned-ID-before-next-request assertion refinement. Those two
focused methods then passed in 0.071s / 0.042s. The committed exact-head full
rerun is required for the final refinement; this checkpoint is not that evidence.
Baseline verify_repo, compileall (x_context/tests/scripts), diff-check PASS.
No pre-existing tests/assertions were removed or weakened.
