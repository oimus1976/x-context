# SPEC-0008 addendum: unattended app-scoped synthetic publisher (Issue #62)

Authority: Issue #62, latest main 440073d52584d7a9a6c1fd9960795d5999db8f69,
merged PRs #59/#61. Risk HIGH_IMPACT: credentials, external write, security
boundary and Windows platform. Synthetic compiled fixtures only; X acquisition,
X credentials, original PoC/Issue60 files and real-data gates are unchanged.

## Narrow contract under independent review

The new backend uses only https://www.googleapis.com/auth/drive.file with a
user-owned Desktop OAuth client. It creates a fresh private My Drive folder.
It must never adopt old connector-created files or search by title to authorize
an update. A local registry binds folder/doc IDs to appProperties and roles.
Owner-only metadata and exact parent, identity, title, prior body and revision
are checked before effects. Unknown visible children, duplicates, missing IDs,
missing pagination/metadata, incompleteSearch and revision conflicts fail closed.

Unlike the unchanged Issue60 transport, this backend proves completeness only
within the app-authorized visible file set. Hidden owner-added files cannot be
excluded by drive.file; no global inventory guarantee is made. The single-owner
operator must reserve the fresh folder for this app. The reduced threat model
applies ONLY to compiled synthetic data; it does not lift real X sharing gates.
No broad drive/metadata/documents scope, service account, sync service or daemon.

Reuse drive.preview/apply for snapshot comparison, stable URLs, no-op,
withdrawal and CURRENT-last. Reuse connector checks/receipts/body allowlist.
Create empty native Docs using Drive files.create with parents, verify privacy
and placement, then write through Docs requiredRevisionId. One tab, plain text,
UTF-16 indexes; remove only the provider's structural final newline on read and
restore it through provider structure, preserving every application newline.
Unsupported tables, objects, tabs and suggestions block rather than flatten.

Persistent single-writer journal is written before every remote effect.
Pending/ambiguous effects block subsequent processes. Successful publication
requires final full readback then journal commit; failures preserve inspection
state. No automatic retry, adoption, deletion or rollback. IDs are nonsecret
local state; credential envelope is separate DPAPI CurrentUser protected storage.

## Requirements / AC / test progression

| Requirement | AC | Automated RED then GREEN contracts |
|---|---|---|
| Synthetic-only source | A01 | named fixtures, invalid CLI before auth, existing suite |
| Minimal credentials | A02 | exact scope, protected store, redaction, refresh failure preserves old record |
| App-owned target | A03 | ID registry, namespace/role, owner-only, parent, unknown/stolen ID rejection |
| Visible inventory | A04 | all MIME pages, empty page with next token, duplicate/cyclic/missing/incomplete receipt |
| Native text updates | A05 | UTF-16/Unicode/LF, conditional revision, CURRENT last, ambiguity journal |
| Stable diff behavior | A06 | first publish, repeat zero write, edit only P001+CURRENT, tombstone, restore IDs |
| Unattended invocation | A07 | new lifecycle/backend instances load state and refresh without browser |
| Multi-AI proof | A08 | LIVE_AUTH_PENDING; new app folder reader test after consent, optional Meowth/PC-off |
| Evidence | A09 | regression, Windows synthetic DPAPI, exact-head baseline/CI, independent L2, Draft PR |

### A02 Desktop client metadata compatibility (PR #63 review #5505171117)

Accept `installed.auth_uri` only when it exactly equals either
`https://accounts.google.com/o/oauth2/auth` (Google's installed-client JSON
example) or `https://accounts.google.com/o/oauth2/v2/auth`. The actual browser
authorization request must always use the compiled v2 endpoint, never the
metadata as a request destination. Keep `installed.token_uri` exactly
`https://oauth2.googleapis.com/token`; this change does not add token aliases.
Reject missing/non-string metadata, other hosts, schemes, ports, userinfo,
paths, query parameters, fragments and whitespace before browser/server/token
effects or credential saving. Tests use only fictional downloaded-shaped JSON,
fake callback/browser/exchange and an in-memory store. No real credentials,
Google authentication or Drive API traffic are needed to establish this contract.

Primary references checked 2026-10-14:
- https://developers.google.com/api-client-library/dotnet/guide/aaa_client_secrets
- https://developers.google.com/identity/protocols/oauth2/native-app

### A02 callback issuer (PR #63 review #5518750357)

Google callback responses must contain exactly one `iss`, whose form-decoded
value is exactly `https://accounts.google.com` (simple case-sensitive string
comparison, without URL normalization). Missing or empty issuer is rejected:
Google's public metadata declares RFC 9207 support, so older issuer-less
callbacks are deliberately unsupported. No runtime discovery or new endpoint
selection is introduced. The only newly allowed key is `iss`; the complete
allowlist remains `state`, `code`, `scope`, `authuser`, `prompt`, `iss`.
Every supplied key must have exactly one value, including optional keys and
blank values; unknown keys (even blank/bare) and duplicate decoded keys fail
closed. Existing exact state, safe single code, fixed token endpoint, redirect,
S256 PKCE and timeout checks remain. Rejection returns HTTP 400 and cannot
record a code, exchange tokens or save credentials. Diagnostics never echo
callback URLs/values. A later valid callback may still complete within timeout.

Primary references checked 2026-10-14 (public, no authenticated API request):
- https://www.rfc-editor.org/rfc/rfc9207.html#section-2.4
- https://accounts.google.com/.well-known/openid-configuration

## Explicit owner authorization gate (not executed in this change)

Before creating a project/client, opening first consent or saving credentials,
the owner must choose account/project and approve this plan:
1. Create/select personal Google Cloud project, enable Drive and Docs APIs.
2. Configure external consent with drive.file ONLY, Desktop client; no Workspace
   admin/domain delegation. Keep downloaded client configuration outside Git.
3. Explicit login uses system browser, loopback 127.0.0.1, state and S256 PKCE,
   offline access; granted scope must match exactly. Never paste tokens in chat.
4. Store entire Google credential envelope at
   %LOCALAPPDATA%/x-context/google-drive/credential-v1.dpapi, separate from X.
   DPAPI protects at rest, not against same-user processes; never plaintext token.json.
5. Explicit sandbox init creates a new private folder and records returned ID.
   Afterward one-shot preview/apply needs no manual Drive edits; refresh before
   expiry. API quotas/provider failures stop without retries; no infinite-token claim.
6. External Testing refresh tokens expire after 7 days for this scope. Production
   status is a separate owner decision, not an automatic change. Expiry/revocation
   requires explicit reauthorization; preserve publisher registry/journal.
7. Recovery starts with journal and Drive IDs. Google account third-party app
   access removal revokes the grant; deleting local credentials alone does not.
   No automatic remote cleanup, content-history purge or Task Scheduler setup.

LIVE_GOOGLE_AUTH_PENDING: no new Google project, client, consent, credential
persistence or authenticated product API call is authorized/performed now.
The offline transport implementation is reviewable independently of that gate.

Primary sources checked 2026-10-13:
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list
- https://developers.google.com/workspace/drive/api/reference/rest/v3/files/create
- https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate
- https://developers.google.com/identity/protocols/oauth2/native-app
- https://developers.google.com/identity/protocols/oauth2

PC-off and Meowth UAT are OPTIONAL/DEFERRED, not PASS and not release blockers
for Issue62. New folder ChatGPT/Gemini evidence still requires approved live setup.
Ready and merge remain human-final; Draft code completion is not live qualification.

## Quota and cost qualification before approved live setup

Confirm actual project quotas/billing with the owner, not only public defaults.
Current official Docs default is 300 reads/60 writes per user per project per
minute. This five-record fake first publication observes 231 Docs GETs and 859
Drive calls (checks are deliberately repeated). These are fake call counts,
not measured live usage/latency. Back-to-back runs can exceed quotas; avoid rapid
repeats and wait for a new quota window before the next operator invocation.
Provider throttling/403/429 stops; no automatic mutation retry. A partial run
retains the pending journal and needs inspection, not blind repeat. Drive limits
changed for newly created projects in May2026 and quota-unit/daily billing rules
must be checked on the chosen project. No quota increase/billing change occurs.
- https://developers.google.com/workspace/docs/api/limits
- https://developers.google.com/workspace/drive/api/guides/limits
