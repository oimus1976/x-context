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
