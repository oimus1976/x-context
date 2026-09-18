#!/usr/bin/env python3
"""Synchronize and verify one merged PR from authoritative GitHub evidence."""

from __future__ import annotations

import sys

# This maintenance entry point may be run from a clean canonical checkout.
# Avoid creating ignored __pycache__ residue before closeout cleanliness checks.
sys.dont_write_bytecode = True

import argparse
from dataclasses import dataclass
import json
import re
from pathlib import Path
import subprocess
from typing import Callable, Sequence

from closeout_state import (
    FULL_SHA_RE,
    canonical_worktree,
    current_branch,
    is_ancestor,
    list_worktrees,
    remote_repository_identity,
    resolve_worktree,
    rev_parse,
    worktree_failures,
)


REQUIRED_PUSH_WORKFLOWS = ("project-ci", "policy-check")
_HTTPS_GITHUB_USERINFO_RE = re.compile(r"https://[^/\s@]+@github\.com", re.IGNORECASE)


@dataclass(frozen=True)
class ClosingIssue:
    number: int
    state: str


@dataclass(frozen=True)
class PREvidence:
    number: int
    state: str
    merged_at: str | None
    base_ref: str
    head_ref: str
    head_sha: str
    merge_sha: str
    is_cross_repository: bool
    closing_issues: tuple[ClosingIssue, ...]


@dataclass(frozen=True)
class WorkflowEvidence:
    name: str
    event: str
    status: str
    conclusion: str | None
    head_sha: str


@dataclass(frozen=True)
class VerifierResult:
    ok: bool
    output: str


@dataclass(frozen=True)
class NativeResult:
    ok: bool
    exit_code: int
    output: str


@dataclass(frozen=True)
class CloseoutResult:
    ok: bool
    failures: tuple[str, ...]


PRReader = Callable[[int, str], PREvidence]
WorkflowReader = Callable[[str, str], tuple[WorkflowEvidence, ...]]
Verifier = Callable[[Path, str, str], VerifierResult]
IdentityReader = Callable[[Path, str], tuple[str | None, str | None]]
Emitter = Callable[[str], None]


def _run_process(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def invoke_native(
    args: Sequence[str],
    *,
    cwd: Path,
    emit: Emitter = print,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> NativeResult:
    """Run one native command, retain diagnostics, and trust only its exit code."""

    try:
        result = runner(
            list(args),
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError:
        emit("native_diagnostic=command could not be started")
        emit("native_exit=unavailable")
        return NativeResult(False, -1, "")

    output = result.stdout or ""
    safe_lines = [
        _HTTPS_GITHUB_USERINFO_RE.sub("https://***@github.com", line)
        for line in output.splitlines()
    ]
    for line in safe_lines:
        emit(line)
    emit(f"native_exit={result.returncode}")

    safe_output = "\n".join(safe_lines)
    if output.endswith("\n") and safe_output:
        safe_output += "\n"
    return NativeResult(result.returncode == 0, int(result.returncode), safe_output)


def _gh_json(args: Sequence[str]) -> object:
    try:
        result = _run_process(("gh", *args))
    except OSError as exc:
        raise RuntimeError("authenticated GitHub evidence is unavailable") from exc
    if result.returncode != 0:
        raise RuntimeError("authenticated GitHub evidence is unavailable")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("authenticated GitHub evidence is invalid") from exc


def read_github_pr(pr: int, repository: str) -> PREvidence:
    raw = _gh_json(
        (
            "pr",
            "view",
            str(pr),
            "-R",
            repository,
            "--json",
            "number,state,mergedAt,baseRefName,headRefName,headRefOid,isCrossRepository,mergeCommit,closingIssuesReferences",
        )
    )
    if not isinstance(raw, dict):
        raise RuntimeError("authenticated GitHub PR evidence is invalid")

    try:
        merge = raw.get("mergeCommit")
        merge_sha = merge.get("oid") if isinstance(merge, dict) else ""
        raw_issues = raw.get("closingIssuesReferences") or []
        if not isinstance(raw_issues, list):
            raise TypeError
        issues = tuple(
            ClosingIssue(number=int(item["number"]), state=str(item["state"]))
            for item in raw_issues
            if isinstance(item, dict)
        )
        if len(issues) != len(raw_issues):
            raise TypeError
        return PREvidence(
            number=int(raw["number"]),
            state=str(raw["state"]),
            merged_at=raw.get("mergedAt"),
            base_ref=str(raw["baseRefName"]),
            head_ref=str(raw["headRefName"]),
            head_sha=str(raw["headRefOid"]),
            merge_sha=str(merge_sha or ""),
            is_cross_repository=bool(raw["isCrossRepository"]),
            closing_issues=issues,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("authenticated GitHub PR evidence is incomplete") from exc


def read_merge_workflows(merge_sha: str, repository: str) -> tuple[WorkflowEvidence, ...]:
    raw = _gh_json(
        (
            "run",
            "list",
            "-R",
            repository,
            "--commit",
            merge_sha,
            "--event",
            "push",
            "--limit",
            "100",
            "--json",
            "name,event,status,conclusion,headSha",
        )
    )
    if not isinstance(raw, list):
        raise RuntimeError("authenticated GitHub workflow evidence is invalid")

    runs: list[WorkflowEvidence] = []
    try:
        for item in raw:
            if not isinstance(item, dict):
                raise TypeError
            runs.append(
                WorkflowEvidence(
                    name=str(item["name"]),
                    event=str(item["event"]),
                    status=str(item["status"]),
                    conclusion=(
                        None
                        if item.get("conclusion") is None
                        else str(item.get("conclusion"))
                    ),
                    head_sha=str(item["headSha"]),
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("authenticated GitHub workflow evidence is incomplete") from exc
    return tuple(runs)


def run_local_verifier(repo: Path, branch: str, remote: str) -> VerifierResult:
    verifier = Path(__file__).resolve().with_name("verify_local_closeout.py")
    try:
        result = _run_process(
            (
                sys.executable,
                str(verifier),
                "--repo",
                str(repo),
                "--branch",
                branch,
                "--remote",
                remote,
            ),
            cwd=repo,
        )
    except OSError:
        return VerifierResult(False, "LOCAL CLOSEOUT: FAIL\n")
    return VerifierResult(result.returncode == 0, result.stdout or "")


def _fail(emit: Emitter, failures: Sequence[str]) -> CloseoutResult:
    for failure in failures:
        emit(f"FAIL: {failure}")
    emit("POST-MERGE CLOSEOUT: FAIL")
    return CloseoutResult(False, tuple(failures))


def _validate_pr_evidence(
    evidence: PREvidence,
    *,
    requested_pr: int,
    branch: str,
) -> list[str]:
    failures: list[str] = []
    if evidence.number != requested_pr:
        failures.append("GitHub PR number does not match the requested PR")
    if evidence.state.upper() != "MERGED" or not evidence.merged_at:
        failures.append("GitHub PR is not proven merged")
    if evidence.base_ref != branch:
        failures.append("GitHub PR base branch does not match the canonical branch")
    if evidence.is_cross_repository:
        failures.append("cross-repository PR closeout is unsupported")
    if not evidence.head_ref:
        failures.append("GitHub PR head branch is missing")
    if not FULL_SHA_RE.fullmatch(evidence.head_sha):
        failures.append("GitHub PR head SHA is not a full 40-character hexadecimal SHA")
    if not FULL_SHA_RE.fullmatch(evidence.merge_sha):
        failures.append("GitHub merge commit SHA is not a full 40-character hexadecimal SHA")
    return failures


def _validate_closing_issues(evidence: PREvidence) -> list[str]:
    failures: list[str] = []
    for issue in evidence.closing_issues:
        if issue.number <= 0 or issue.state.upper() != "CLOSED":
            failures.append(f"GitHub closing issue #{issue.number} is not closed")
    return failures


def _validate_workflows(
    workflows: tuple[WorkflowEvidence, ...],
    *,
    merge_sha: str,
) -> list[str]:
    failures: list[str] = []
    for required in REQUIRED_PUSH_WORKFLOWS:
        matching = [
            run
            for run in workflows
            if run.name == required
            and run.event == "push"
            and run.head_sha.lower() == merge_sha.lower()
        ]
        if not matching:
            failures.append(
                f"required workflow {required!r} is missing for the merge commit push"
            )
            continue
        current = matching[0]
        if current.status.lower() != "completed":
            failures.append(f"required workflow {required!r} is not completed")
        elif (current.conclusion or "").lower() != "success":
            failures.append(f"required workflow {required!r} did not succeed")
    return failures


def _refresh_canonical(
    repo: Path,
    *,
    remote: str,
    branch: str,
    emit: Emitter,
) -> tuple[str | None, str | None]:
    remote_ref = f"refs/remotes/{remote}/{branch}"
    refspec = f"+refs/heads/{branch}:{remote_ref}"
    fetched = invoke_native(
        ("git", "fetch", remote, refspec),
        cwd=repo,
        emit=emit,
    )
    if not fetched.ok:
        return None, f"could not refresh {remote}/{branch}; remote freshness is unverified"
    remote_sha = rev_parse(repo, remote_ref)
    if remote_sha is None:
        return None, f"remote-tracking ref is unavailable: {remote}/{branch}"
    return remote_sha, None


def _target_worktree_failures(
    repo: Path,
    *,
    evidence: PREvidence,
    emit: Emitter,
) -> list[str]:
    worktrees, error = list_worktrees(repo)
    if error or worktrees is None:
        return [error or "worktree registry is unavailable"]

    topic_ref = f"refs/heads/{evidence.head_ref}"
    targets = [
        item
        for item in worktrees
        if item.branch_ref == topic_ref
        or (item.head or "").lower() == evidence.head_sha.lower()
    ]

    emit(f"target_worktree_count={len(targets)}")
    failures: list[str] = []
    for item in targets:
        if not item.path.is_dir():
            emit("target_worktree_state=unavailable")
            failures.append("target worktree path is unavailable")
            continue

        state_failures = worktree_failures(item.path, "target")
        if item.branch_ref == topic_ref and (item.head or "").lower() != evidence.head_sha.lower():
            state_failures.append("target topic worktree HEAD moved from the merged PR head")

        if state_failures:
            emit("target_worktree_state=blocked")
            failures.extend(
                f"target worktree: {failure}" for failure in state_failures
            )
        else:
            emit("target_worktree_state=clean")
            emit(
                "target_worktree_mode="
                + ("detached" if item.detached else "topic-branch")
            )
    return failures


def run_closeout(
    repo: Path,
    pr: int,
    repository: str,
    *,
    branch: str = "main",
    remote: str = "origin",
    pr_reader: PRReader = read_github_pr,
    workflow_reader: WorkflowReader = read_merge_workflows,
    verifier: Verifier = run_local_verifier,
    identity_reader: IdentityReader = remote_repository_identity,
    emit: Emitter = print,
) -> CloseoutResult:
    requested, error = resolve_worktree(Path(repo))
    if error or requested is None:
        return _fail(emit, [error or "repository/worktree could not be resolved"])

    identity, identity_error = identity_reader(requested, remote)
    if identity_error or identity is None:
        return _fail(
            emit,
            [identity_error or f"could not establish {remote} repository identity"],
        )
    if identity.lower() != repository.lower():
        return _fail(
            emit,
            [
                f"repository identity mismatch: local {remote} does not match the asserted repository"
            ],
        )

    try:
        evidence = pr_reader(pr, repository)
    except RuntimeError as exc:
        return _fail(emit, [str(exc)])

    evidence_failures = _validate_pr_evidence(
        evidence,
        requested_pr=pr,
        branch=branch,
    )
    if evidence_failures:
        return _fail(emit, evidence_failures)

    issue_failures = _validate_closing_issues(evidence)
    if issue_failures:
        return _fail(emit, issue_failures)

    try:
        workflows = workflow_reader(evidence.merge_sha, repository)
    except RuntimeError as exc:
        return _fail(emit, [str(exc)])
    workflow_failures = _validate_workflows(
        workflows,
        merge_sha=evidence.merge_sha,
    )
    if workflow_failures:
        return _fail(emit, workflow_failures)

    emit(f"repository={repository}")
    emit(f"pr={pr}")
    emit(f"pr_head={evidence.head_sha}")
    emit(f"merge_commit={evidence.merge_sha}")
    emit("merge_push_ci=PASS")
    emit(
        "closing_issues=PASS"
        if evidence.closing_issues
        else "closing_issues=none"
    )

    remote_sha, freshness_error = _refresh_canonical(
        requested,
        remote=remote,
        branch=branch,
        emit=emit,
    )
    if freshness_error or remote_sha is None:
        return _fail(emit, [freshness_error or "canonical freshness is unverified"])

    merge_object = rev_parse(requested, f"{evidence.merge_sha}^{{commit}}")
    if merge_object is None or merge_object.lower() != evidence.merge_sha.lower():
        return _fail(emit, ["authoritative merge commit is unavailable after fetch"])
    if not is_ancestor(requested, evidence.merge_sha, remote_sha):
        return _fail(
            emit,
            ["authoritative merge commit is not contained in the fetched canonical remote"],
        )
    emit("merge_commit_contained=PASS")

    canonical = canonical_worktree(requested, branch)
    if canonical is None:
        return _fail(
            emit,
            [
                f"canonical branch {branch!r} is not checked out in exactly one available worktree"
            ],
        )

    canonical_failures = worktree_failures(canonical, "canonical")
    if current_branch(canonical) != branch:
        canonical_failures.append(
            f"canonical worktree is not on branch {branch!r}"
        )
    if canonical_failures:
        return _fail(emit, canonical_failures)

    local_before = rev_parse(canonical, "HEAD")
    if local_before is None:
        return _fail(emit, ["canonical HEAD is unavailable"])
    emit(f"canonical_head_before={local_before}")
    emit(f"canonical_remote_head={remote_sha}")

    if local_before != remote_sha and not is_ancestor(canonical, local_before, remote_sha):
        return _fail(
            emit,
            ["canonical branch has diverged; safe fast-forward is unavailable"],
        )

    merged = invoke_native(
        ("git", "merge", "--ff-only", f"{remote}/{branch}"),
        cwd=canonical,
        emit=emit,
    )
    if not merged.ok:
        return _fail(
            emit,
            [f"canonical fast-forward failed with exit code {merged.exit_code}"],
        )

    local_after = rev_parse(canonical, "HEAD")
    refreshed_after = rev_parse(canonical, f"refs/remotes/{remote}/{branch}")
    if local_after is None or refreshed_after is None or local_after != refreshed_after:
        return _fail(
            emit,
            ["canonical HEAD does not match the freshly fetched remote after fast-forward"],
        )
    if not is_ancestor(canonical, evidence.merge_sha, local_after):
        return _fail(
            emit,
            ["canonical final HEAD does not contain the authoritative merge commit"],
        )
    emit(f"canonical_head_after={local_after}")

    verified = verifier(canonical, branch, remote)
    for line in verified.output.splitlines():
        emit(line)
    if not verified.ok:
        return _fail(emit, ["existing local closeout verifier failed"])
    emit("local_closeout_verifier=PASS")

    try:
        final_evidence = pr_reader(pr, repository)
    except RuntimeError as exc:
        return _fail(emit, [str(exc)])
    final_evidence_failures = _validate_pr_evidence(
        final_evidence,
        requested_pr=pr,
        branch=branch,
    )
    if (
        final_evidence.head_sha.lower() != evidence.head_sha.lower()
        or final_evidence.merge_sha.lower() != evidence.merge_sha.lower()
        or final_evidence.head_ref != evidence.head_ref
    ):
        final_evidence_failures.append(
            "GitHub PR evidence changed during closeout; rerun from a fresh state"
        )
    final_evidence_failures.extend(_validate_closing_issues(final_evidence))
    if final_evidence_failures:
        return _fail(emit, final_evidence_failures)

    try:
        final_workflows = workflow_reader(evidence.merge_sha, repository)
    except RuntimeError as exc:
        return _fail(emit, [str(exc)])
    final_workflow_failures = _validate_workflows(
        final_workflows,
        merge_sha=evidence.merge_sha,
    )
    if final_workflow_failures:
        return _fail(emit, final_workflow_failures)
    emit("final_github_revalidation=PASS")

    target_failures = _target_worktree_failures(
        canonical,
        evidence=evidence,
        emit=emit,
    )
    if target_failures:
        return _fail(emit, target_failures)

    emit("POST-MERGE CLOSEOUT: PASS")
    return CloseoutResult(True, ())


def _positive_pr(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("PR number must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("PR number must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize and verify one merged PR from authoritative GitHub evidence."
    )
    parser.add_argument("--repo", default=".", help="Any worktree in the local repository.")
    parser.add_argument("--pr", required=True, type=_positive_pr, help="Merged pull-request number.")
    parser.add_argument(
        "--repository",
        required=True,
        help="Expected GitHub repository in owner/repo form; must match the configured remote.",
    )
    parser.add_argument("--branch", default="main", help="Canonical branch.")
    parser.add_argument("--remote", default="origin", help="Canonical Git remote.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_closeout(
        Path(args.repo),
        args.pr,
        args.repository,
        branch=args.branch,
        remote=args.remote,
    )
    return 0 if result.ok else 2


if __name__ == "__main__":
    sys.exit(main())
