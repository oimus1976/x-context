"""Issue #47 RED contracts: scoped reads must not relax destructive cleanup.

All registry paths, ownership failures and native commands are synthetic. No
Git/GitHub/X subprocess is allowed through this fixture; no real repository or
worktree is mutated. Negative safety cases omit unrelated entries so a global
registry failure cannot accidentally satisfy the intended rejection assertion.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import closeout_state as state
import post_merge_closeout as closeout
import post_merge_cleanup as cleanup
import verify_local_closeout as verifier

OLD = "1" * 40
PR_HEAD = "2" * 40
MERGE = "3" * 40
OTHER = "4" * 40
TOPIC = "issue-47-topic"


class ScopedCloseoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="issue47-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.canonical = self.root / "canonical"
        self.target = self.root / "target"
        self.foreign = [self.root / f"unrelated-{n}" for n in range(7)]
        self.common = self.root / "common.git"
        self.common.mkdir()
        self.entries = []
        self.branches = {}
        self.heads = {}
        self.dirs = {}
        self.top_levels = {}
        self.commons = {}
        for path, branch, head in [
            (self.canonical, "main", OLD), (self.target, TOPIC, PR_HEAD),
            *[(path, f"unrelated-{n}", OTHER) for n, path in enumerate(self.foreign)],
        ]:
            path.mkdir()
            self.entries.append({"path": path, "branch": branch, "head": head})
            self.branches[path] = branch
            self.heads[path] = head
            self.top_levels[path] = path
            self.commons[path] = self.common
            self.dirs[path] = self.common if path == self.canonical else self.root / f"git-{path.name}"
            self.dirs[path].mkdir(exist_ok=True)
        self.unreadable = set(self.foreign)
        self.dirty = set()
        self.ignored = set()
        self.hidden = set()
        self.submodules = set()
        self.diverged = False
        self.calls = []
        self.native_calls = []
        self.evidence = closeout.PREvidence(
            47, "MERGED", "2026-10-05T00:00:00Z", "main", TOPIC,
            PR_HEAD, MERGE, False, (closeout.ClosingIssue(47, "CLOSED"),),
        )
        self.workflows = tuple(closeout.WorkflowEvidence(
            name, "push", "completed", "success", MERGE
        ) for name in closeout.REQUIRED_PUSH_WORKFLOWS)
        self.start_patch(state, "git", self.fake_git)
        self.start_patch(closeout, "invoke_native", self.fake_native)
        # Future native read helpers must use the fake boundary, never real Git.
        self.start_patch(subprocess, "run", self.forbidden_subprocess)

    def start_patch(self, module, name, value):
        patcher = patch.object(module, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def forbidden_subprocess(self, *args, **kwargs):
        self.fail("synthetic fixture attempted an unmocked subprocess")

    def without_unrelated(self):
        self.entries = self.entries[:2]

    def registry(self):
        blocks = []
        for item in self.entries:
            lines = [f"worktree {item['path']}", f"HEAD {item['head']}"]
            if item["branch"] is None:
                lines.append("detached")
            else:
                lines.append(f"branch refs/heads/{item['branch']}")
            if item.get("prunable"):
                lines.append("prunable synthetic stale registration")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n\n"

    def fake_git(self, *args, cwd, check=True):
        cwd = Path(cwd).resolve()
        self.calls.append((cwd, args))
        code, output = 0, ""
        if args == ("worktree", "list", "--porcelain"):
            output = self.registry()
        elif cwd in self.unreadable:
            code, output = 128, "fatal: detected dubious ownership in synthetic repository"
        elif args[0] == "fetch":
            pass
        elif args == ("rev-parse", "--show-toplevel"):
            output = str(self.top_levels[cwd])
        elif args[0] == "rev-parse" and args[-1] in {"--git-dir", "--git-common-dir"}:
            output = str(self.commons[cwd] if args[-1] == "--git-common-dir" else self.dirs[cwd])
        elif args[:2] == ("rev-parse", "--verify"):
            ref = args[2]
            output = self.heads[cwd] if ref == "HEAD" else {
                f"{MERGE}^{{commit}}": MERGE, "refs/remotes/origin/main": MERGE,
                "refs/heads/main": self.heads[self.canonical],
                f"refs/heads/{TOPIC}": PR_HEAD,
                f"refs/remotes/origin/{TOPIC}": PR_HEAD,
            }.get(ref, "")
            code = 0 if output else 1
        elif args == ("branch", "--show-current"):
            output = self.branches[cwd] or ""
        elif args[0] == "status":
            if cwd in self.dirty:
                output = " M tracked.txt\n"
            if "--ignored=matching" in args and cwd in self.ignored:
                output += "!! unknown-ignored\0"
        elif args[:2] == ("ls-files", "-v"):
            output = "S tracked.txt\0" if cwd in self.hidden else "H tracked.txt\0"
        elif args[:2] == ("ls-files", "--stage"):
            output = f"160000 {OTHER} 0\tsubmodule\0" if cwd in self.submodules else ""
        elif args[:2] == ("merge-base", "--is-ancestor"):
            code = 1 if self.diverged and args[2] == OLD else 0
        else:
            self.fail("unexpected synthetic Git command")
        return subprocess.CompletedProcess(["git", *args], code, output, "")

    def fake_native(self, args, *, cwd, emit):
        self.native_calls.append((Path(cwd), tuple(args)))
        if tuple(args)[:3] == ("git", "merge", "--ff-only"):
            self.heads[Path(cwd)] = MERGE
        elif tuple(args)[:2] != ("git", "fetch"):
            self.fail("unexpected synthetic native effect")
        return closeout.NativeResult(True, 0, "")

    def execute(self, requested=None):
        return closeout.run_closeout(
            requested or self.canonical, 47, "example/repo",
            pr_reader=lambda *_: self.evidence,
            workflow_reader=lambda *_: self.workflows,
            identity_reader=lambda *_: ("example/repo", None),
            verifier=lambda *_: closeout.VerifierResult(True, ""),
            emit=lambda _: None,
        )

    def assert_no_sync(self):
        self.assertFalse(any(args[:2] == ("git", "merge") for _, args in self.native_calls),
                         "unsafe topology reached canonical synchronization")
        self.assertTrue(self.heads[self.canonical] == OLD, "canonical state changed")

    def assert_blocked_before_sync(self, category, requested=None):
        result = self.execute(requested)
        self.assertFalse(result.ok, "unsafe state was accepted")
        self.assertTrue(any(category in reason for reason in result.failures),
                        "failure did not establish the intended safety boundary")
        self.assert_no_sync()

    def test_closeout_from_canonical_with_seven_foreign_worktrees(self):
        self.assertTrue(self.execute().ok, "unrelated ownership failures blocked scoped closeout")
        self.assertTrue(self.heads[self.canonical] == MERGE)

    def test_closeout_from_target_with_seven_foreign_worktrees(self):
        self.assertTrue(self.execute(self.target).ok, "unrelated ownership failures blocked scoped closeout")

    def test_detached_exact_pr_head_with_seven_foreign_worktrees(self):
        self.entries[1]["branch"] = None
        self.branches[self.target] = None
        self.assertTrue(self.execute().ok, "exact detached PR target must remain verifiable")

    def test_topic_verifier_with_seven_foreign_worktrees(self):
        self.heads[self.canonical] = MERGE
        argv = ["verify_local_closeout.py", "--repo", str(self.target), "--expected-pr-head", PR_HEAD]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            result = verifier.main()
        self.assertEqual(result, 0, "unrelated ownership failures blocked non-destructive verifier")
        self.assertFalse(self.native_calls, "verifier attempted a native mutation")

    def test_target_selection_ignores_seven_unrelated_ownership_failures(self):
        failures = closeout._target_worktree_failures(self.canonical, evidence=self.evidence, emit=lambda _: None)
        self.assertFalse(bool(failures), "unrelated entries contaminated exact target checks")

    def test_unreadable_target_blocks_before_sync(self):
        self.without_unrelated()
        self.unreadable.add(self.target)
        self.assert_blocked_before_sync("worktree")

    def test_dirty_target_blocks_before_sync(self):
        self.without_unrelated()
        self.dirty.add(self.target)
        self.assert_blocked_before_sync("target")

    def test_target_operation_blocks_before_sync(self):
        self.without_unrelated()
        (self.dirs[self.target] / "MERGE_HEAD").write_text(PR_HEAD, encoding="utf-8")
        self.assert_blocked_before_sync("target")

    def test_moved_topic_registry_head_blocks_before_sync(self):
        self.without_unrelated()
        self.entries[1]["head"] = OTHER
        self.heads[self.target] = OTHER
        self.assert_blocked_before_sync("target")

    def test_actual_target_head_must_match_registry_and_pr(self):
        self.without_unrelated()
        self.heads[self.target] = OTHER
        self.assert_blocked_before_sync("target")

    def test_unknown_actual_target_head_blocks_before_sync(self):
        self.without_unrelated()
        self.heads[self.target] = ""
        self.assert_blocked_before_sync("target")

    def test_detached_matching_head_dirty_target_blocks_before_sync(self):
        self.without_unrelated()
        self.entries[1]["branch"] = None
        self.branches[self.target] = None
        self.dirty.add(self.target)
        self.assert_blocked_before_sync("target")

    def test_every_matching_target_checked_before_sync(self):
        self.without_unrelated()
        other = self.foreign[0]
        self.entries.append({"path": other, "branch": None, "head": PR_HEAD})
        self.assert_blocked_before_sync("worktree")

    def test_prunable_target_blocks_before_sync(self):
        self.without_unrelated()
        self.entries[1]["prunable"] = True
        self.assert_blocked_before_sync("target")

    def test_target_path_bound_to_other_repository_blocks_before_sync(self):
        self.without_unrelated()
        self.commons[self.target] = self.root / "different.git"
        self.assert_blocked_before_sync("target")

    def test_target_top_level_mismatch_blocks_before_sync(self):
        self.without_unrelated()
        self.top_levels[self.target] = self.foreign[0]
        self.assert_blocked_before_sync("target")

    def test_missing_target_path_blocks_before_sync(self):
        self.without_unrelated()
        self.entries[1]["path"] = self.root / "missing"
        self.assert_blocked_before_sync("target")

    def test_ambiguous_canonical_registry_blocks_before_sync(self):
        self.without_unrelated()
        self.entries.append({"path": self.foreign[0], "branch": "main", "head": MERGE})
        self.assert_blocked_before_sync("canonical")

    def test_missing_canonical_registry_blocks_before_sync(self):
        self.without_unrelated()
        self.entries = self.entries[1:]
        self.assert_blocked_before_sync("canonical")

    def test_missing_canonical_path_blocks_before_sync(self):
        self.without_unrelated()
        self.entries[0]["path"] = self.root / "missing"
        self.assert_blocked_before_sync("canonical")

    def test_dirty_canonical_blocks_before_sync(self):
        self.without_unrelated()
        self.dirty.add(self.canonical)
        self.assert_blocked_before_sync("canonical")

    def test_canonical_operation_blocks_before_sync(self):
        self.without_unrelated()
        (self.common / "rebase-merge").mkdir()
        self.assert_blocked_before_sync("canonical")

    def test_diverged_canonical_blocks_before_sync(self):
        self.without_unrelated()
        self.diverged = True
        self.assert_blocked_before_sync("diverged")

    def test_canonical_branch_mismatch_blocks_before_sync(self):
        self.without_unrelated()
        self.branches[self.canonical] = "other"
        self.assert_blocked_before_sync("canonical")

    def test_canonical_top_level_mismatch_blocks_before_sync(self):
        self.without_unrelated()
        self.top_levels[self.canonical] = self.foreign[0]
        self.assert_blocked_before_sync("canonical", self.target)

    def test_malformed_registry_blocks_before_sync(self):
        self.registry = lambda: f"HEAD {OTHER}\nbranch refs/heads/other\n\n"
        self.assert_blocked_before_sync("canonical")

    def test_missing_merge_sha_blocks_before_sync(self):
        self.evidence = replace(self.evidence, merge_sha="")
        self.assert_blocked_before_sync("merge")

    def test_missing_successful_ci_blocks_before_sync(self):
        self.workflows = self.workflows[:1]
        self.assert_blocked_before_sync("workflow")

    def test_open_closing_issue_blocks_before_sync(self):
        self.evidence = replace(self.evidence, closing_issues=(closeout.ClosingIssue(47, "OPEN"),))
        self.assert_blocked_before_sync("issue")

    def test_clean_control_without_foreign_entries_passes(self):
        self.without_unrelated()
        self.assertTrue(self.execute().ok, "clean synthetic control must pass")

    def test_unreadable_canonical_blocks_before_sync(self):
        self.without_unrelated()
        self.unreadable.add(self.canonical)
        self.assert_blocked_before_sync("canonical", self.target)

    def test_prunable_canonical_blocks_before_sync(self):
        self.without_unrelated()
        self.entries[0]["prunable"] = True
        self.assert_blocked_before_sync("canonical")

    def test_canonical_other_common_directory_blocks_before_sync(self):
        self.without_unrelated()
        self.commons[self.canonical] = self.root / "different.git"
        self.assert_blocked_before_sync("canonical", self.target)

    def test_unreadable_detached_exact_head_target_blocks_before_sync(self):
        self.without_unrelated()
        self.entries[1]["branch"] = None
        self.branches[self.target] = None
        self.unreadable.add(self.target)
        self.assert_blocked_before_sync("worktree")

    def test_dirty_target_failure_established_despite_seven_foreign_entries(self):
        self.dirty.add(self.target)
        self.assert_blocked_before_sync("target")

    def test_strict_registry_retains_foreign_ownership_failure(self):
        entries, error = state.list_worktrees(self.canonical)
        self.assertIsNone(entries, "strict registry falsely approved unknown ownership")
        self.assertTrue(bool(error), "strict registry silently discarded an unreadable entry")

    def test_cleanup_plan_stays_blocked_by_foreign_ownership(self):
        evidence = cleanup.PREvidence(47, "MERGED", "2026-10-05T00:00:00Z", "main", TOPIC, PR_HEAD, False)
        with patch.object(cleanup, "remote_repository_identity", return_value=("example/repo", None)):
            plan, failures = cleanup.build_plan(self.canonical, 47, "main", "origin", "example/repo", False,
                                                github_reader=lambda *_: evidence)
        self.assertIsNone(plan, "destructive cleanup approved incomplete ownership topology")
        self.assertTrue(bool(failures))
        self.assert_no_sync()

    def test_cleanup_primary_target_guard_remains_fail_closed(self):
        self.without_unrelated()
        self.heads[self.canonical] = MERGE
        self.dirs[self.target] = self.common
        evidence = cleanup.PREvidence(47, "MERGED", "2026-10-05T00:00:00Z", "main", TOPIC, PR_HEAD, False)
        with patch.object(cleanup, "remote_repository_identity", return_value=("example/repo", None)), \
             patch.object(cleanup, "remote_branch_sha", return_value=(PR_HEAD, None)), \
             patch.object(cleanup, "snapshot_refs", return_value=({}, None)):
            plan, failures = cleanup.build_plan(self.canonical, 47, "main", "origin", "example/repo", False,
                                                github_reader=lambda *_: evidence)
        self.assertIsNone(plan, "primary topic worktree became a removal candidate")
        self.assertTrue(any("primary" in reason for reason in failures))
        self.assertFalse(self.native_calls)

    def test_cleanup_unknown_ignored_contents_remain_blocking(self):
        self.ignored.add(self.target)
        failures = state.cleanup_worktree_failures(self.target, "target")
        self.assertTrue(any("ignored" in reason for reason in failures))
        self.assertFalse(self.native_calls)

    def test_cleanup_hidden_index_flags_remain_blocking(self):
        self.hidden.add(self.target)
        failures = state.cleanup_worktree_failures(self.target, "target")
        self.assertTrue(any("index" in reason for reason in failures))
        self.assertFalse(self.native_calls)

    def test_cleanup_submodule_gitlinks_remain_blocking(self):
        self.submodules.add(self.target)
        failures = state.cleanup_worktree_failures(self.target, "target")
        self.assertTrue(any("submodule" in reason for reason in failures))
        self.assertFalse(self.native_calls)


if __name__ == "__main__":
    unittest.main()
