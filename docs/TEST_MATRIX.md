# Test Matrix

Related specification: `docs/specs/0001-mvp.md`  
Related work item: Issue #1

This matrix is the traceability bridge from requirement IDs to acceptance tests. Test names below are planned contracts until implementation begins.

| Requirement | Acceptance criteria | Planned automated evidence | Real-boundary evidence |
|---|---|---|---|
| FR-001 | AC-FR001-01..05 | `test_FR_001_extract_post_id`, `test_FR_001_query_fragment_ignored`, `test_FR_001_reject_foreign_host`, `test_FR_001_reject_missing_numeric_status`, `test_FR_001_invalid_input_no_network` | N/A |
| FR-002 | AC-FR002-01..06 | provider-contract tests for success, 401, 403, unavailable, 429, and no-unofficial-fallback | One official X API post lookup using non-secret evidence only |
| FR-003 | AC-FR003-01..05 | bookmark endpoint contract, pagination, no-default-persistence, missing-scope failure, no fallback | Authenticated bookmark read with payload redacted from evidence |
| FR-004 | AC-FR004-01..05 | likes endpoint contract, pagination, no-default-persistence, missing-scope failure, no fallback | Authenticated liked-post read with payload redacted from evidence |
| FR-005 | AC-FR005-01..04 | schema validation, optional/unknown semantics, secret redaction, provider-decoupling tests | Spot-check normalized output without publishing private payloads |
| FR-006 | AC-FR006-01..05 | CLI stdout/stderr separation, exit codes, stable error-category tests, credential non-disclosure | CLI smoke against official API after implementation |
| NFR-001 | official API only | provider boundary tests; source scan/review for unofficial acquisition paths | Verify real smoke destination is official API |
| NFR-002 | read-only boundary | auth-scope configuration tests; no mutation command registration | Verify granted/requested scopes documented without token material |
| NFR-003 | credential protection | secret-pattern regression tests; fixtures use fake credentials; error redaction tests | Review smoke logs/artifacts for credential absence |
| NFR-004 | fail closed | all provider failure paths assert no fallback provider invocation | Induce/observe a safe official-API failure where practical |
| NFR-005 | usage observability | request/item/pagination metadata tests without payload-body logging | Verify useful non-secret rate/request metadata |
| NFR-006 | private activity handling | tests assert no persistence side effect by default | Inspect local filesystem before/after bookmark/like smoke |

## Evidence rules

- Unit/contract tests must not require live credentials.
- Live X API tests are smoke/qualification evidence, not the only proof of behavior.
- Private bookmark/like payloads must not be committed to the repository, pasted into Issues/PRs, or retained in CI artifacts.
- Credentials and authorization headers must never appear in test output.
- A remediation that changes behavior invalidates affected evidence and requires the mapped tests to be rerun.

## Implementation ordering

The preferred first vertical slice after SPEC-0001 is accepted is:

1. FR-001 local URL parsing and error contract;
2. FR-005 minimal canonical schema needed by `read`;
3. FR-002 official post lookup;
4. FR-006 `read` CLI;
5. FR-003 bookmarks;
6. FR-004 likes.

This ordering does not authorize scope expansion; it only sequences the accepted MVP requirements.
