import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeployScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="panel-deploy-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Deploy Test")
        self.run_git("config", "user.email", "deploy@example.invalid")
        (self.repo / "version.txt").write_text("old\n")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "old")
        self.old_revision = self.run_git("rev-parse", "HEAD")
        (self.repo / "version.txt").write_text("new\n")
        self.run_git("commit", "-qam", "new")
        self.new_revision = self.run_git("rev-parse", "HEAD")
        self.state = self.base / "state"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.log = self.base / "commands.log"
        self.write_shim("systemctl", 'printf "systemctl %s\\n" "$*" >> "$DEPLOY_TEST_LOG"\n')
        self.write_shim("curl", 'printf "curl %s\\n" "$*" >> "$DEPLOY_TEST_LOG"\nexit "${CURL_EXIT:-0}"\n')
        self.env = os.environ.copy()
        self.env.update({
            "LINKO_DEPLOY_ROOT": str(self.repo),
            "LINKO_DEPLOY_STATE_DIR": str(self.state),
            "SYSTEMCTL": str(self.bin / "systemctl"),
            "CURL": str(self.bin / "curl"),
            "DEPLOY_TEST_LOG": str(self.log),
        })

    def run_git(self, *args):
        result = subprocess.run(["git", *args], cwd=getattr(self, "repo", None),
                                check=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()

    def write_shim(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)

    def run_script(self, name, *, expected=0):
        result = subprocess.run([str(ROOT / "scripts" / name)], cwd=ROOT,
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_deploy_configuration_has_required_command_arrays(self):
        config = json.loads((ROOT / ".linko-deploy.json").read_text())
        for key in ("deploy_command", "backup_command", "health_command", "rollback_command"):
            self.assertIsInstance(config[key], list)
            self.assertTrue(all(isinstance(value, str) for value in config[key]))
            self.assertTrue((ROOT / config[key][0]).is_file())

    def test_backup_deploy_health_and_rollback_use_disposable_state(self):
        self.run_script("backup.sh")
        self.assertEqual((self.state / "rollback-revision").read_text().strip(), self.old_revision)

        self.run_script("deploy.sh")
        self.assertEqual((self.state / "deployed-revision").read_text().strip(), self.new_revision)
        self.assertEqual(self.log.read_text().strip(), "systemctl --user restart linko-dev-panel.service")

        self.run_script("health.sh")
        self.assertIn("curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8765/", self.log.read_text())

        self.run_script("rollback.sh")
        self.assertEqual(self.run_git("rev-parse", "HEAD"), self.old_revision)
        self.assertEqual((self.state / "deployed-revision").read_text().strip(), self.old_revision)
        self.assertEqual(self.log.read_text().count("systemctl --user restart"), 2)

    def test_health_failure_propagates(self):
        self.env["CURL_EXIT"] = "22"
        self.run_script("health.sh", expected=22)

    def test_rollback_without_backup_fails_without_touching_repository(self):
        self.run_script("rollback.sh", expected=1)
        self.assertEqual(self.run_git("rev-parse", "HEAD"), self.new_revision)


if __name__ == "__main__":
    unittest.main()
