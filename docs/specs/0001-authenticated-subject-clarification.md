# SPEC-0001 clarification — authenticated subject boundary

- **Status:** Normative clarification for Issue #11
- **Base specification:** `docs/specs/0001-mvp.md`
- **Scope:** Shared authenticated-subject resolution/binding boundary required before FR-003 bookmarks and FR-004 likes

## 1. Purpose

SPEC-0001 requires authenticated collection reads to target only the currently authenticated X user. Issue #11 isolates the common identity boundary before either collection is implemented so bookmarks and likes cannot acquire separate, inconsistent subject logic.

This clarification narrows only the subject-resolution/binding slice. It does not authorize bookmarks/likes payload retrieval, OAuth browser flow implementation, token persistence, write authority, arbitrary target-user reads, or unofficial acquisition.

## 2. External-provider facts

The implementation uses the official authenticated-user lookup endpoint:

```text
GET https://api.x.com/2/users/me
```

The response is the authority for the authenticated subject. Current X endpoint names, accepted authorization flows, scopes, prices, limits, and billing behavior remain external platform facts and must be re-verified at the collection integration boundary where they matter.

No provider scope list or rate-limit number becomes a hard-coded product correctness constant in this slice.

## 3. Credential boundary

The app-only credential already used by FR-002/FR-006 `read` and the later user-context credential are different authority classes.

- `X_CONTEXT_BEARER_TOKEN` remains the app-only credential source for the current `read` CLI.
- Future authenticated collection commands use a distinct user-context source named `X_CONTEXT_USER_ACCESS_TOKEN`.
- No fallback from the user-context source to `X_CONTEXT_BEARER_TOKEN` is permitted.
- Missing, empty, or CR/LF-bearing user-context tokens are rejected locally as `configuration_error` before transport.
- Provider/domain helpers accept an explicit user-context token; environment lookup remains a caller/CLI boundary concern.

The slice does not implement Authorization Code + PKCE browser interaction, refresh-token persistence, keyring storage, or config-file credential storage.

## 4. Authenticated subject model

The minimum subject value contains:

- `id`: required non-empty ASCII-decimal X user ID string;
- `username`: optional non-empty string when safely present in the authenticated-user response.

No display name, profile fields, metrics, description, location, image URL, or arbitrary provider fields are carried into this domain contract.

A missing/invalid subject ID, invalid username shape, malformed JSON, missing `data`, or another contradictory success shape fails closed as `provider_error`. The implementation does not fabricate or infer identity from local configuration, requested target, token contents, cached username, or another endpoint.

## 5. Official request contract

Subject resolution performs one official provider request:

```text
GET https://api.x.com/2/users/me
Authorization: Bearer <user-context-access-token>
Accept: application/json
```

This slice requests no optional `user.fields` or expansions. Minimum default provider fields are sufficient when `id` is present; `username` is retained only when safely returned.

A successful resolution exposes only:

- normalized subject;
- allow-listed safe rate metadata already used by the provider layer;
- provider requests attempted = 1.

Local credential rejection reports zero provider requests. Unexpected transport exceptions are converted to a stable `provider_error` with one attempted request and no exception chaining.

## 6. Failure contract

Existing stable categories are reused:

- `configuration_error` — missing/unsafe local user-context credential;
- `authentication_failed` — safely established provider authentication failure;
- `authorization_failed` — safely established provider authorization/scope failure;
- `rate_limited` — safely established provider rate-limit response;
- `usage_blocked` — safely established provider usage/credit/spending gate;
- `provider_error` — malformed/ambiguous/unexpected provider or transport failure;
- `invalid_input` — invalid local target identifier supplied to the binding helper;
- `subject_mismatch` — a valid target user ID differs from the authenticated subject.

`resource_unavailable` is not used to fabricate meaning for an authenticated-user lookup when the provider does not safely establish such semantics; ambiguous failures remain `provider_error`.

Provider raw payloads, Authorization headers, token values, arbitrary headers, and underlying transport exception text must not enter normal exception text, diagnostics, repr, traceback chaining controlled by this boundary, or committed evidence.

## 7. Same-subject binding

The shared binding helper receives a resolved authenticated subject plus the target user ID that a later internal collection call intends to place in `/2/users/{id}/...`.

- target ID must be a non-empty ASCII-decimal string;
- exact equality with `subject.id` succeeds and returns/authorizes that same ID;
- a valid but different ID fails as `subject_mismatch`;
- invalid target input fails as `invalid_input`;
- the binding check performs no network access.

This helper does not create an arbitrary-user feature. FR-003/FR-004 CLI still expose no user-ID positional argument or option; the future collection integration passes only its internally resolved target through this guard.

## 8. NFR-005 accounting boundary

`/2/users/me` is a provider request. Subject resolution therefore returns a request-attempt count and safe rate metadata so later collection commands can account for their total provider work without adding provider metadata to canonical JSON.

This slice does not decide whether every future collection invocation must resolve `/users/me` immediately before the collection request or whether an in-process subject result may be reused. That execution/cost policy belongs to the collection integration workstream and must preserve identity correctness, fail-closed behavior, and truthful NFR-005 accounting.

## 9. Acceptance criteria

Issue #11 owns `AC-AUTH-SUBJ-01..12` as recorded in the Issue. The concrete test matrix is authoritative for automated evidence names.

## 10. Evidence / governance

Required order:

1. normative clarification;
2. TEST_MATRIX mapping;
3. contract/security tests;
4. minimal implementation;
5. adversarial review;
6. authoritative local exact-head validation;
7. Draft PR;
8. human Ready / merge.

Tests use fake user-context credentials and fake transports. Any real `/users/me` smoke is optional qualification evidence requiring an intentional human decision because it touches a real account identity and may consume API usage.
