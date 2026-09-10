# Test Matrix

Related specification: `docs/specs/0001-mvp.md`  
Related work items: Issue #1 (spec baseline), Issue #5 (FR-005 minimal `read` schema)

This matrix is the traceability bridge from requirement IDs to acceptance tests. Test names below are planned contracts until implementation begins; implemented slices should name their concrete automated evidence.

| Requirement | Acceptance criteria | Planned automated evidence | Real-boundary evidence |
|---|---|---|---|
| FR-001 | AC-FR001-01..05 | `test_FR_001_extract_post_id`, `test_FR_001_query_fragment_ignored`, `test_FR_001_reject_foreign_host`, `test_FR_001_reject_missing_numeric_status`, `test_FR_001_invalid_input_no_network` | N/A |
| FR-002 | AC-FR002-01..06 | provider-contract tests for success, authentication/authorization failure, unavailable resource, rate limit, and no-unofficial-fallback | One official X API post lookup using non-secret evidence only |
| FR-003 | AC-FR003-01..10 | bookmark endpoint contract; authenticated-subject derivation/binding; reject subject mismatch before collection request; no arbitrary user-ID CLI; one-page bound; explicit continuation token; default 25; max-results 1..100; completeness semantics; no-default-persistence; missing-scope failure; no fallback | Authenticated bookmark read with payload redacted; verify subject matches authenticated user, one request/page, and explicit continuation behavior |
| FR-004 | AC-FR004-01..10 | likes endpoint contract; authenticated-subject derivation/binding; reject subject mismatch before collection request; no arbitrary user-ID CLI; one-page bound; explicit continuation token; default 25; max-results 1..100; completeness semantics; no-default-persistence; missing-scope failure; no fallback | Authenticated liked-post read with payload redacted; verify subject matches authenticated user, one request/page, and explicit continuation behavior |
| FR-005 | AC-FR005-01..07 | Current `read` slice: `test_FR_005_read_envelope_shape_and_schema_version`, `test_FR_005_retrieved_at_is_normalized_to_utc`, `test_FR_005_rejects_naive_retrieved_at`, `test_FR_005_read_subject_and_page_contract`, `test_FR_005_page_rejects_complete_with_next_token`, `test_FR_005_unrequested_optional_fields_are_not_fabricated`, `test_FR_005_provider_or_secret_passthrough_is_not_part_of_model`, `test_FR_005_rejects_non_ascii_or_non_numeric_post_id`; later collection slices must add authenticated `subject` provenance and optional/known-empty coverage for the canonical fields they introduce | Spot-check normalized output without publishing private payloads; confirm collection subject identity provenance when authenticated collection slices are implemented |
| FR-006 | AC-FR006-01..08 | CLI stdout/stderr separation, exit codes, stable error categories including `subject_mismatch` and `usage_blocked`, credential non-disclosure, page-token single-page behavior, local max-results bounds/no-network rejection, no target-user argument | CLI smoke against official API after implementation |
| NFR-001 | official API only | provider boundary tests; source scan/review for unofficial acquisition paths | Verify real smoke destination is official API |
| NFR-002 | read-only/same-subject boundary | auth-scope configuration tests; no mutation command registration; authenticated collection target must equal authenticated subject | Verify granted/requested scopes and subject binding without token material |
| NFR-003 | credential protection | secret-pattern regression tests; fixtures use fake credentials; error redaction tests | Review smoke logs/artifacts for credential absence |
| NFR-004 | fail closed | all provider failure paths assert no fallback provider invocation | Induce/observe a safe official-API failure where practical |
| NFR-005 | usage observability | request count, item count, requested page size, continuation state, safe rate/usage metadata tests; assert no payload-body logging and no hard-coded monetary-cost promise | Verify useful non-secret usage metadata and inspect logs for private-data absence |
| NFR-006 | private activity handling | tests assert no persistence side effect by default; continuation tokens excluded from diagnostics; subject provenance minimized | Inspect local filesystem/logs before/after bookmark/like smoke |

## FR-005 staging note

Issue #5 implements only the minimal canonical model needed by `read`. In this slice an item serializes the normalized numeric post ID as `id` and the post text as `text`. Optional expansion-backed fields that are not yet requested/resolved are omitted; omission means unrequested/unresolved/not represented, not known-empty. The later FR-002/provider slice must update this matrix before introducing any additional canonical item fields, and authenticated collection subject semantics remain deferred to their collection workstreams. Issue #5 must not be used as evidence that FR-005 is complete for bookmarks/likes.

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

Where provider responses cannot reliably distinguish a cause, tests must prefer a conservative stable category rather than fabricate certainty.

## Evidence rules

- Unit/contract tests must not require live credentials.
- Live X API tests are smoke/qualification evidence, not the only proof of behavior.
- Private bookmark/like payloads must not be committed to the repository, pasted into Issues/PRs, or retained in CI artifacts.
- Credentials and authorization headers must never appear in test output.
- Opaque continuation/page tokens must not appear in diagnostic logs or committed evidence.
- A remediation that changes behavior invalidates affected evidence and requires the mapped tests to be rerun.
- GitHub Actions is currently unavailable due to exhausted monthly Actions minutes; local/static evidence is required and queued/unstarted Actions runs are not CI success/failure evidence.

## Implementation ordering

The preferred first vertical slice after SPEC-0001 is accepted is:

1. FR-001 local URL parsing and error contract;
2. FR-005 minimal canonical schema needed by `read`;
3. FR-002 official post lookup;
4. FR-006 `read` CLI;
5. authenticated-subject resolution/binding contract for collections;
6. FR-003 bookmarks with same-subject and bounded one-page continuation;
7. FR-004 likes with same-subject and bounded one-page continuation.

This ordering does not authorize scope expansion; it only sequences the accepted MVP requirements.
