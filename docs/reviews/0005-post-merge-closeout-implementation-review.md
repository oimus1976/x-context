# Review-0005 — Post-merge closeout implementation adversarial review

- **Date:** 2026-09-18
- **Workstream:** Issue #38 / Draft PR #39
- **Specification:** `docs/specs/0005-post-merge-closeout-command.md`
- **Implementation under review:** `scripts/post_merge_closeout.py`
- **Test contract:** `tests/test_post_merge_closeout_command.py`
- **Base main:** `45d4347fd7caa1d1232cd7a7a306396eb4c5d301`

## Review question

Can the new post-merge closeout path eliminate manually copied PR/merge SHAs without creating a broader or less reliable mutation authority?

The review focuses on false PASS risk, hidden native-command failures, GitHub/local state drift, secret-bearing diagnostics, and accidental overlap with destructive cleanup.

## Findings and remediation

### 1. Manual authoritative-SHA transcription — remediated by design

The motivating PR #37 closeout incident passed the literal placeholder `<PR #37 merge commit SHA>` to Git. Git correctly returned a non-zero fatal error and canonical `main` remained unchanged, but the operator procedure depended on a manually copied authoritative value.

The new command accepts a PR number rather than PR-head or merge SHAs. It obtains `headRefOid` and `mergeCommit` from authenticated GitHub evidence, requires both to be full 40-character hexadecimal SHAs, and rejects incomplete or contradictory evidence before canonical synchronization.

No fallback attempts to infer a merge SHA from local history.

**Disposition:** fixed structurally.

### 2. Native stderr vs exit-code authority — contract is explicit

Windows PowerShell may render ordinary native stderr as an error record, while real Git failures also arrive on stderr. Text appearance therefore cannot determine success.

The tracked command captures stdout/stderr together for diagnostics but uses the native process exit code as the authority. Tests cover both:
- stderr-style/progress output with exit 0 remains successful;
- fatal-looking output with non-zero exit remains failure.

There is no text-based reclassification from failure to success.

**Disposition:** no blocker after contract tests.

### 3. GitHub remote userinfo could leak through surfaced Git diagnostics — found and remediated

Adversarial output testing showed that a Git message such as:

```text
From https://secret-token@github.com/example/repo
```

would initially have been surfaced verbatim even though the command's stable errors themselves did not expose it.

The native-output path now redacts HTTPS GitHub URL userinfo before emitting or retaining the returned diagnostic text. A regression test requires the sentinel to be absent while preserving the non-secret repository destination.

**Disposition:** remediated before Ready consideration.

### 4. Ambiguous duplicate workflow evidence — found and remediated

The first workflow validator selected the first exact-name / exact-SHA matching run. That relied on an ordering assumption if multiple matching workflow runs existed.

The validator now requires exactly one exact merge-SHA `push` run for each required workflow name (`project-ci`, `policy-check`). Missing, pending, unsuccessful, wrong-SHA, or duplicate matching evidence fails closed.

This is deliberately stricter than attempting to choose a winner among ambiguous evidence.

**Disposition:** remediated before Ready consideration.

### 5. GitHub evidence can change during local synchronization — bounded by final revalidation

Closing-Issue state and workflow state are checked before the canonical fast-forward. The command then runs the existing local verifier and re-reads the PR and required merge-push workflow evidence before final PASS.

The second PR read must retain the same PR head, head branch, and merge SHA and must still satisfy merged/base/repository/closing-Issue requirements. Required workflows must still satisfy exact-SHA completed-success requirements.

GitHub is not transactionally lockable by this local tool, so the final PASS is evidence about the final observed snapshot rather than a guarantee that remote state can never change afterward.

**Disposition:** bounded; no material blocker.

### 6. Canonical synchronization authority remains narrow

Before synchronization the command:
- binds the configured remote identity to the explicit `--repository` assertion;
- refreshes the canonical remote;
- proves the authoritative merge commit exists locally and is contained in that fresh remote;
- locates exactly one canonical worktree;
- requires it to be clean and free of in-progress Git operations;
- requires local canonical history to be equal to or an ancestor of the fetched canonical remote.

The only canonical synchronization command is:

```text
git merge --ff-only <remote>/<branch>
```

There is no reset, rebase, stash, force, checkout-discard, or merge-commit fallback.

**Disposition:** no material blocker.

### 7. Existing local-closeout authority is reused, not weakened

After synchronization, `verify_local_closeout.py` is executed as a separate tracked boundary. Its failure propagates to closeout failure.

This preserves its existing freshness, canonical-worktree, and clean-state requirements rather than duplicating a weaker approximation.

**Disposition:** no material blocker.

### 8. Topic worktree handling does not broaden cleanup authority

The command inventories worktrees associated with the PR head branch or exact PR-head SHA. Clean targets are reported. Dirty, unavailable, operation-in-progress, or moved topic worktrees block a full PASS.

The command does not remove or switch a worktree and does not import or invoke `post_merge_cleanup.py`. Local/remote branch and ref deletion remain outside this authority.

Canonical fast-forward may already have succeeded before a later target-worktree or final-evidence failure. The emitted canonical-head and verifier facts make that bounded allowed effect observable; a FAIL must not be interpreted as "no Git effect occurred."

**Disposition:** acceptable within SPEC-0005; destructive cleanup remains separate.

## Validation observations

The first hosted implementation run had one test-fixture portability failure: an orphan-branch fixture used `git rm -rf .` when no matching path existed. The fixture was changed to use `--ignore-unmatch`; this did not alter the product/tool contract.

A later adversarial test correctly exposed the native-diagnostic userinfo redaction defect, which was fixed.

The implementation code head `5962dc2c5d8058f648d6853c75014edd289234f2` subsequently passed both hosted `project-ci` and `policy-check`. Documentation/review commits after that head still require exact-current-head hosted validation before Ready.

## Remaining limitations / human gates

- The command depends on authenticated GitHub CLI (`gh`) reads; unavailable or malformed GitHub evidence fails closed.
- Required workflow names are project policy: `project-ci` and `policy-check`. A workflow rename must update SPEC/tests/tooling together.
- The command does not poll pending CI or rerun workflows.
- The command does not mutate Issue state; closing Issues must already be closed.
- The command performs no branch/worktree/ref/file cleanup.
- Ready and merge remain human-final.
- A Windows exact-head run is still required before Ready because this repository's authoritative operator environment is Windows and the full suite includes the real DPAPI boundary.
- The first real end-to-end qualification of the new command should be a non-destructive dogfood run after PR #39 itself is merged, using PR number only.

## Review conclusion

After the remediations above, no material implementation blocker is identified for the bounded non-destructive authority defined by SPEC-0005.

This conclusion is conditional on:
1. exact-current-head hosted `project-ci` and `policy-check` success;
2. Windows exact-head validation success;
3. no subsequent behavior-changing commit without rerunning affected evidence;
4. separate human decisions for Ready and merge.
