# Review-0005-F1 — Closing-Issue state compatibility review

- **Date:** 2026-09-24
- **Workstream:** Issue #40 / Draft PR #41
- **Base main:** `62b61978676d30158db740ff61aba917114bc738`
- **Clarification:** `docs/specs/0005-closing-issue-state-clarification.md`

## Trigger

The first real post-merge dogfood of PR #39 failed with:

```text
FAIL: authenticated GitHub PR evidence is incomplete
POST-MERGE CLOSEOUT: FAIL
```

The command failed before canonical synchronization, so the failure preserved the intended fail-closed boundary. The defect was compatibility between the synthetic fixture and real GitHub CLI output.

## Root cause

The merged test fixture represented `closingIssuesReferences` as:

```json
{"number": 38, "state": "CLOSED"}
```

Real GitHub CLI exports each closing-Issue reference with identity fields such as `number`, `url`, and nested `repository`, but no nested Issue `state`.

The implementation therefore attempted `item["state"]` on data where that field does not exist.

## Remediation review

The corrected design separates two authorities:

1. `gh pr view ... --json closingIssuesReferences` determines which Issues the PR reports as closing.
2. `gh issue view <number> -R owner/repo --json number,state` determines the current state of each referenced Issue.

The implementation validates:
- positive Issue number;
- non-empty, single-component repository owner/name;
- exact Issue-number readback;
- state type and enum (`OPEN` / `CLOSED` only).

An `OPEN` state is preserved as evidence and rejected by the existing closing-Issue policy validation. Missing/malformed/unavailable evidence fails during evidence acquisition.

Cross-repository closing Issues are checked in the repository GitHub reports. This does not change SPEC-0005's rejection of cross-repository pull requests.

Because `read_github_pr()` is called again during final GitHub revalidation, Issue-state lookup is repeated before final PASS.

## Authority comparison

Unchanged:
- PR number remains the only operator-supplied PR identity;
- PR head / merge SHA remain GitHub-derived;
- required exact merge-SHA push CI remains unchanged;
- canonical synchronization remains `git merge --ff-only` only;
- native exit-code authority remains unchanged;
- worktree inventory/removal boundary remains unchanged;
- no Issue mutation is introduced;
- no cleanup authority is introduced.

Expanded read surface:
- one authenticated `gh issue view` read per PR-reported closing Issue, repeated during final revalidation.

This is necessary to satisfy the original AC-CLOSEOUT-11 against the actual GitHub CLI data model.

## Test coverage added

The tests now model the real reference shape and cover:
- no nested `state` in `closingIssuesReferences`;
- same-repository closed Issue lookup;
- cross-repository closing Issue lookup;
- malformed repository identity;
- Issue-number mismatch;
- missing/empty/null/unknown Issue state;
- unavailable Issue lookup;
- open Issue preserved for policy rejection;
- existing final closing-Issue revalidation.

## Review conclusion

No new destructive or synchronization authority is introduced.

The correction resolves the specific real-boundary incompatibility found by PR #39 dogfood. Remaining gates before Ready:

1. exact-current-head hosted CI;
2. Windows exact-head validation;
3. corrected real dogfood against merged PR #39;
4. human Ready decision.

Merge remains a separate human-final gate.
