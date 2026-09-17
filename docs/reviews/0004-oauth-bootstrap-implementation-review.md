# Review-0004 — OAuth bootstrap implementation adversarial review

- **Review type:** adversarial implementation review
- **Date:** 2026-09-17
- **Issue:** #36
- **Draft PR:** #37
- **Reviewed implementation/docs through head:** `ec42a18ad78fbfb1541eccc6e845513205b0b2c9`
- **Base main:** `4f0bd3151d737b5ea40cb1891ca0a97fa3fa1efc`

## Question

Does the proposed `auth login` slice compose the already-accepted OAuth acquisition and credential-lifecycle boundaries without silently broadening X authority, leaking ceremony/credential secrets, damaging a previously committed credential on failure, or bypassing the repository's bounded-effect contracts?

## Evidence inspected

- Issue #36 requirement and AC boundary;
- `docs/specs/0004-oauth-bootstrap-cli.md`;
- `x_context/cli.py`;
- existing `x_context/oauth.py` acquisition/configuration/normalization boundary;
- existing `x_context/credential_lifecycle.py` persistence/refresh/storage boundary;
- `tests/test_oauth_bootstrap_cli.py`;
- `tests/test_oauth_bootstrap_cli_security.py`;
- `docs/TEST_MATRIX.md`, `README.md`, `PROJECT_STATUS.md`, and `CHANGELOG.md`;
- hosted branch-head test evidence available during the review;
- X official OAuth 2.0 Authorization Code + PKCE documentation re-read on 2026-09-17.

No real provider credential, callback code, private X payload, or DPAPI protected blob was used or retained by this review.

## Authority review

### Finding: no new X data authority identified

`auth login` does not introduce a content endpoint. It delegates authorization construction to the existing acquisition boundary with `refresh_capable=True`. That boundary requests the existing P0 read scopes and adds only `offline.access` for refresh capability.

No CLI scope override exists. No write, DM, follows, list, block, mute, OAuth 1.0a, scraping, browser-cookie, or internal API path is added.

**Disposition:** acceptable within the existing P0 authority boundary.

## Configuration and effect ordering

### Finding: configuration and secure-store availability are checked before browser launch

The CLI constructs `OAuthConfig` from `X_CONTEXT_OAUTH_CLIENT_ID` and `X_CONTEXT_OAUTH_REDIRECT_URI`, then resolves the lifecycle store before calling the acquisition function. Existing `OAuthConfig` validation requires a safe public Client ID and the fixed IPv4 loopback callback shape. The acquisition implementation retains its existing bind-before-browser and one-exchange bounds.

Unsupported default-store environments therefore fail before opening a browser, and no plaintext storage fallback is introduced.

**Disposition:** acceptable.

## Persistence and recovery

### Finding: pre-commit failures do not replace the prior credential

The bootstrap does not touch the lifecycle store until acquisition succeeds and bootstrap-specific checks confirm both a refresh token and a positive expiry duration. Persistence then goes through `persist_oauth_result(...)`, which delegates replacement to the existing lifecycle store contract.

Tests exercise configuration failure, acquisition failure, missing refresh token, missing expiry, and storage replacement failure with a pre-existing record. The failed paths retain the previous committed record in the synthetic store contract, while the underlying lifecycle suite already covers atomic replacement failure and real Windows DPAPI round-trip behavior.

`X_CONTEXT_USER_ACCESS_TOKEN` is not read as bootstrap input and is not imported into managed storage.

**Disposition:** acceptable; Windows exact-head validation remains required because the production default store is platform-dependent DPAPI.

## Secret-handling review

### Finding: controlled CLI output is allow-listed and parser errors do not echo credential-shaped values

The new success object contains only operation/status/persistence/refresh-capable booleans. Handled errors contain stable categories rather than provider/OS exception prose.

Additional adversarial tests pass credential-looking values as an unsupported `--token` option and as an extra positional argument and assert that parser rejection neither launches OAuth nor reflects those values into stdout/stderr.

The existing OAuth boundary continues to hide authorization URL/state/verifier/token request material from repr/error surfaces, and the lifecycle boundary continues to hide access/refresh tokens and protected credential contents.

**Disposition:** acceptable.

## Provider-response compatibility

### Finding: strict expiry requirement is safe but requires real-provider qualification for compatibility

X's current official OAuth guide documents `offline.access` as the mechanism that causes refresh-token issuance, but the current guide pages inspected during this workstream do not establish `expires_in` as a product invariant.

The bootstrap deliberately does not infer the guide's stated default access-token lifetime or synthesize an expiry. A normalized token result without a positive `expires_in` fails before persistence.

This is fail-closed and avoids fabricating lifecycle state, but it leaves one external compatibility question: whether the current real provider response always supplies the positive expiry value required by this managed bootstrap.

**Disposition:** not a merge blocker for the synthetic contract. Record as a real-provider qualification item. Real browser/provider qualification remains human-gated and must retain only non-secret facts.

## Documentation findings remediated during review

1. README originally showed cmd.exe-style `set` commands even though the supported default persistent path is Windows DPAPI and the operator workflow commonly uses PowerShell. The example was changed to `$env:...` PowerShell syntax.
2. TEST_MATRIX initially named `AC-BOOT-01..12` while SPEC-0004 listed only anonymous numbered criteria. SPEC-0004 now names the same AC identifiers explicitly.
3. Issue #36 originally described `X_CONTEXT_OAUTH_REDIRECT_URI` as only a candidate configuration source. The Issue/spec now agree that it is the selected non-secret redirect configuration source.
4. SPEC-0004's work-order footer originally spoke as though tests/implementation were still future work. It now records the actual Requirement -> AC -> Test -> Implementation branch history.

These were documentation/traceability defects, not changes to provider or credential authority.

## Residual uncertainty

- Real provider/browser login has not been executed and remains a human-gated qualification action.
- Hosted Linux CI cannot exercise Windows DPAPI; the current PR head therefore still requires authoritative Windows exact-head validation including the real-DPAPI synthetic test.
- If a real provider result omits `expires_in`, this bootstrap will fail closed by design; any decision to support such a response would require a new requirement/AC decision rather than silently assuming a lifetime.

## Review result

No material implementation blocker was identified after the documentation/traceability remediations above.

This review does **not** authorize Ready or merge. Before the human Ready gate, the final PR head must still have:

1. hosted `project-ci` and `policy-check` success on that exact head;
2. authoritative Windows exact-head validation through the tracked validation runner, including full tests, the real Windows DPAPI synthetic test, `git diff --check`, and clean final-state checks;
3. a final diff/head check confirming no later behavior change invalidated this review.

Because committing this review record itself moves the branch head only by documentation, its own commit does not invalidate the reviewed executable behavior, but the final-head checks above remain required.