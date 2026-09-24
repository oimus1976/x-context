from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import post_merge_closeout as closeout


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


class PostMergeCloseoutCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp, True)

        self.remote = self.temp / "remote.git"
        run("git", "init", "--bare", "--initial-branch=main", str(self.remote), cwd=self.temp)

        self.repo = self.temp / "repo"
        run("git", "clone", str(self.remote), str(self.repo), cwd=self.temp)
        self.configure(self.repo)
        (self.repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
        run("git", "add", "tracked.txt", cwd=self.repo)
        run("git", "commit", "-m", "initial", cwd=self.repo)
        run("git", "push", "-u", "origin", "main", cwd=self.repo)
        self.initial_head = self.head(self.repo)

        self.author = self.temp / "author"
        run("git", "clone", str(self.remote), str(self.author), cwd=self.temp)
        self.configure(self.author)
        run("git", "switch", "-c", "issue-38-topic", cwd=self.author)
        (self.author / "topic.txt").write_text("topic\n", encoding="utf-8")
        run("git", "add", "topic.txt", cwd=self.author)
        run("git", "commit", "-m", "topic", cwd=self.author)
        self.pr_head = self.head(self.author)
        run("git", "push", "-u", "origin", "issue-38-topic", cwd=self.author)
        run("git", "switch", "main", cwd=self.author)
        run("git", "merge", "--no-ff", "issue-38-topic", "-m", "merge topic", cwd=self.author)
        self.merge_sha = self.head(self.author)
        run("git", "push", "origin", "main", cwd=self.author)

        self.repository = "example/repo"
        self.issue = closeout.ClosingIssue(number=38, state="CLOSED")
        self.pr = closeout.PREvidence(
            number=38,
            state="MERGED",
            merged_at="2026-09-18T00:00:00Z",
            base_ref="main",
            head_ref="issue-38-topic",
            head_sha=self.pr_head,
            merge_sha=self.merge_sha,
            is_cross_repository=False,
            closing_issues=(self.issue,),
        )
        self.workflows = (
            closeout.WorkflowEvidence(
                name="project-ci",
                event="push",
                status="completed",
                conclusion="success",
                head_sha=self.merge_sha,
            ),
            closeout.WorkflowEvidence(
                name="policy-check",
                event="push",
                status="completed",
                conclusion="success",
                head_sha=self.merge_sha,
            ),
        )

    def configure(self, repo: Path) -> None:
        run("git", "config", "user.name", "Closeout Test", cwd=repo)
        run("git", "config", "user.email", "closeout@example.invalid", cwd=repo)

    def head(self, repo: Path) -> str:
        return run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()

    def pr_reader(self, evidence: closeout.PREvidence | None = None):
        value = evidence or self.pr
        return lambda pr, repository: value

    def workflow_reader(
        self, workflows: tuple[closeout.WorkflowEvidence, ...] | None = None
    ):
        value = self.workflows if workflows is None else workflows
        return lambda merge_sha, repository: value

    def verifier(self, ok: bool = True):
        def _verify(repo: Path, branch: str, remote: str):
            return closeout.VerifierResult(
                ok=ok,
                output="LOCAL CLOSEOUT: PASS\n" if ok else "LOCAL CLOSEOUT: FAIL\n",
            )

        return _verify

    def identity_reader(self, repository: str | None = None):
        value = repository or self.repository
        return lambda repo, remote: (value, None)

    def execute(
        self,
        *,
        evidence: closeout.PREvidence | None = None,
        workflows: tuple[closeout.WorkflowEvidence, ...] | None = None,
        verifier_ok: bool = True,
        identity: str | None = None,
    ) -> tuple[closeout.CloseoutResult, list[str]]:
        output: list[str] = []
        result = closeout.run_closeout(
            self.repo,
            38,
            self.repository,
            pr_reader=self.pr_reader(evidence),
            workflow_reader=self.workflow_reader(workflows),
            verifier=self.verifier(verifier_ok),
            identity_reader=self.identity_reader(identity),
            emit=output.append,
        )
        return result, output

    def test_cli_requires_pr_and_repository_but_accepts_no_sha_inputs(self) -> None:
        parser = closeout.build_parser()
        options = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertIn("--pr", options)
        self.assertIn("--repository", options)
        self.assertNotIn("--expected-pr-head", options)
        self.assertNotIn("--merge-commit", options)
        self.assertNotIn("--merge-sha", options)

    def test_merged_happy_path_derives_shas_and_fast_forwards_main(self) -> None:
        result, output = self.execute()

        self.assertTrue(result.ok, result.failures)
        self.assertEqual(self.head(self.repo), self.merge_sha)
        joined = "\n".join(output)
        self.assertIn(f"pr_head={self.pr_head}", joined)
        self.assertIn(f"merge_commit={self.merge_sha}", joined)
        self.assertIn("merge_push_ci=PASS", joined)
        self.assertIn("closing_issues=PASS", joined)
        self.assertIn("POST-MERGE CLOSEOUT: PASS", joined)

    def test_repository_identity_mismatch_fails_before_github_pr_read(self) -> None:
        calls = {"pr": 0}

        def reader(pr: int, repository: str):
            calls["pr"] += 1
            return self.pr

        output: list[str] = []
        result = closeout.run_closeout(
            self.repo,
            38,
            self.repository,
            pr_reader=reader,
            workflow_reader=self.workflow_reader(),
            verifier=self.verifier(),
            identity_reader=self.identity_reader("someone/else"),
            emit=output.append,
        )

        self.assertFalse(result.ok)
        self.assertEqual(calls["pr"], 0)
        self.assertEqual(self.head(self.repo), self.initial_head)
        self.assertIn("repository identity", " ".join(result.failures))

    def test_unmerged_wrong_base_and_cross_repository_fail_before_sync(self) -> None:
        variants = (
            closeout.PREvidence(**{**self.pr.__dict__, "state": "OPEN", "merged_at": None}),
            closeout.PREvidence(**{**self.pr.__dict__, "base_ref": "develop"}),
            closeout.PREvidence(**{**self.pr.__dict__, "is_cross_repository": True}),
        )

        for evidence in variants:
            with self.subTest(evidence=evidence):
                result, _ = self.execute(evidence=evidence)
                self.assertFalse(result.ok)
                self.assertEqual(self.head(self.repo), self.initial_head)

    def test_malformed_or_placeholder_like_merge_sha_fails_before_sync(self) -> None:
        for value in ("", "abc123", "<PR merge commit SHA>", "g" * 40):
            with self.subTest(value=value):
                evidence = closeout.PREvidence(**{**self.pr.__dict__, "merge_sha": value})
                result, _ = self.execute(evidence=evidence)
                self.assertFalse(result.ok)
                self.assertEqual(self.head(self.repo), self.initial_head)
                self.assertIn("merge commit SHA", " ".join(result.failures))

    def test_open_closing_issue_blocks_before_sync(self) -> None:
        evidence = closeout.PREvidence(
            **{
                **self.pr.__dict__,
                "closing_issues": (closeout.ClosingIssue(number=38, state="OPEN"),),
            }
        )

        result, _ = self.execute(evidence=evidence)

        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.initial_head)
        self.assertIn("closing issue", " ".join(result.failures).lower())

    def test_merge_push_ci_missing_pending_failed_or_wrong_sha_blocks(self) -> None:
        cases = (
            tuple(run for run in self.workflows if run.name != "policy-check"),
            (
                self.workflows[0],
                closeout.WorkflowEvidence(
                    name="policy-check",
                    event="push",
                    status="in_progress",
                    conclusion=None,
                    head_sha=self.merge_sha,
                ),
            ),
            (
                self.workflows[0],
                closeout.WorkflowEvidence(
                    name="policy-check",
                    event="push",
                    status="completed",
                    conclusion="failure",
                    head_sha=self.merge_sha,
                ),
            ),
            (
                self.workflows[0],
                closeout.WorkflowEvidence(
                    name="policy-check",
                    event="push",
                    status="completed",
                    conclusion="success",
                    head_sha="0" * 40,
                ),
            ),
        )

        for workflows in cases:
            with self.subTest(workflows=workflows):
                result, _ = self.execute(workflows=workflows)
                self.assertFalse(result.ok)
                self.assertEqual(self.head(self.repo), self.initial_head)
                self.assertIn("workflow", " ".join(result.failures).lower())

    def test_duplicate_exact_workflow_evidence_is_ambiguous_and_blocks(self) -> None:
        duplicated = self.workflows + (
            closeout.WorkflowEvidence(
                name="project-ci",
                event="push",
                status="completed",
                conclusion="success",
                head_sha=self.merge_sha,
            ),
        )

        result, _ = self.execute(workflows=duplicated)

        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.initial_head)
        self.assertIn("ambiguous duplicate", " ".join(result.failures).lower())

    def test_remote_without_authoritative_merge_commit_is_rejected(self) -> None:
        other = self.temp / "unrelated"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        self.configure(other)
        run("git", "switch", "--orphan", "unrelated-root", cwd=other)
        run("git", "rm", "-rf", "--ignore-unmatch", ".", cwd=other)
        (other / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
        run("git", "add", "unrelated.txt", cwd=other)
        run("git", "commit", "-m", "unrelated", cwd=other)
        unrelated_sha = self.head(other)
        run("git", "fetch", str(other), "unrelated-root", cwd=self.repo)

        evidence = closeout.PREvidence(**{**self.pr.__dict__, "merge_sha": unrelated_sha})
        workflows = tuple(
            closeout.WorkflowEvidence(
                name=item.name,
                event=item.event,
                status=item.status,
                conclusion=item.conclusion,
                head_sha=unrelated_sha,
            )
            for item in self.workflows
        )

        result, _ = self.execute(evidence=evidence, workflows=workflows)

        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.initial_head)
        self.assertIn("not contained", " ".join(result.failures))

    def test_dirty_and_in_progress_canonical_worktree_block_before_fast_forward(self) -> None:
        (self.repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        result, _ = self.execute()
        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.initial_head)

        (self.repo / "dirty.txt").unlink()
        git_dir = Path(run("git", "rev-parse", "--git-dir", cwd=self.repo).stdout.strip())
        if not git_dir.is_absolute():
            git_dir = self.repo / git_dir
        (git_dir / "CHERRY_PICK_HEAD").write_text(self.initial_head + "\n", encoding="utf-8")
        result, _ = self.execute()
        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.initial_head)

    def test_diverged_canonical_history_fails_without_reset_or_rebase(self) -> None:
        (self.repo / "local.txt").write_text("local\n", encoding="utf-8")
        run("git", "add", "local.txt", cwd=self.repo)
        run("git", "commit", "-m", "local divergence", cwd=self.repo)
        divergent = self.head(self.repo)

        result, output = self.execute()

        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), divergent)
        text = "\n".join(output).lower()
        self.assertNotIn("reset --hard", text)
        self.assertNotIn("rebase", text)
        self.assertNotIn("stash", text)

    def test_existing_local_verifier_failure_propagates(self) -> None:
        result, output = self.execute(verifier_ok=False)

        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.merge_sha)
        self.assertIn("local closeout verifier", " ".join(result.failures).lower())
        self.assertIn("LOCAL CLOSEOUT: FAIL", "\n".join(output))

    def test_clean_target_worktree_is_reported_and_retained(self) -> None:
        run("git", "fetch", "origin", "issue-38-topic", cwd=self.repo)
        target = self.temp / "topic-worktree"
        run(
            "git",
            "worktree",
            "add",
            "-b",
            "issue-38-topic",
            str(target),
            "origin/issue-38-topic",
            cwd=self.repo,
        )

        result, output = self.execute()

        self.assertTrue(result.ok, result.failures)
        self.assertTrue(target.exists())
        joined = "\n".join(output)
        self.assertIn("target_worktree_count=1", joined)
        self.assertIn("target_worktree_state=clean", joined)

    def test_dirty_target_worktree_blocks_but_is_never_removed(self) -> None:
        run("git", "fetch", "origin", "issue-38-topic", cwd=self.repo)
        target = self.temp / "topic-worktree"
        run(
            "git",
            "worktree",
            "add",
            "-b",
            "issue-38-topic",
            str(target),
            "origin/issue-38-topic",
            cwd=self.repo,
        )
        (target / "untracked.txt").write_text("preserve me\n", encoding="utf-8")

        result, output = self.execute()

        self.assertFalse(result.ok)
        self.assertTrue(target.exists())
        self.assertTrue((target / "untracked.txt").exists())
        self.assertIn("target worktree", " ".join(result.failures).lower())
        self.assertNotIn("worktree remove", "\n".join(output).lower())

    def test_native_exit_code_is_authoritative_even_with_stderr_style_output(self) -> None:
        emitted: list[str] = []

        def success_runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="From https://github.com/example/repo\n",
            )

        success = closeout.invoke_native(
            ("git", "fetch", "origin"),
            cwd=self.repo,
            emit=emitted.append,
            runner=success_runner,
        )
        self.assertTrue(success.ok)
        self.assertIn("From https://github.com/example/repo", "\n".join(emitted))

        def fail_runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args,
                returncode=128,
                stdout="fatal: Not a valid object name <placeholder>\n",
            )

        failure = closeout.invoke_native(
            ("git", "merge-base", "--is-ancestor", "bad", "origin/main"),
            cwd=self.repo,
            emit=emitted.append,
            runner=fail_runner,
        )
        self.assertFalse(failure.ok)
        self.assertEqual(failure.exit_code, 128)

    def _real_closing_issue_reference(
        self,
        *,
        number: int = 38,
        owner: str = "example",
        name: str = "repo",
    ) -> dict[str, object]:
        return {
            "id": f"I_{number}",
            "number": number,
            "url": f"https://github.com/{owner}/{name}/issues/{number}",
            "repository": {
                "id": "R_123",
                "name": name,
                "owner": {
                    "id": "U_123",
                    "login": owner,
                },
            },
        }

    def _real_pr_json(
        self,
        *,
        closing_issues: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "number": 38,
            "state": "MERGED",
            "mergedAt": "2026-09-18T00:00:00Z",
            "baseRefName": "main",
            "headRefName": "issue-38-topic",
            "headRefOid": self.pr_head,
            "isCrossRepository": False,
            "mergeCommit": {"oid": self.merge_sha},
            "closingIssuesReferences": (
                [self._real_closing_issue_reference()]
                if closing_issues is None
                else closing_issues
            ),
        }

    def test_github_pr_reader_uses_real_closing_issue_reference_shape_and_separate_state_lookup(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_gh(args):
            calls.append(tuple(args))
            if args[0:2] == ("pr", "view"):
                return self._real_pr_json()
            if args[0:2] == ("issue", "view"):
                return {"number": 38, "state": "CLOSED"}
            raise AssertionError(args)

        with patch.object(closeout, "_gh_json", side_effect=fake_gh):
            evidence = closeout.read_github_pr(38, self.repository)

        self.assertEqual(evidence.head_sha, self.pr_head)
        self.assertEqual(evidence.merge_sha, self.merge_sha)
        self.assertEqual(
            evidence.closing_issues,
            (closeout.ClosingIssue(38, "CLOSED", "example/repo"),),
        )

        pr_args = calls[0]
        issue_args = calls[1]
        self.assertEqual(pr_args[0:2], ("pr", "view"))
        self.assertIn("closingIssuesReferences", " ".join(pr_args))
        self.assertEqual(issue_args[0:3], ("issue", "view", "38"))
        self.assertIn("-R", issue_args)
        self.assertEqual(issue_args[issue_args.index("-R") + 1], "example/repo")
        self.assertEqual(issue_args[-2:], ("--json", "number,state"))

    def test_github_pr_reader_checks_cross_repository_closing_issue_in_reported_repository(self) -> None:
        calls: list[tuple[str, ...]] = []
        ref = self._real_closing_issue_reference(
            number=77,
            owner="other-owner",
            name="other-repo",
        )

        def fake_gh(args):
            calls.append(tuple(args))
            if args[0:2] == ("pr", "view"):
                return self._real_pr_json(closing_issues=[ref])
            if args[0:2] == ("issue", "view"):
                return {"number": 77, "state": "CLOSED"}
            raise AssertionError(args)

        with patch.object(closeout, "_gh_json", side_effect=fake_gh):
            evidence = closeout.read_github_pr(38, self.repository)

        self.assertEqual(
            evidence.closing_issues,
            (closeout.ClosingIssue(77, "CLOSED", "other-owner/other-repo"),),
        )
        issue_args = calls[1]
        self.assertEqual(issue_args[issue_args.index("-R") + 1], "other-owner/other-repo")

    def test_github_pr_reader_rejects_malformed_closing_issue_repository_identity(self) -> None:
        malformed = self._real_closing_issue_reference()
        malformed["repository"] = {"name": "repo", "owner": {"login": ""}}

        with patch.object(
            closeout,
            "_gh_json",
            return_value=self._real_pr_json(closing_issues=[malformed]),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "closing-Issue reference",
            ):
                closeout.read_github_pr(38, self.repository)

    def test_github_pr_reader_rejects_issue_number_mismatch_or_missing_state(self) -> None:
        for issue_json in (
            {"number": 39, "state": "CLOSED"},
            {"number": 38},
            {"number": 38, "state": ""},
        ):
            with self.subTest(issue_json=issue_json):
                replies = iter((self._real_pr_json(), issue_json))
                with patch.object(closeout, "_gh_json", side_effect=lambda args: next(replies)):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "closing-Issue state evidence",
                    ):
                        closeout.read_github_pr(38, self.repository)

    def test_github_pr_reader_issue_lookup_unavailable_fails_closed(self) -> None:
        calls = 0

        def fake_gh(args):
            nonlocal calls
            calls += 1
            if calls == 1:
                return self._real_pr_json()
            raise RuntimeError("authenticated GitHub evidence is unavailable")

        with patch.object(closeout, "_gh_json", side_effect=fake_gh):
            with self.assertRaisesRegex(
                RuntimeError,
                "authenticated GitHub evidence is unavailable",
            ):
                closeout.read_github_pr(38, self.repository)

    def test_github_pr_reader_open_closing_issue_is_preserved_for_policy_validation(self) -> None:
        replies = iter(
            (
                self._real_pr_json(),
                {"number": 38, "state": "OPEN"},
            )
        )
        with patch.object(closeout, "_gh_json", side_effect=lambda args: next(replies)):
            evidence = closeout.read_github_pr(38, self.repository)

        self.assertEqual(
            evidence.closing_issues,
            (closeout.ClosingIssue(38, "OPEN", "example/repo"),),
        )
        self.assertIn(
            "closing issue",
            " ".join(closeout._validate_closing_issues(evidence)).lower(),
        )

    def test_workflow_reader_filters_exact_merge_commit_push_runs(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_gh(args):
            calls.append(tuple(args))
            return [
                {
                    "name": "project-ci",
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": self.merge_sha,
                }
            ]

        with patch.object(closeout, "_gh_json", side_effect=fake_gh):
            runs = closeout.read_merge_workflows(self.merge_sha, self.repository)

        self.assertEqual(runs[0].head_sha, self.merge_sha)
        args = calls[0]
        self.assertIn("--commit", args)
        self.assertEqual(args[args.index("--commit") + 1], self.merge_sha)
        self.assertIn("--event", args)
        self.assertEqual(args[args.index("--event") + 1], "push")

    def test_native_diagnostics_redact_https_remote_userinfo(self) -> None:
        emitted: list[str] = []

        def runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="From https://secret-token@github.com/example/repo\n",
            )

        result = closeout.invoke_native(
            ("git", "fetch", "origin"),
            cwd=self.repo,
            emit=emitted.append,
            runner=runner,
        )

        self.assertTrue(result.ok)
        joined = "\n".join(emitted)
        self.assertNotIn("secret-token", joined)
        self.assertIn("https://***@github.com/example/repo", joined)

    def test_success_revalidates_closing_issues_after_local_sync(self) -> None:
        reopened = closeout.PREvidence(
            **{
                **self.pr.__dict__,
                "closing_issues": (
                    closeout.ClosingIssue(
                        number=38,
                        state="OPEN",
                        repository="example/repo",
                    ),
                ),
            }
        )
        evidence = iter((self.pr, reopened))

        result = closeout.run_closeout(
            self.repo,
            38,
            self.repository,
            pr_reader=lambda pr, repository: next(evidence),
            workflow_reader=self.workflow_reader(),
            verifier=self.verifier(),
            identity_reader=self.identity_reader(),
            emit=lambda line: None,
        )

        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.merge_sha)
        self.assertIn("closing issue", " ".join(result.failures).lower())

    def test_success_revalidates_merge_push_ci_after_local_sync(self) -> None:
        failed = (
            self.workflows[0],
            closeout.WorkflowEvidence(
                name="policy-check",
                event="push",
                status="completed",
                conclusion="failure",
                head_sha=self.merge_sha,
            ),
        )
        workflow_sets = iter((self.workflows, failed))

        result = closeout.run_closeout(
            self.repo,
            38,
            self.repository,
            pr_reader=self.pr_reader(),
            workflow_reader=lambda merge_sha, repository: next(workflow_sets),
            verifier=self.verifier(),
            identity_reader=self.identity_reader(),
            emit=lambda line: None,
        )

        self.assertFalse(result.ok)
        self.assertEqual(self.head(self.repo), self.merge_sha)
        self.assertIn("workflow", " ".join(result.failures).lower())

    def test_source_does_not_import_or_invoke_destructive_cleanup(self) -> None:
        source = (ROOT / "scripts/post_merge_closeout.py").read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertNotIn("import post_merge_cleanup", lowered)
        self.assertNotIn("worktree remove", lowered)
        self.assertNotIn("reset --hard", lowered)
        self.assertNotIn("branch -d", lowered)
        self.assertNotIn("branch -d", lowered)
        self.assertNotIn("--delete-remote", lowered)


if __name__ == "__main__":
    unittest.main()
