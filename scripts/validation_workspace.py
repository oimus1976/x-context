from __future__ import annotations

import argparse
import json
import ntpath
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - Python < 3.11 is unsupported here
    raise RuntimeError("Python 3.11+ is required for validation workspace policy") from exc


class WorkspacePolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspacePolicy:
    canonical_repo: str
    disposable_root: str
    worktree_root: str
    durable_log_dir: str
    final_branch: str


def _expand_windows_env(value: str, environ: Mapping[str, str]) -> str:
    result = value
    for _ in range(8):
        start = result.find("%")
        if start < 0:
            break
        end = result.find("%", start + 1)
        if end < 0:
            break
        name = result[start + 1 : end]
        if not name:
            raise WorkspacePolicyError("empty environment variable reference in policy path")
        replacement = environ.get(name)
        if replacement is None:
            raise WorkspacePolicyError(f"required environment variable is not set: {name}")
        result = result[:start] + replacement + result[end + 1 :]
    if "%" in result:
        raise WorkspacePolicyError(f"unresolved environment variable reference in path: {value}")
    return result


def _norm(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise WorkspacePolicyError("path must be a non-empty string")
    return ntpath.normcase(ntpath.normpath(path))


def _is_absolute_windows_path(path: str) -> bool:
    drive, tail = ntpath.splitdrive(path)
    return bool(drive) and tail.startswith(("\\", "/"))


def _require_absolute(path: str, label: str) -> None:
    if not _is_absolute_windows_path(path):
        raise WorkspacePolicyError(f"{label} must be an absolute Windows path: {path}")


def _is_strict_child(path: str, root: str) -> bool:
    npath = _norm(path)
    nroot = _norm(root)
    try:
        common = ntpath.commonpath([npath, nroot])
    except ValueError:
        return False
    return common == nroot and npath != nroot


def load_policy(profile_path: Path, *, environ: Mapping[str, str] | None = None) -> WorkspacePolicy:
    env = os.environ if environ is None else environ
    with profile_path.open("rb") as handle:
        data = tomllib.load(handle)
    raw = data.get("validation_workspace")
    if not isinstance(raw, dict):
        raise WorkspacePolicyError("PROJECT_PROFILE.toml lacks [validation_workspace]")

    required = ("canonical_repo", "disposable_root", "worktree_root", "durable_log_dir", "final_branch")
    missing = [name for name in required if not isinstance(raw.get(name), str) or not raw.get(name)]
    if missing:
        raise WorkspacePolicyError("missing validation workspace fields: " + ", ".join(missing))

    policy = WorkspacePolicy(
        canonical_repo=_expand_windows_env(raw["canonical_repo"], env),
        disposable_root=_expand_windows_env(raw["disposable_root"], env),
        worktree_root=_expand_windows_env(raw["worktree_root"], env),
        durable_log_dir=_expand_windows_env(raw["durable_log_dir"], env),
        final_branch=raw["final_branch"],
    )

    for label, value in (
        ("canonical_repo", policy.canonical_repo),
        ("disposable_root", policy.disposable_root),
        ("worktree_root", policy.worktree_root),
        ("durable_log_dir", policy.durable_log_dir),
    ):
        _require_absolute(value, label)

    if not _is_strict_child(policy.worktree_root, policy.disposable_root):
        raise WorkspacePolicyError("worktree_root must be beneath disposable_root")
    if not _is_strict_child(policy.durable_log_dir, policy.canonical_repo):
        raise WorkspacePolicyError("durable_log_dir must be beneath canonical_repo")
    return policy


def validate_canonical_repo(actual_repo: str, policy: WorkspacePolicy) -> None:
    if _norm(actual_repo) != _norm(policy.canonical_repo):
        raise WorkspacePolicyError(
            f"canonical repository mismatch: expected '{policy.canonical_repo}', actual '{actual_repo}'"
        )


def validate_disposable_path(path: str, policy: WorkspacePolicy, *, kind: str) -> None:
    root = policy.worktree_root if kind == "worktree" else policy.disposable_root
    if not _is_strict_child(path, root):
        raise WorkspacePolicyError(f"{kind} path must be beneath '{root}': {path}")


def validate_durable_log_path(path: str, policy: WorkspacePolicy) -> None:
    if not _is_strict_child(path, policy.durable_log_dir):
        raise WorkspacePolicyError(
            f"durable log path must be beneath '{policy.durable_log_dir}': {path}"
        )


def validate_final_state(
    *,
    location: str,
    branch: str,
    head: str,
    origin_main: str,
    status_lines: list[str],
    log_path: str,
    log_exists: bool,
    log_size: int,
    policy: WorkspacePolicy,
) -> None:
    validate_canonical_repo(location, policy)
    if branch != policy.final_branch:
        raise WorkspacePolicyError(
            f"final branch mismatch: expected '{policy.final_branch}', actual '{branch}'"
        )
    if not head or head != origin_main:
        raise WorkspacePolicyError(
            f"final HEAD/origin mismatch: HEAD='{head}', origin/main='{origin_main}'"
        )
    if status_lines:
        raise WorkspacePolicyError("final canonical working tree is not clean")
    validate_durable_log_path(log_path, policy)
    if not log_exists:
        raise WorkspacePolicyError(f"durable verification log does not exist: {log_path}")
    if log_size <= 0:
        raise WorkspacePolicyError(f"durable verification log is empty: {log_path}")


def _policy_json(policy: WorkspacePolicy) -> str:
    return json.dumps(
        {
            "canonical_repo": policy.canonical_repo,
            "disposable_root": policy.disposable_root,
            "worktree_root": policy.worktree_root,
            "durable_log_dir": policy.durable_log_dir,
            "final_branch": policy.final_branch,
        },
        separators=(",", ":"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("paths")

    p_repo = sub.add_parser("check-repo")
    p_repo.add_argument("path")

    p_disp = sub.add_parser("check-disposable")
    p_disp.add_argument("--kind", choices=("worktree", "scratch"), required=True)
    p_disp.add_argument("path")

    p_log = sub.add_parser("check-log")
    p_log.add_argument("path")

    args = parser.parse_args(argv)
    policy = load_policy(Path(args.profile))

    try:
        if args.command == "paths":
            print(_policy_json(policy))
        elif args.command == "check-repo":
            validate_canonical_repo(args.path, policy)
        elif args.command == "check-disposable":
            validate_disposable_path(args.path, policy, kind=args.kind)
        elif args.command == "check-log":
            validate_durable_log_path(args.path, policy)
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except WorkspacePolicyError as exc:
        print(str(exc), file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
