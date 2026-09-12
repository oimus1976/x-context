import unittest
from pathlib import Path


class ValidationRunnerContractTests(unittest.TestCase):
    def setUp(self):
        self.script = Path("scripts/Invoke-XContextValidation.ps1").read_text(encoding="utf-8")

    def test_runner_does_not_use_dotnet_getrelativepath_missing_from_windows_powershell_51(self):
        self.assertNotIn("GetRelativePath", self.script)

    def test_runner_uses_windows_powershell_51_compatible_tee_object_parameter(self):
        self.assertNotIn("Tee-Object -LiteralPath", self.script)
        self.assertIn("Tee-Object -FilePath", self.script)

    def test_runner_derives_paths_from_profile_guard(self):
        self.assertIn("PROJECT_PROFILE.toml", self.script)
        self.assertIn("validation_workspace.py", self.script)
        self.assertIn("check-disposable --kind worktree", self.script)
        self.assertIn("check-log", self.script)

    def test_runner_never_force_removes_failed_worktree(self):
        self.assertNotIn("worktree remove --force", self.script)
        self.assertNotIn("git reset --hard", self.script)
        self.assertNotIn("git clean", self.script)

    def test_runner_records_final_postconditions(self):
        for marker in (
            "FINAL_LOCATION=",
            "FINAL_BRANCH=",
            "FINAL_HEAD=",
            "FINAL_ORIGIN_MAIN=",
            "FINAL_STATUS_BEGIN",
            "LOG_PATH=",
            "FINAL_RESULT=PASS",
            "FINAL_RESULT=FAIL",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.script)


if __name__ == "__main__":
    unittest.main()
