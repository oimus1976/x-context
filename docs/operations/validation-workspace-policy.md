# Validation workspace policy

This note records a blocking operational requirement discovered during Issue #11 validation. It is not the enforcement mechanism itself.

The project requires a separate tracked governance/tooling change before future validation commands are treated as policy-compliant.

Required invariant:

- canonical repository: `C:\Users\oimus\x-context`
- disposable validation worktrees and scratch artifacts: beneath a dedicated project temp root `%TEMP%\x-context\`; do not create x-context validation worktrees or scratch artifacts directly beneath `%TEMP%`
- durable verification evidence: beneath the canonical repository `logs\verification\`
- final operator location after validation: canonical repository
- final canonical branch: `main`
- final canonical HEAD: the freshly verified `origin/main` expected by that validation
- final canonical status: clean

Enforcement target:

1. define these project-specific workspace paths in `PROJECT_PROFILE.toml`;
2. provide a tracked reusable PowerShell validation helper that derives paths from project policy rather than ad-hoc chat snippets;
3. fail before effects when a disposable worktree/scratch path is outside the dedicated temp root or a durable evidence path is outside `logs\verification`;
4. verify final location/branch/HEAD/status/log existence;
5. add negative tests proving policy violations are rejected;
6. distinguish DECLARED, ENFORCED, and VERIFIED state in `PROJECT_PROFILE.toml`.

Until that enforcement work is merged, ad-hoc validation snippets must not be described as enforcing this workspace policy.