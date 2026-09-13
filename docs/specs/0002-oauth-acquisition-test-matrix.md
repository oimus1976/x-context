# SPEC-0002 OAuth acquisition test matrix

- **Status:** Planned contracts before implementation
- **Date recorded:** 2026-09-14
- **Related:** Issue #23, `0002-oauth-acquisition-clarification.md`
- **Integration note:** These mappings must be folded into canonical `docs/TEST_MATRIX.md` before PR. Direct canonical-file update was blocked by the current GitHub connector write guard; this file preserves Requirement -> AC -> Test ordering without weakening the contract.

| Acceptance criterion | Planned automated evidence |
|---|---|
| AC-OAUTH-01 | `test_OAUTH_uses_official_authorize_endpoint_and_read_scopes` |
| AC-OAUTH-02 | `test_OAUTH_public_client_uses_client_id_without_secret` |
| AC-OAUTH-03 | `test_OAUTH_generates_fresh_state_and_verifier_per_attempt` |
| AC-OAUTH-04 | `test_OAUTH_derives_s256_challenge_without_plain_fallback` |
| AC-OAUTH-05 | `test_OAUTH_uses_exact_registered_redirect_and_scope_set`, `test_OAUTH_offline_access_is_explicit_only` |
| AC-OAUTH-06 | `test_OAUTH_external_browser_boundary_is_single_launch` |
| AC-OAUTH-07 | `test_OAUTH_loopback_configuration_requires_127_0_0_1_fixed_registered_redirect`, `test_OAUTH_bind_failure_prevents_browser_launch` |
| AC-OAUTH-08 | `test_OAUTH_missing_wrong_or_duplicate_state_blocks_exchange`, `test_OAUTH_wrong_path_malformed_or_provider_error_callback_blocks_exchange`, `test_OAUTH_timeout_closes_listener_without_exchange` |
| AC-OAUTH-09 | `test_OAUTH_exact_token_endpoint_form_contract` |
| AC-OAUTH-10 | `test_OAUTH_access_token_only_result_is_in_memory_and_redacted`, `test_OAUTH_refresh_token_result_requires_provider_value`, `test_OAUTH_malformed_success_fails_closed` |
| AC-OAUTH-11 | `test_OAUTH_offline_access_is_explicit_only` |
| AC-OAUTH-12 | `test_OAUTH_secret_sentinels_absent_from_stdout_stderr_repr_traceback`, `test_OAUTH_transport_and_provider_failures_are_conservative_and_redacted` |
| AC-OAUTH-13 | `test_OAUTH_no_persistence_or_environment_side_effect`, `test_OAUTH_existing_user_token_lookup_unchanged` |
| AC-OAUTH-14 | `test_OAUTH_correct_state_callback_exchanges_once`, `test_OAUTH_duplicate_late_callback_cannot_reexchange` |
| AC-OAUTH-15 | full `python -m unittest discover -s tests -v` regression |

## Negative requirements

Tests must also prove that this slice contains no:

- client-secret dependency;
- PKCE `plain` fallback;
- wildcard/non-loopback listener bind;
- dynamic redirect URI substitution;
- embedded browser or browser-cookie reuse;
- automatic retry/relaunch/re-exchange loop;
- OAuth 1.0a or unofficial fallback;
- access/refresh-token persistence;
- parent-shell environment mutation;
- access/refresh token printing or clipboard copy;
- change to existing `X_CONTEXT_USER_ACCESS_TOKEN` collection lookup.

## Secret-sentinel evidence

Automated tests use obvious fake values only and must assert that sentinel values representing these secret classes never appear in controlled output or retained evidence:

- authorization code;
- state;
- PKCE verifier;
- access token;
- refresh token;
- raw token response;
- full callback query.

No live X credential is permitted in unit/contract tests.

## Real-boundary qualification

After authoritative exact-head automated validation and independent/adversarial review, at most one intentional real browser/PKCE qualification may be run by explicit human decision. Retained evidence is limited to non-secret protocol facts and boolean token-presence facts.
