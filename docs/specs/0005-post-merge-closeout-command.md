# SPEC-0005 — Authoritative post-merge closeout command

- **Status:** Proposed maintenance specification
- **Date recorded:** 2026-09-18
- **Related:** Issue #38, `scripts/verify_local_closeout.py`, `scripts/post_merge_cleanup.py`
- **Base:** `45d4347fd7caa1d1232cd7a7a306396eb4c5d301`

## Purpose

Replace ad hoc post-merge scripts and manually copied commit SHAs with one tracked, non-destructive closeout command whose only PR identity input is the pull-request number.

The motivating incident occurred after PR #37: an executable PowerShell snippet still contained the placeholder `<PR #37 merge commit SHA>`. Git correctly returned a non-zero exit with `fatal: Not a valid object name`. The failure was safe because canonical `main` had not yet been fast-forwarded, but the procedure depended on manual transcription of authoritative GitHub state and therefore admitted an avoidable operator/tooling error.

This specification also makes explicit that Windows PowerShell rendering native stderr as `NativeCommandError` is not a success/failure authority. Native output is evidence; the native process exit code and validated preconditions determine success.

## Command contract

The tracked command is:

```text
python scripts/post_merge_closeout.py --pr <number> --repository <owner/repo>
```

Optional maintenance parameters may select the canonical branch and remote, defaulting to `main` and `origin`.

The operator does not supply:

- PR head SHA;
- merge commit SHA;
- closing Issue number;
- CI run identifier.

Those values are derived from authenticated GitHub evidence.

## Authority boundaries

The command may:

- read authenticated GitHub PR metadata;
- read GitHub Actions run metadata;
- read local Git/worktree state;
- fetch the configured canonical remote branch;
- fast-forward the canonical local branch to the freshly fetched remote branch;
- execute the existing tracked local-closeout verifier;
- report target-PR worktree state.

The command must not:

- reset, rebase, create a merge commit, stash, discard, or force-update local work;
- delete any worktree, local branch, remote branch, remote-tracking ref, file, ignored residue, or Issue;
- mark a PR Ready, merge a PR, close an Issue, or rerun CI;
- call the destructive cleanup executor.

`scripts/post_merge_cleanup.py` remains a separate explicit authority boundary.

## GitHub PR evidence

Before canonical-branch mutation, authenticated GitHub evidence must establish:

- requested PR number matches the returned PR;
- state is merged;
- merge timestamp is present;
- base branch exactly matches the requested canonical branch;
- PR is same-repository;
- head branch is non-empty;
- head SHA is a full 40-character hexadecimal SHA;
- merge commit SHA is a full 40-character hexadecimal SHA;
- every GitHub closing Issue reference is closed.

Missing, malformed, placeholder-like, contradictory, or unavailable evidence fails closed.

The command must not reconstruct or guess a merge SHA from local history.

## Repository identity

The configured remote fetch and push URLs must resolve to one unambiguous `github.com/<owner>/<repo>` identity using the existing shared boundary.

The derived identity must exactly match the explicit `--repository` assertion, case-insensitively.

A mismatch or non-GitHub/ambiguous remote fails before synchronization.

## Post-merge CI evidence

The required merge-commit push workflows are:

- `project-ci`;
- `policy-check`.

For each workflow, GitHub evidence must refer to:

- event `push`;
- head SHA equal to the authoritative merge commit SHA;
- completed status;
- successful conclusion.

A missing, pending, cancelled, failed, skipped, or wrong-SHA run blocks closeout. PR-head CI is not a substitute for merge-commit push CI.

The command does not poll or rerun CI. The operator may rerun the command later.

## Canonical synchronization

After GitHub evidence is accepted:

1. resolve the requested repository/worktree;
2. fetch only the canonical remote branch using the existing freshness contract;
3. verify the authoritative merge commit exists locally after fetch;
4. verify that merge commit is an ancestor of the freshly fetched canonical remote;
5. locate exactly one canonical worktree for the canonical branch;
6. require it to be clean and free of in-progress Git operations;
7. require the local canonical HEAD to be equal to, or an ancestor of, the fetched remote canonical HEAD;
8. synchronize only with `git merge --ff-only <remote>/<branch>`;
9. treat any non-zero native exit as failure;
10. run the existing `verify_local_closeout.py` boundary after synchronization.

No fallback synchronization method exists.

## Native command semantics

Native stdout/stderr is diagnostic evidence, not a success classifier.

For every native command whose output is surfaced by this orchestrator:

- stdout and stderr are captured together for deterministic operator logging;
- relevant diagnostic output is retained/surfaced;
- the process exit code is authoritative;
- exit code zero may succeed even when Git writes ordinary progress to stderr;
- any non-zero exit is failure regardless of whether the text appears benign;
- placeholder or malformed SHA values must be rejected before they can reach Git.

Provider/CLI exception text that could contain uncontrolled environment details is not passed through as a stable product decision.

## Worktree inventory

After synchronization and local verification, enumerate worktrees associated with the target PR by either:

- branch ref equal to the authoritative PR head branch; or
- HEAD equal to the authoritative PR head SHA.

The command reports whether each matching worktree is available, clean, dirty, detached, or still on the topic branch.

It does not remove or modify those worktrees. Destructive cleanup requires the separate cleanup workflow.

A target worktree with uncommitted/untracked changes or an in-progress Git operation blocks a full closeout PASS because the task still has unresolved local state.

Unrelated worktrees are not modified and do not block closeout merely by existing.

## Output contract

Success output contains stable non-secret facts including:

- repository;
- PR number;
- PR head SHA;
- merge commit SHA;
- merge push CI result;
- closing-Issue result;
- canonical pre/post HEAD;
- local verifier result;
- target worktree count/state;
- final `POST-MERGE CLOSEOUT: PASS`.

Failure output names a stable blocking reason and ends with `POST-MERGE CLOSEOUT: FAIL`.

No credential, token, Authorization header, arbitrary environment value, or raw authenticated GitHub response is emitted.

## Acceptance criteria

- **AC-CLOSEOUT-01:** PR number is the only operator-supplied PR identity; PR head and merge SHA are never required as inputs.
- **AC-CLOSEOUT-02:** local remote identity must match `--repository` before GitHub evidence is accepted.
- **AC-CLOSEOUT-03:** GitHub must prove merged, same-repository, expected-base PR state with full head and merge SHAs.
- **AC-CLOSEOUT-04:** missing/malformed/placeholder-like/contradictory evidence fails before canonical mutation.
- **AC-CLOSEOUT-05:** canonical remote freshness is re-established before merge containment or synchronization.
- **AC-CLOSEOUT-06:** authoritative merge commit must exist after fetch and be an ancestor of the fetched canonical remote.
- **AC-CLOSEOUT-07:** canonical worktree must be unique, clean, operation-free, and safely fast-forwardable; synchronization uses only `git merge --ff-only`.
- **AC-CLOSEOUT-08:** native output is retained while non-zero exit is always failure; stderr text alone never overrides exit status.
- **AC-CLOSEOUT-09:** existing `verify_local_closeout.py` remains authoritative after synchronization.
- **AC-CLOSEOUT-10:** target PR worktrees are inventoried but never deleted or switched by this command; dirty/in-progress target state blocks PASS.
- **AC-CLOSEOUT-11:** all GitHub closing Issues must be closed; the command never closes them.
- **AC-CLOSEOUT-12:** `project-ci` and `policy-check` must have successful completed `push` runs on the exact merge SHA.
- **AC-CLOSEOUT-13:** no cleanup authority is added; branch/ref/worktree/file deletion remains out of scope.
- **AC-CLOSEOUT-14:** success/failure output is stable, non-secret, and ends with an explicit PASS/FAIL marker.

## Test-first plan

Tests precede implementation and cover:

- merged happy path using GitHub-derived head/merge SHAs;
- unmerged, wrong-base, cross-repository, malformed-SHA evidence;
- repository-identity mismatch;
- remote canonical that does not contain the merge commit;
- dirty or in-progress canonical worktree;
- divergent local canonical history and absence of reset/rebase fallback;
- native exit-code authority for both stderr-with-zero and non-zero cases;
- existing verifier failure propagation;
- clean retained target worktree reporting;
- dirty/in-progress target worktree blocking without deletion;
- open closing Issue blocking;
- missing/pending/failed/wrong-SHA merge push CI blocking;
- successful exact-SHA push CI acceptance;
- no invocation of destructive cleanup.

## Human gates

Ready and merge remain separate human-final decisions.

This command is a post-merge verifier/synchronizer. It does not authorize the merge that precedes it or destructive cleanup that may follow it.

## Work order

**Requirement -> Acceptance Criteria -> Tests -> Implementation**
