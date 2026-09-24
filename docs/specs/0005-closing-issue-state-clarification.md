# SPEC-0005 clarification — Closing-Issue state lookup

- **Status:** Proposed compatibility clarification
- **Date recorded:** 2026-09-24
- **Related:** SPEC-0005, Issue #40, PR #39 dogfood
- **Base:** `62b61978676d30158db740ff61aba917114bc738`

## Purpose

Correct SPEC-0005's closing-Issue evidence implementation so it matches the real GitHub CLI JSON contract without weakening the original requirement that every closing Issue be closed before post-merge closeout can pass.

The first real dogfood of PR #39 failed before canonical synchronization with:

```text
FAIL: authenticated GitHub PR evidence is incomplete
POST-MERGE CLOSEOUT: FAIL
```

The failure was caused by assuming that nested objects from:

```text
gh pr view <pr> -R owner/repo --json closingIssuesReferences
```

contain an Issue `state` field.

Current GitHub CLI exports closing-Issue references with identity data such as:

- Issue number;
- Issue URL;
- repository name;
- repository owner.

It does not export Issue state inside that nested reference object.

Issue state is separately available through:

```text
gh issue view <number> -R owner/repo --json number,state
```

## Clarified evidence model

A closing-Issue reference and a closing-Issue state observation are separate evidence objects.

### Reference discovery

`gh pr view` remains authoritative for which Issues the PR claims to close.

For each returned closing-Issue reference the closeout command must require:

- a positive Issue number;
- a repository object;
- non-empty repository owner login;
- non-empty repository name.

The repository identity is normalized as `owner/repo`.

A malformed or ambiguous reference fails closed.

### Current Issue-state lookup

For every validated reference, perform one authenticated lookup:

```text
gh issue view <number> -R owner/repo --json number,state
```

The returned object must:

- be a JSON object;
- contain the same positive Issue number requested;
- contain a non-empty state;
- report state `CLOSED`.

Any unavailable, malformed, number-mismatched, or non-closed result fails closed.

### Cross-repository closing Issues

SPEC-0005 continues to reject cross-repository **pull requests**.

That does not imply that a same-repository PR may only close Issues in its own repository. If GitHub reports a closing-Issue reference in another GitHub repository, the closeout command must check that Issue in the reported repository.

No mutation authority is added for that repository.

## Revalidation

The original SPEC-0005 final GitHub revalidation remains in force.

Because `read_github_pr()` performs fresh Issue-state lookups while rebuilding the PR evidence, the final revalidation must also repeat the Issue-state reads. A closing Issue reopened during closeout therefore blocks final PASS.

## Acceptance criteria

- **AC-CLOSEOUT-F1-01:** real `closingIssuesReferences` objects without nested `state` are accepted as reference identity objects.
- **AC-CLOSEOUT-F1-02:** each reference requires a positive Issue number plus non-empty repository owner/name.
- **AC-CLOSEOUT-F1-03:** each reference causes one authenticated `gh issue view <number> -R owner/repo --json number,state` read.
- **AC-CLOSEOUT-F1-04:** Issue lookup number mismatch, missing/malformed state, or unavailable evidence fails closed.
- **AC-CLOSEOUT-F1-05:** any Issue state other than `CLOSED` blocks closeout.
- **AC-CLOSEOUT-F1-06:** cross-repository closing-Issue references are checked in their reported repository; cross-repository PR rejection is unchanged.
- **AC-CLOSEOUT-F1-07:** final PR evidence revalidation repeats closing-Issue state reads.
- **AC-CLOSEOUT-F1-08:** SHA derivation, required workflow checks, canonical ff-only synchronization, native exit semantics, worktree handling, and cleanup authority remain unchanged.
- **AC-CLOSEOUT-F1-09:** automated fixtures model the real exported closing-Issue reference shape and must not reintroduce a synthetic nested `state` field.

## Work order

**Requirement -> Acceptance Criteria -> Tests -> Implementation**

Ready and merge remain human-final.
