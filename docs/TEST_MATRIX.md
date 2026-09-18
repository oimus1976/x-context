# Test Matrix

Related specification: `docs/specs/0001-mvp.md`, `docs/specs/0001-fr006-read-clarification.md`, `docs/specs/0001-authenticated-subject-clarification.md`, `docs/specs/0002-oauth-acquisition-clarification.md`, `docs/specs/0003-credential-lifecycle.md`, `docs/specs/0004-oauth-bootstrap-cli.md`, and `docs/specs/0005-post-merge-closeout-command.md`
Related work items: Issue #1 (spec baseline), Issue #5 (FR-005 minimal `read` schema), Issue #7 (FR-002 official single-post lookup), Issue #9 (FR-006 `read` CLI), Issue #11 (authenticated-subject resolution/binding), Issue #23 (OAuth user-token acquisition), Issue #32 (credential lifecycle), Issue #36 (end-user OAuth bootstrap), Issue #38 (authoritative post-merge closeout)

This matrix is the traceability bridge from requirement IDs to acceptance tests. Test names below are planned contracts until implementation begins; implemented slices should name their concrete automated evidence.

| Requirement | Acceptance criteria | Planned automated evidence | Real-boundary evidence |
|---|---|---|---|
| FR-001 | AC-FR001-01..05 | `test_FR_001_extract_post_id`, `test_FR_001_query_fragment_ignored`, `test_FR_001_reject_foreign_host`, `test_FR_001_reject_missing_numeric_status`, `test_FR_001_invalid_input_no_network` | N/A |
| FR-002 | AC-FR002-01..11 | Implemented: `test_FR_002_uses_official_single_post_endpoint`, `test_FR_002_rejects_provider_incompatible_post_id_without_network`, `test_FR_002_requests_no_optional_fields_or_expansions`, `test_FR_002_success_normalizes_id_and_text`, `test_FR_002_rejects_provider_id_mismatch`, `test_FR_002_rejects_malformed_success_payload`, `test_FR_002_authentication_failure`, `test_FR_002_authorization_failure`, `test_FR_002_resource_unavailable`, `test_FR_002_rate_limited_safe_metadata`, `test_FR_002_usage_blocked`, `test_FR_002_provider_error`, `test_FR_002_missing_bearer_token_is_configuration_error_without_network`, `test_FR_002_no_fallback_or_secret_passthrough`, `test_FR_002_request_repr_does_not_expose_authorization`, `test_FR_002_transport_exception_does_not_chain_secret`, `test_FR_002_rejects_header_injection_token_without_network` | At most one intentional official X API single-Post lookup using app-only Bearer authorization and non-secret evidence only; do not retain the raw provider payload |
| Authenticated subject boundary | AC-AUTH-SUBJ-01..12 | Implemented: `test_AUTH_SUBJ_uses_official_authenticated_user_endpoint`, `test_AUTH_SUBJ_requests_no_optional_user_fields_or_expansions`, `test_AUTH_SUBJ_rejects_missing_or_unsafe_user_token_without_transport`, `test_AUTH_SUBJ_normalizes_minimum_subject`, `test_AUTH_SUBJ_username_is_optional`, `test_AUTH_SUBJ_empty_errors_does_not_make_success_contradictory`, `test_AUTH_SUBJ_rejects_malformed_subject_payload`, `test_AUTH_SUBJ_maps_authentication_and_authorization_failures`, `test_AUTH_SUBJ_provider_failure_is_conservative`, `test_AUTH_SUBJ_does_not_leak_token_raw_body_headers_or_transport_exception`, `test_AUTH_SUBJ_same_subject_binding_succeeds_locally`, `test_AUTH_SUBJ_mismatch_fails_closed_locally`, `test_AUTH_SUBJ_invalid_target_is_invalid_input`, `test_AUTH_SUBJ_app_only_token_is_not_a_user_token_fallback`, `test_AUTH_SUBJ_reports_request_attempt_and_safe_rate_metadata`, `test_AUTH_SUBJ_maps_identified_rate_and_usage_failures` | Optional intentional `/2/users/me` smoke using a real user-context token; retain only non-secret subject/protocol facts, never the credential or raw provider body |
| FR-003 | Issue #19 AC-FR003-01..16; normative `0001-fr003-bookmarks-clarification.md` | `test_FR_003_official_endpoint_subject_binding_and_canonical`, `test_FR_003_user_credential_only`, `test_FR_003_default_and_bounds`, `test_FR_003_invalid_input_before_transport`, `test_FR_003_binding_failure_stops_collection`, `test_FR_003_one_page_continuation_and_completeness`, `test_FR_003_malformed_success_fails_closed`, `test_FR_003_conservative_errors_and_accounting`, `test_FR_003_private_values_excluded_from_diagnostics_and_repr`, `test_FR_003_transport_failure_redacted`, `test_FR_003_no_default_persistence`, `test_FR_003_no_target_or_all_cli`, `test_FR_003_rate_metadata_for_both_attempts`, `test_FR_003_redirects_not_followed`; full `python -m unittest discover -s tests -v` | Live credentials prohibited for this task; real-boundary qualification remains unverified |
| FR-004 | Issue #21 AC-FR004-01..16; normative `0001-fr004-likes-clarification.md` | `test_FR_004_official_endpoint_subject_binding_and_canonical`, `test_FR_004_user_credential_only`, `test_FR_004_default_and_bounds`, `test_FR_004_invalid_input_before_transport`, `test_FR_004_binding_failure_stops_collection`, `test_FR_004_one_page_continuation_and_completeness`, `test_FR_004_malformed_success_fails_closed`, `test_FR_004_conservative_errors_and_accounting`, `test_FR_004_private_values_excluded_from_diagnostics_and_repr`, `test_FR_004_transport_failure_redacted`, `test_FR_004_no_default_persistence`, `test_FR_004_no_target_or_all_cli`, `test_FR_004_rate_metadata_for_both_attempts`, `test_FR_004_redirects_not_followed`, `test_FR_004_overfull_page_fails_closed`, `test_FR_004_subject_failure_blocks_likes`, `test_FR_004_canonical_requires_subject`, `test_FR_004_default_transport_one_attempt_per_endpoint`; full `python -m unittest discover -s tests -v` | Live credentials prohibited for this task; real-boundary qualification remains unverified |
| FR-005 | AC-FR005-01..07 | Current `read` slice: `test_FR_005_read_envelope_shape_and_schema_version`, `test_FR_005_retrieved_at_is_normalized_to_utc`, `test_FR_005_rejects_naive_retrieved_at`, `test_FR_005_read_subject_and_page_contract`, `test_FR_005_page_rejects_complete_with_next_token`, `test_FR_005_unrequested_optional_fields_are_not_fabricated`, `test_FR_005_provider_or_secret_passthrough_is_not_part_of_model`, `test_FR_005_rejects_non_ascii_or_non_numeric_post_id`; later collection slices must add authenticated `subject` provenance and optional/known-empty coverage for the canonical fields they introduce | Spot-check normalized output without publishing private payloads; confirm collection subject identity provenance when authenticated collection slices are implemented |
| FR-006 `read` slice | AC-FR006-R01..R13 | Implemented: `test_FR_006_read_success_writes_canonical_json_only_to_stdout`, `test_FR_006_read_success_writes_usage_diagnostics_to_stderr`, `test_FR_006_read_rejects_direct_post_id`, `test_FR_006_read_invalid_url_is_local_exit_2_without_network`, `test_FR_006_read_provider_incompatible_id_is_local_exit_2_without_transport`, `test_FR_006_read_missing_credential_is_configuration_exit_2_without_transport`, `test_FR_006_read_unsafe_credential_is_configuration_exit_2_without_transport`, `test_FR_006_read_provider_categories_exit_3`, `test_FR_006_read_success_exposes_only_safe_rate_metadata`, `test_FR_006_read_missing_rate_metadata_is_not_fabricated`, `test_FR_006_read_has_no_token_cli_argument`, `test_FR_006_read_does_not_leak_token_raw_body_or_arbitrary_headers`, `test_FR_006_read_transport_exception_is_redacted_and_counted` | Optional intentional CLI smoke against official single-Post API; canonical payload may be inspected locally but evidence retains only non-secret/non-raw diagnostic facts |
| FR-006 collections | AC-FR006-01..08 collection portions | FR-003/FR-004 tests above cover page-token single-page behavior, max-results 1..100/no-network rejection, canonical stdout, safe stderr, and no target-user argument | Live qualification unverified; no live credentials or reads in this task |
| OAuth acquisition | Issue #23 AC-OAUTH-01..15; normative `0002-oauth-acquisition-clarification.md` | `test_OAUTH_uses_official_authorize_endpoint_and_read_scopes`, `test_OAUTH_public_client_uses_client_id_without_secret`, `test_OAUTH_generates_fresh_state_and_verifier_per_attempt`, `test_OAUTH_derives_s256_challenge_without_plain_fallback`, `test_OAUTH_loopback_configuration_requires_127_0_0_1_fixed_registered_redirect`, `test_OAUTH_bind_failure_prevents_browser_launch`, `test_OAUTH_browser_launch_failure_closes_listener_without_wait_or_exchange`, `test_OAUTH_external_browser_boundary_is_single_launch`, `test_OAUTH_missing_wrong_or_duplicate_state_blocks_exchange`, `test_OAUTH_wrong_path_malformed_or_provider_error_callback_blocks_exchange`, `test_OAUTH_unrelated_request_does_not_terminate_loopback_wait`, `test_OAUTH_timeout_closes_listener_without_exchange`, `test_OAUTH_exact_token_endpoint_form_contract`, `test_OAUTH_correct_state_callback_exchanges_once`, `test_OAUTH_duplicate_late_callback_cannot_reexchange`, `test_OAUTH_access_token_only_result_is_in_memory_and_redacted`, `test_OAUTH_refresh_token_result_requires_provider_value`, `test_OAUTH_malformed_success_fails_closed`, `test_OAUTH_offline_access_is_explicit_only`, `test_OAUTH_secret_sentinels_absent_from_stdout_stderr_repr_traceback`, `test_OAUTH_transport_and_provider_failures_are_conservative_and_redacted`, `test_OAUTH_no_persistence_or_environment_side_effect`, `test_OAUTH_unrequested_refresh_token_fails_closed`, `test_OAUTH_unsafe_client_id_is_configuration_error`; existing FR-003/FR-004 credential-source regressions plus full `python -m unittest discover -s tests -v` | Real browser/PKCE qualification remains human-gated; retain only non-secret protocol facts and token-presence booleans |
| Credential lifecycle | Issue #32 AC-CRED-01..19; normative `0003-credential-lifecycle.md`; storage decision ADR-0005 | `test_CRED_explicit_persistence_round_trip_and_redaction`, `test_CRED_real_windows_dpapi_round_trip_and_plaintext_absent`, `test_CRED_oauth_acquisition_remains_nonpersistent`, `test_CRED_env_override_wins_and_invalid_override_fails_closed`, `test_CRED_no_app_bearer_fallback_or_env_auto_import`, `test_CRED_expiry_and_refresh_window`, `test_CRED_refresh_request_public_client_contract_and_single_attempt`, `test_CRED_malformed_or_scope_expanding_refresh_preserves_state`, `test_CRED_successful_refresh_commits_before_use`, `test_CRED_refresh_token_replacement_and_omission_rule`, `test_CRED_failed_refresh_preserves_state_and_blocks_collection`, `test_CRED_collection_subject_binding_still_runs`, `test_CRED_local_delete_is_idempotent_and_local_only`, `test_CRED_provider_revoke_contract_and_delete_order`, `test_CRED_corrupt_or_unsupported_state_fails_closed`, `test_CRED_secret_sentinels_absent_from_repr_errors_and_diagnostics`, `test_CRED_scope_authority_remains_read_only`, `test_CRED_storage_replace_failure_keeps_prior_commit`, `test_CRED_concurrency_claim_is_single_writer`, `test_CRED_invalid_max_results_precedes_due_refresh`, `test_CRED_invalid_page_token_precedes_due_refresh`; full `python -m unittest discover -s tests -v` | Windows exact-head validation must execute the real-DPAPI synthetic test; any live X refresh/revoke qualification is separately human-gated; retain endpoint/success/token-presence/scope facts only, never token values or raw provider payloads |
| OAuth bootstrap CLI | Issue #36 AC-BOOT-01..12; normative `0004-oauth-bootstrap-cli.md` | `test_AUTH_login_success_composes_refresh_capable_acquisition_and_persistence`, `test_AUTH_login_missing_or_invalid_configuration_has_zero_oauth_and_store_effects`, `test_AUTH_login_requires_refresh_token_before_persistence`, `test_AUTH_login_requires_expiry_before_persistence`, `test_AUTH_login_acquisition_failure_preserves_existing_credential`, `test_AUTH_login_persistence_failure_is_local_and_does_not_leak_secrets`, `test_AUTH_login_never_imports_environment_access_token`, `test_AUTH_login_secret_values_are_absent_from_success_output`, `test_AUTH_login_unsupported_default_store_fails_before_oauth`, `test_AUTH_login_persisted_result_is_consumed_by_existing_bookmarks_path`, `test_AUTH_login_rejects_credential_cli_argument_without_echoing_secret`, `test_AUTH_login_rejects_extra_secret_argument_without_echoing_it`; existing OAuth/lifecycle scope and DPAPI tests plus full `python -m unittest discover -s tests -v` | Windows exact-head validation must include the bootstrap tests and real-DPAPI lifecycle test; any real browser/provider login remains separately human-gated; retain only non-secret effect facts, never token/callback/provider payload material |
| Post-merge closeout command | Issue #38 AC-CLOSEOUT-01..14; normative `0005-post-merge-closeout-command.md` | `test_cli_requires_pr_and_repository_but_accepts_no_sha_inputs`, `test_merged_happy_path_derives_shas_and_fast_forwards_main`, `test_repository_identity_mismatch_fails_before_github_pr_read`, `test_unmerged_wrong_base_and_cross_repository_fail_before_sync`, `test_malformed_or_placeholder_like_merge_sha_fails_before_sync`, `test_open_closing_issue_blocks_before_sync`, `test_merge_push_ci_missing_pending_failed_or_wrong_sha_blocks`, `test_duplicate_exact_workflow_evidence_is_ambiguous_and_blocks`, `test_remote_without_authoritative_merge_commit_is_rejected`, `test_dirty_and_in_progress_canonical_worktree_block_before_fast_forward`, `test_diverged_canonical_history_fails_without_reset_or_rebase`, `test_existing_local_verifier_failure_propagates`, `test_clean_target_worktree_is_reported_and_retained`, `test_dirty_target_worktree_blocks_but_is_never_removed`, `test_native_exit_code_is_authoritative_even_with_stderr_style_output`, `test_github_pr_reader_requests_and_parses_authoritative_merge_fields`, `test_workflow_reader_filters_exact_merge_commit_push_runs`, `test_native_diagnostics_redact_https_remote_userinfo`, `test_success_revalidates_closing_issues_after_local_sync`, `test_success_revalidates_merge_push_ci_after_local_sync`, `test_source_does_not_import_or_invoke_destructive_cleanup`; full `python -m unittest discover -s tests -v` | Windows exact-head validation must run the complete suite; first real operator qualification should use the tracked command after a merged same-repository PR with successful push CI, retaining only non-secret merge/check/worktree facts; destructive cleanup remains separate |
| NFR-001 | official API only | provider boundary tests; authenticated-subject endpoint contract; OAuth, lifecycle, and bootstrap tests pin or compose only the official authorize/token/revoke endpoints and prohibit unofficial/browser-cookie/OAuth1 fallback | Verify real smoke destination is official API |
| NFR-002 | read-only/same-subject boundary | authenticated-subject resolution and local binding tests; collection target must equal authenticated subject; OAuth/lifecycle/bootstrap scope tests allow only the four MVP read scopes plus explicit `offline.access`, with no write scope | Verify granted/requested scopes and subject binding without token material |
| NFR-003 | credential protection | secret-pattern regression tests; fixtures use fake credentials; OAuth tests cover access/refresh token, authorization code, state, PKCE verifier, request/response, authorization-URL repr, and traceback redaction; lifecycle tests add protected persistence, refresh/revoke, DPAPI envelope, storage-error redaction, and a Windows-only real-DPAPI round trip with synthetic token sentinels; bootstrap tests reject credential-shaped CLI arguments without echo and cover output/storage-failure redaction | Review Windows exact-head evidence for execution of the real-DPAPI test; review smoke logs/artifacts for credential and OAuth ceremony-secret absence |
| NFR-004 | fail closed | all provider failure paths assert no fallback provider invocation; subject mismatch fails before collection transport; OAuth rejects unsafe config, invalid/wrong/duplicate callback state, unexpected refresh authority, malformed token success, unrelated callback paths, transport/provider failures, and duplicate exchange; lifecycle rejects corrupt state, unsafe env override, refresh failure, scope drift, partial replacement, and collection-local invalid input before refresh; bootstrap rejects missing/invalid config, missing refresh/expiry metadata, unsupported store, acquisition failure, and persistence failure without importing env credentials or downgrading persistence | Induce/observe a safe official-API failure where practical |
| NFR-005 | usage observability | FR-006 `read`: operation, provider-request count, returned-item count, continuation=false, safe rate/usage metadata when present, zero-request diagnostics for local rejection; authenticated-subject resolution exposes its own provider-request count and safe rate metadata for later collection aggregation; collection slices later add requested page size and continuation-token state; lifecycle diagnostics expose only safe source/refresh/revoke facts; bootstrap emits only bounded non-secret status/error facts; assert no payload-body logging and no hard-coded monetary-cost promise | Verify useful non-secret usage metadata and inspect logs for private-data/credential absence |
| NFR-006 | private activity handling | tests assert no collection persistence side effect by default; continuation tokens excluded from diagnostics; subject provenance minimized; lifecycle/bootstrap persistence stores only the explicitly committed protected credential envelope | Inspect local filesystem/logs before/after bookmark/like smoke |

## FR-002 provider-boundary staging note

Issue #7 keeps the first official-provider slice intentionally narrow. It uses the documented single-Post endpoint with app-only Bearer authorization and requests no optional `post.fields` or `expansions`. Provider `data.id` and `data.text` are the only Post fields normalized into the existing `CanonicalPost`; no author, created-at, canonical URL, references, media, or link shape is introduced by this workstream.

FR-001 remains a URL parsing/extraction requirement and does not acquire a provider-specific length rule retroactively. Before issuing an FR-002 network request, the provider boundary must reject a Post ID that does not match the official endpoint's current `^[0-9]{1,19}$` path contract as `invalid_input`; that rejection must make no network request.

Current provider rate limits, prices, monthly caps, and Owned Read qualification are external facts rather than product constants. In particular, official X documentation currently contains conflicting monthly pay-per-use Post-read cap figures, so no test or implementation may infer product behavior from either figure. Tests may use synthetic safe rate headers/problem types but must not hard-code current numeric limits as correctness criteria.

## FR-005 staging note

Issue #5 implements only the minimal canonical model needed by `read`. In this slice an item serializes the normalized numeric post ID as `id` and the post text as `text`. Optional expansion-backed fields that are not yet requested/resolved are omitted; omission means unrequested/unresolved/not represented, not known-empty. The later FR-002/provider slice must update this matrix before introducing any additional canonical item fields, and authenticated collection subject semantics remain deferred to their collection workstreams. Issue #5 must not be used as evidence that FR-005 is complete for bookmarks/likes.

## FR-006 `read` staging note

Issue #9 composes the completed FR-001, FR-002, and FR-005 boundaries. The CLI accepts only a supported status URL and obtains the app-only token from `X_CONTEXT_BEARER_TOKEN`; direct Post-ID and token CLI arguments are intentionally absent.

Successful stdout is canonical JSON only. NFR-005 diagnostics go to stderr and remain outside the canonical schema. Exit codes are intentionally grouped: `0` success, `2` local/parser/input/configuration failure, and `3` provider/read failure; the existing stable error category supplies the finer cause.

The existing `lookup_post(...) -> CanonicalEnvelope` behavior remains a compatibility contract. Any success-diagnostic provider wrapper/helper introduced for FR-006 must not force existing callers to consume provider metadata and must expose only allow-listed non-secret rate metadata.

For `read`, requested page size is not applicable and must not be fabricated. Invalid URL, provider-incompatible extracted ID, and local credential rejection must remain zero-request paths. No price, monthly cap, current rate-limit number, or Owned Read classification becomes a behavioral constant.

## Authenticated-subject staging note

Issue #11 introduces the common identity boundary required by both FR-003 and FR-004 without retrieving either private collection. The authenticated subject is resolved only through the official `GET /2/users/me` endpoint using an explicit user-context access token. The existing app-only `X_CONTEXT_BEARER_TOKEN` must not be reinterpreted or used as fallback user authority; future collection CLI integration uses a distinct `X_CONTEXT_USER_ACCESS_TOKEN` source.

The minimum subject contract is required ASCII-decimal `id` plus optional safe `username`. No other provider user fields become domain/canonical state. Same-subject binding is a local guard: exact target ID equality succeeds, invalid target input is `invalid_input`, and a valid different ID is `subject_mismatch`; neither path makes a collection request.

`/users/me` counts as one provider request when attempted. Safe rate metadata may be carried in a non-canonical result wrapper for later NFR-005 aggregation. Issue #11 does not decide per-command subject-resolution caching/reuse policy, implement OAuth browser/PKCE ceremony, persist refresh tokens, retrieve bookmarks/likes, or change the FR-005 collection envelope.

## OAuth acquisition AC-to-test mapping

| Acceptance criterion | Automated evidence |
|---|---|
| AC-OAUTH-01 | `test_OAUTH_uses_official_authorize_endpoint_and_read_scopes` |
| AC-OAUTH-02 | `test_OAUTH_public_client_uses_client_id_without_secret`, `test_OAUTH_unsafe_client_id_is_configuration_error` |
| AC-OAUTH-03 | `test_OAUTH_generates_fresh_state_and_verifier_per_attempt` |
| AC-OAUTH-04 | `test_OAUTH_derives_s256_challenge_without_plain_fallback` |
| AC-OAUTH-05 | `test_OAUTH_uses_official_authorize_endpoint_and_read_scopes`, `test_OAUTH_loopback_configuration_requires_127_0_0_1_fixed_registered_redirect`, `test_OAUTH_offline_access_is_explicit_only` |
| AC-OAUTH-06 | `test_OAUTH_external_browser_boundary_is_single_launch`, `test_OAUTH_browser_launch_failure_closes_listener_without_wait_or_exchange` |
| AC-OAUTH-07 | `test_OAUTH_loopback_configuration_requires_127_0_0_1_fixed_registered_redirect`, `test_OAUTH_bind_failure_prevents_browser_launch`, `test_OAUTH_unrelated_request_does_not_terminate_loopback_wait` |
| AC-OAUTH-08 | `test_OAUTH_missing_wrong_or_duplicate_state_blocks_exchange`, `test_OAUTH_wrong_path_malformed_or_provider_error_callback_blocks_exchange`, `test_OAUTH_timeout_closes_listener_without_exchange`, `test_OAUTH_unrelated_request_does_not_terminate_loopback_wait` |
| AC-OAUTH-09 | `test_OAUTH_exact_token_endpoint_form_contract` |
| AC-OAUTH-10 | `test_OAUTH_access_token_only_result_is_in_memory_and_redacted`, `test_OAUTH_refresh_token_result_requires_provider_value`, `test_OAUTH_malformed_success_fails_closed`, `test_OAUTH_unrequested_refresh_token_fails_closed` |
| AC-OAUTH-11 | `test_OAUTH_offline_access_is_explicit_only`, `test_OAUTH_unrequested_refresh_token_fails_closed` |
| AC-OAUTH-12 | `test_OAUTH_secret_sentinels_absent_from_stdout_stderr_repr_traceback`, `test_OAUTH_transport_and_provider_failures_are_conservative_and_redacted` |
| AC-OAUTH-13 | `test_OAUTH_no_persistence_or_environment_side_effect`; existing FR-003/FR-004 regressions preserve the unchanged `X_CONTEXT_USER_ACCESS_TOKEN` collection boundary |
| AC-OAUTH-14 | `test_OAUTH_correct_state_callback_exchanges_once`, `test_OAUTH_duplicate_late_callback_cannot_reexchange` |
| AC-OAUTH-15 | full `python -m unittest discover -s tests -v` regression |

## OAuth acquisition staging note

Issue #23 adds only the native/public-client Authorization Code + PKCE acquisition ceremony. It does not replace the existing `X_CONTEXT_USER_ACCESS_TOKEN` source used by bookmarks/likes and does not persist or automatically refresh credentials.

Each attempt uses fresh independent state and PKCE verifier material, S256 only, the external system browser, and a fixed registered `http://127.0.0.1:<port>/<path>` callback. Listener bind must succeed before browser launch. Unrelated loopback requests do not terminate the listener; only the configured callback path is eligible, within one bounded overall timeout. A validated callback permits at most one official token exchange.

The default requested scope set is exactly `tweet.read users.read bookmark.read like.read`. `offline.access` is added only by explicit refresh-capable acquisition. No client secret, write scope, alternate OAuth flow, scraping/browser-cookie fallback, retry loop, persistence, clipboard copy, or parent-environment mutation is introduced.

Real browser/PKCE qualification is separate human-gated evidence. The acquisition result is deliberately in-memory only; secure Windows persistence, refresh lifecycle, revoke/logout, and integration with collection credential lookup belong to a later lifecycle workstream.

## Credential lifecycle AC-to-test mapping

| Acceptance criterion | Automated evidence |
|---|---|
| AC-CRED-01 | `test_CRED_explicit_persistence_round_trip_and_redaction`, `test_CRED_real_windows_dpapi_round_trip_and_plaintext_absent` (Windows-only real boundary) |
| AC-CRED-02 | `test_CRED_oauth_acquisition_remains_nonpersistent` |
| AC-CRED-03 | `test_CRED_env_override_wins_and_invalid_override_fails_closed` |
| AC-CRED-04 | `test_CRED_no_app_bearer_fallback_or_env_auto_import` |
| AC-CRED-05 | `test_CRED_expiry_and_refresh_window` |
| AC-CRED-06 | `test_CRED_refresh_request_public_client_contract_and_single_attempt` |
| AC-CRED-07 | `test_CRED_malformed_or_scope_expanding_refresh_preserves_state` |
| AC-CRED-08 | `test_CRED_successful_refresh_commits_before_use` |
| AC-CRED-09 | `test_CRED_refresh_token_replacement_and_omission_rule` |
| AC-CRED-10 | `test_CRED_failed_refresh_preserves_state_and_blocks_collection` |
| AC-CRED-11 | `test_CRED_collection_subject_binding_still_runs` plus existing FR-003/FR-004 binding regressions |
| AC-CRED-12 | `test_CRED_local_delete_is_idempotent_and_local_only` |
| AC-CRED-13 | `test_CRED_provider_revoke_contract_and_delete_order` |
| AC-CRED-14 | `test_CRED_corrupt_or_unsupported_state_fails_closed` |
| AC-CRED-15 | `test_CRED_secret_sentinels_absent_from_repr_errors_and_diagnostics` |
| AC-CRED-16 | `test_CRED_scope_authority_remains_read_only` |
| AC-CRED-17 | `test_CRED_storage_replace_failure_keeps_prior_commit`, `test_CRED_concurrency_claim_is_single_writer` |
| AC-CRED-18 | full `python -m unittest discover -s tests -v` regression |
| AC-CRED-19 | `test_CRED_invalid_max_results_precedes_due_refresh`, `test_CRED_invalid_page_token_precedes_due_refresh` |

## Credential lifecycle staging note

Issue #32 replaces mandatory environment-only user credential sourcing with a lifecycle-managed provider while retaining `X_CONTEXT_USER_ACCESS_TOKEN` as an explicit per-operation compatibility/recovery override. The env override wins when present and is never automatically persisted or refreshed. `X_CONTEXT_BEARER_TOKEN` remains app-only and cannot become user authority.

ADR-0005 selects DPAPI CurrentUser protected local-file storage. The entire versioned credential envelope is the atomic storage unit. Known expiry uses a 300-second refresh-before-use window; unknown expiry is not fabricated. A resolution performs at most one refresh, and a failed attempted refresh blocks the current collection operation even if the old access token has not yet reached its exact expiry.

Successful refresh replacement is conservative about undocumented rotation semantics: a returned refresh token replaces the prior token; omission fails closed, leaves the previous committed credential unchanged, and does not expose the returned access token for use. Collection-local invalid input is rejected before credential resolution so it cannot trigger refresh or any X API request. Provider revoke is distinct from local delete and is a single-token operation; it prefers the refresh token when present and deletes local state only after provider success, without claiming token-family invalidation or complete provider logout.

Most automated lifecycle evidence uses fake credentials/storage/transport. `test_CRED_real_windows_dpapi_round_trip_and_plaintext_absent` is the explicit Windows-only concrete DPAPI boundary test; it uses synthetic credentials and a temporary path and must not retain generated protected blobs. Any real X refresh or revoke affecting an account remains human-gated.

## OAuth bootstrap AC-to-test mapping

| Acceptance criterion | Automated evidence |
|---|---|
| AC-BOOT-01 | `test_AUTH_login_missing_or_invalid_configuration_has_zero_oauth_and_store_effects` |
| AC-BOOT-02 | `test_AUTH_login_success_composes_refresh_capable_acquisition_and_persistence` |
| AC-BOOT-03 | `test_AUTH_login_success_composes_refresh_capable_acquisition_and_persistence` plus existing `test_OAUTH_uses_official_authorize_endpoint_and_read_scopes` and `test_OAUTH_offline_access_is_explicit_only` |
| AC-BOOT-04 | `test_AUTH_login_requires_refresh_token_before_persistence` |
| AC-BOOT-05 | `test_AUTH_login_requires_expiry_before_persistence` |
| AC-BOOT-06 | `test_AUTH_login_acquisition_failure_preserves_existing_credential`, `test_AUTH_login_requires_refresh_token_before_persistence`, `test_AUTH_login_requires_expiry_before_persistence` |
| AC-BOOT-07 | `test_AUTH_login_success_composes_refresh_capable_acquisition_and_persistence` plus lifecycle atomic-replacement/DPAPI tests |
| AC-BOOT-08 | `test_AUTH_login_never_imports_environment_access_token` |
| AC-BOOT-09 | `test_AUTH_login_secret_values_are_absent_from_success_output`, `test_AUTH_login_persistence_failure_is_local_and_does_not_leak_secrets`, `test_AUTH_login_rejects_credential_cli_argument_without_echoing_secret`, `test_AUTH_login_rejects_extra_secret_argument_without_echoing_it` |
| AC-BOOT-10 | `test_AUTH_login_unsupported_default_store_fails_before_oauth` |
| AC-BOOT-11 | `test_AUTH_login_persisted_result_is_consumed_by_existing_bookmarks_path` |
| AC-BOOT-12 | parser surface and full regression suite; no delete/revoke/status/P1 command or scope is introduced |

## OAuth bootstrap staging note

Issue #36 is a composition slice over the already-accepted OAuth acquisition and lifecycle boundaries. `auth login` requests a refresh-capable credential with exactly the four P0 read scopes plus `offline.access`, requires fixed registered loopback configuration, resolves a supported secure lifecycle store before browser launch, and persists only after a normalized result includes a refresh token and positive expiry duration. Missing expiry is not repaired by assuming the provider's currently documented default lifetime.

The command accepts no credential, code, state, verifier, client-secret, or scope argument. `X_CONTEXT_USER_ACCESS_TOKEN` remains unmanaged and is never imported. The bootstrap performs no X content read and adds no write/DM/follows/list/block/mute authority. Local credential delete/status, provider revoke, packaging, and P1 data surfaces remain out of scope.

Synthetic tests provide the contract evidence. Windows exact-head validation must also run the real-DPAPI lifecycle boundary test because this CLI now composes into the default DPAPI store. A real browser/provider login is optional qualification evidence and remains an explicit human decision; if performed, retained evidence must contain only non-secret protocol/effect facts.

## Post-merge closeout command AC-to-test mapping

| Acceptance criterion | Automated evidence |
|---|---|
| AC-CLOSEOUT-01 | `test_cli_requires_pr_and_repository_but_accepts_no_sha_inputs`, `test_merged_happy_path_derives_shas_and_fast_forwards_main` |
| AC-CLOSEOUT-02 | `test_repository_identity_mismatch_fails_before_github_pr_read` |
| AC-CLOSEOUT-03 | `test_unmerged_wrong_base_and_cross_repository_fail_before_sync`, `test_malformed_or_placeholder_like_merge_sha_fails_before_sync`, `test_github_pr_reader_requests_and_parses_authoritative_merge_fields` |
| AC-CLOSEOUT-04 | `test_malformed_or_placeholder_like_merge_sha_fails_before_sync` |
| AC-CLOSEOUT-05 | `test_remote_without_authoritative_merge_commit_is_rejected` |
| AC-CLOSEOUT-06 | `test_remote_without_authoritative_merge_commit_is_rejected` |
| AC-CLOSEOUT-07 | `test_dirty_and_in_progress_canonical_worktree_block_before_fast_forward`, `test_diverged_canonical_history_fails_without_reset_or_rebase` |
| AC-CLOSEOUT-08 | `test_native_exit_code_is_authoritative_even_with_stderr_style_output`, `test_native_diagnostics_redact_https_remote_userinfo` |
| AC-CLOSEOUT-09 | `test_existing_local_verifier_failure_propagates` |
| AC-CLOSEOUT-10 | `test_clean_target_worktree_is_reported_and_retained`, `test_dirty_target_worktree_blocks_but_is_never_removed` |
| AC-CLOSEOUT-11 | `test_open_closing_issue_blocks_before_sync`, `test_success_revalidates_closing_issues_after_local_sync` |
| AC-CLOSEOUT-12 | `test_merge_push_ci_missing_pending_failed_or_wrong_sha_blocks`, `test_duplicate_exact_workflow_evidence_is_ambiguous_and_blocks`, `test_merged_happy_path_derives_shas_and_fast_forwards_main`, `test_workflow_reader_filters_exact_merge_commit_push_runs`, `test_success_revalidates_merge_push_ci_after_local_sync` |
| AC-CLOSEOUT-13 | `test_source_does_not_import_or_invoke_destructive_cleanup`, `test_dirty_target_worktree_blocks_but_is_never_removed` |
| AC-CLOSEOUT-14 | `test_merged_happy_path_derives_shas_and_fast_forwards_main`, `test_native_diagnostics_redact_https_remote_userinfo` |

SPEC-0005 is a maintenance authority boundary rather than X provider behavior. The command derives PR head and merge SHA from authenticated GitHub evidence, requires successful push CI on the exact merge SHA, fast-forwards only the canonical branch, reuses the existing local verifier, and reports target worktrees without deleting them. A separate human-authorized cleanup workflow remains required for branch/worktree/ref deletion.

## Error-model cross-cutting tests

The stable categories in SPEC-0001 must be exercised without requiring callers to parse provider prose:

- `invalid_input`
- `authentication_failed`
- `authorization_failed`
- `subject_mismatch`
- `resource_unavailable`
- `rate_limited`
- `usage_blocked`
- `provider_error`
- `configuration_error`

Lifecycle-local categories such as `credential_missing`, `credential_expired`, and `credential_storage_error` may be introduced by SPEC-0003, but CLI exit-code grouping must remain stable and callers must not parse OS/provider prose.

Where provider responses cannot reliably distinguish a cause, tests must prefer a conservative stable category rather than fabricate certainty. For FR-002, an ambiguous `429` that cannot safely be identified as short-window rate limiting or a usage/credit gate must therefore fall back to `provider_error` rather than guessing.

## Evidence rules

- Unit/contract tests must not require live credentials.
- Live X API tests are smoke/qualification evidence, not the only proof of behavior.
- Private bookmark/like payloads must not be committed to the repository, pasted into Issues/PRs, or retained in CI artifacts.
- Credentials and authorization headers must never appear in test output.
- OAuth authorization codes, state values, PKCE verifiers, access/refresh tokens, raw token responses, authorization URLs carrying ceremony state, and full callback query strings must not appear in retained diagnostics/evidence.
- Opaque continuation/page tokens must not appear in diagnostic logs or committed evidence.
- DPAPI plaintext envelopes, generated protected credential blobs, refresh/revoke request bodies, and raw lifecycle provider responses must not be committed as evidence.
- The Windows-only DPAPI integration test may create a synthetic protected blob only under a temporary path for the duration of the test and must delete it before completion.
- Real-provider login/refresh/revoke qualification remains human-gated and must not be substituted for synthetic contract evidence.
- A remediation that changes behavior invalidates affected evidence and requires the mapped tests to be rerun.
- Public hosted CI is available for this repository; exact-head local/static validation remains required, and hosted `project-ci` / `policy-check` success must be confirmed for the PR head before the Ready human gate.

## Implementation ordering

The preferred first vertical slice after SPEC-0001 is accepted is:

1. FR-001 local URL parsing and error contract;
2. FR-005 minimal canonical schema needed by `read`;
3. FR-002 official post lookup;
4. FR-006 `read` CLI;
5. authenticated-subject resolution/binding contract for collections;
6. FR-003 bookmarks with same-subject and bounded one-page continuation;
7. FR-004 likes with same-subject and bounded one-page continuation;
8. OAuth 2.0 Authorization Code + PKCE user-token acquisition;
9. secure credential persistence/refresh/revoke lifecycle and collection integration as a separate workstream;
10. end-user OAuth bootstrap composition before adding P1 data surfaces.

This ordering does not authorize scope expansion; it only sequences the accepted MVP requirements.
