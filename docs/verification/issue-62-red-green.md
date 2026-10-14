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
