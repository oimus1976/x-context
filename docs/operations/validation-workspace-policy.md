# Validation workspace policy

This document defines the project-specific validation workspace and durable-evidence paths for x-context.

## Required paths

- canonical repository: `C:\Users\oimus\x-context`
- disposable validation/scratch root: `%TEMP%\x-context\`
- disposable worktrees: beneath `%TEMP%\x-context\worktrees\`
- durable verification evidence: beneath `C:\Users\oimus\x-context\logs\verification\`

Validation tooling must not create x-context worktrees or scratch artifacts directly beneath `%TEMP%`.

## Required final state

A validation run must finish with:

- current directory = canonical repository
- branch = `main`
- HEAD = the expected freshly verified `origin/main`
- working tree clean
- durable log exists in `logs\verification\` and is non-empty

## Enforcement target

The tracked validation helper must derive paths from project policy and fail closed when:

- a disposable worktree/scratch path is outside the dedicated x-context temp root;
- a durable log path is outside `logs\verification`;
- final location/branch/HEAD/status/log postconditions are not satisfied.

Negative tests must prove these violations are rejected.
