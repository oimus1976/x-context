import unittest
from pathlib import Path


class ValidationRunnerContractTests(unittest.TestCase):
    def setUp(self):
        self.script = Path("scripts/Invoke-XContextValidation.ps1").read_text(encoding="utf-8")

    def test_runner_does_not_use_dotnet_getrelativepath_missing_from_windows_powershell_51(self):
        self.assertNotIn("GetRelativePath", self.script)

    def test_runner_uses_explicit_utf8_logging_on_windows_powershell_51(self):
        self.assertNotIn("Tee-Object -FilePath $log -Append", self.script)
        self.assertNotIn("Tee-Object -LiteralPath", self.script)
        self.assertIn("System.Text.UTF8Encoding", self.script)
        self.assertIn("System.IO.File]::WriteAllText", self.script)
        self.assertIn("System.IO.File]::AppendAllText", self.script)
        self.assertIn("Invoke-LoggedNative", self.script)
        self.assertIn('"UTF8_PROBE=" + [char]0x65E5 + [char]0x672C + [char]0x8A9E', self.script)

    def test_runner_preserves_native_exit_code_through_logging_helper(self):
        self.assertIn("return [int]$LASTEXITCODE", self.script)
        for marker in (
            '$fetchExit = Invoke-LoggedNative',
            '$worktreeExit = Invoke-LoggedNative',
            '$testExit = Invoke-LoggedNative',
            '$diffExit = Invoke-LoggedNative',
            '$removeExit = Invoke-LoggedNative',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.script)

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
