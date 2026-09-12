import tempfile
import unittest
from pathlib import Path

from scripts.validation_workspace import (
    WorkspacePolicy,
    WorkspacePolicyError,
    load_policy,
    validate_canonical_repo,
    validate_disposable_path,
    validate_durable_log_path,
    validate_effective_clean_status,
    validate_final_state,
)


class ValidationWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.policy = WorkspacePolicy(
            canonical_repo=r"C:\Users\oimus\x-context",
            disposable_root=r"C:\Users\oimus\AppData\Local\Temp\x-context",
            worktree_root=r"C:\Users\oimus\AppData\Local\Temp\x-context\worktrees",
            durable_log_dir=r"C:\Users\oimus\x-context\logs\verification",
            final_branch="main",
        )
        self.log = r"C:\Users\oimus\x-context\logs\verification\issue14-test.log"

    def test_policy_loads_and_expands_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "PROJECT_PROFILE.toml"
            profile.write_text(
                """
[validation_workspace]
canonical_repo = "C:\\\\Users\\\\oimus\\\\x-context"
disposable_root = "%TEMP%\\\\x-context"
worktree_root = "%TEMP%\\\\x-context\\\\worktrees"
durable_log_dir = "C:\\\\Users\\\\oimus\\\\x-context\\\\logs\\\\verification"
final_branch = "main"
""".strip(),
                encoding="utf-8",
            )
            policy = load_policy(profile, environ={"TEMP": r"C:\Temp"})
        self.assertEqual(policy.disposable_root, r"C:\Temp\x-context")
        self.assertEqual(policy.worktree_root, r"C:\Temp\x-context\worktrees")

    def test_accepts_dedicated_worktree_path(self):
        validate_disposable_path(
            r"C:\Users\oimus\AppData\Local\Temp\x-context\worktrees\issue14-abc",
            self.policy,
            kind="worktree",
        )

    def test_rejects_temp_root_sibling_worktree_paths(self):
        invalid = (
            r"C:\Users\oimus\AppData\Local\Temp\x-context-issue14",
            r"C:\Users\oimus\AppData\Local\Temp\issue14-abc",
            r"C:\Users\oimus\AppData\Local\Temp\x-context",
        )
        for path in invalid:
            with self.subTest(path=path):
                with self.assertRaises(WorkspacePolicyError):
                    validate_disposable_path(path, self.policy, kind="worktree")

    def test_rejects_disposable_path_outside_project_temp_root(self):
        with self.assertRaises(WorkspacePolicyError):
            validate_disposable_path(
                r"D:\scratch\x-context\issue14",
                self.policy,
                kind="scratch",
            )

    def test_accepts_durable_log_beneath_repo_verification_dir(self):
        validate_durable_log_path(self.log, self.policy)

    def test_rejects_temp_log_as_durable_evidence(self):
        with self.assertRaises(WorkspacePolicyError):
            validate_durable_log_path(
                r"C:\Users\oimus\AppData\Local\Temp\issue14.log",
                self.policy,
            )

    def test_rejects_other_repo_directory_for_durable_log(self):
        with self.assertRaises(WorkspacePolicyError):
            validate_durable_log_path(
                r"C:\Users\oimus\x-context\docs\issue14.log",
                self.policy,
            )

    def test_rejects_wrong_canonical_repo(self):
        with self.assertRaises(WorkspacePolicyError):
            validate_canonical_repo(r"C:\Users\oimus\other", self.policy)

    def test_effective_clean_status_allows_only_current_untracked_log(self):
        validate_effective_clean_status(
            ["?? logs/verification/issue14-test.log"],
            log_path=self.log,
            policy=self.policy,
        )

    def test_effective_clean_status_rejects_any_other_entry(self):
        cases = (
            [" M PROJECT_PROFILE.toml"],
            ["?? random.tmp"],
            ["?? logs/verification/other.log"],
            ["?? logs/verification/issue14-test.log", "?? random.tmp"],
        )
        for status in cases:
            with self.subTest(status=status):
                with self.assertRaises(WorkspacePolicyError):
                    validate_effective_clean_status(
                        status,
                        log_path=self.log,
                        policy=self.policy,
                    )

    def test_final_state_accepts_expected_repo_main_head_log_and_only_log_status(self):
        validate_final_state(
            location=self.policy.canonical_repo,
            branch="main",
            head="abc123",
            origin_main="abc123",
            status_lines=["?? logs/verification/issue14-test.log"],
            log_path=self.log,
            log_exists=True,
            log_size=42,
            policy=self.policy,
        )

    def test_final_state_rejects_location_mismatch(self):
        with self.assertRaises(WorkspacePolicyError):
            validate_final_state(
                location=r"C:\Temp",
                branch="main",
                head="abc123",
                origin_main="abc123",
                status_lines=[],
                log_path=self.log,
                log_exists=True,
                log_size=1,
                policy=self.policy,
            )

    def test_final_state_rejects_branch_mismatch(self):
        with self.assertRaises(WorkspacePolicyError):
            validate_final_state(
                location=self.policy.canonical_repo,
                branch="topic",
                head="abc123",
                origin_main="abc123",
                status_lines=[],
                log_path=self.log,
                log_exists=True,
                log_size=1,
                policy=self.policy,
            )

    def test_final_state_rejects_head_origin_mismatch(self):
        with self.assertRaises(WorkspacePolicyError):
            validate_final_state(
                location=self.policy.canonical_repo,
                branch="main",
                head="abc123",
                origin_main="def456",
                status_lines=[],
                log_path=self.log,
                log_exists=True,
                log_size=1,
                policy=self.policy,
            )

    def test_final_state_rejects_missing_or_empty_log(self):
        cases = ((False, 0), (True, 0))
        for exists, size in cases:
            with self.subTest(exists=exists, size=size):
                with self.assertRaises(WorkspacePolicyError):
                    validate_final_state(
                        location=self.policy.canonical_repo,
                        branch="main",
                        head="abc123",
                        origin_main="abc123",
                        status_lines=[],
                        log_path=self.log,
                        log_exists=exists,
                        log_size=size,
                        policy=self.policy,
                    )


if __name__ == "__main__":
    unittest.main()
