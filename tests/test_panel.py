"""Safe integration checks against disposable Git repositories."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from io import BytesIO

import server
from repository import Project, load_projects


def git(path, *args):
    return subprocess.run(["git", *args], cwd=path, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        git(root, "init", "--bare", str(self.remote))
        self.repo = root / "one"
        git(root, "init", "-b", "main", str(self.repo))
        git(self.repo, "config", "user.name", "Test User")
        git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "index.html").write_text("initial\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "initial")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        self.initial = git(self.repo, "rev-parse", "HEAD")
        self.project = Project("One", self.repo, "origin", "index.html")
        self.other = root / "two"
        git(root, "clone", "-b", "main", str(self.remote), str(self.other))
        git(self.other, "config", "user.name", "Test User")
        git(self.other, "config", "user.email", "test@example.invalid")
        self.second = Project("Two", self.other, "origin", None)
        self.old_projects = server.PROJECTS
        server.PROJECTS = {"One": self.project, "Two": self.second}
        self.addCleanup(setattr, server, "PROJECTS", self.old_projects)
    def request(self, method, path, body=None):
        handler = server.Handler.__new__(server.Handler)
        handler.path = path
        handler.headers = {"Host": "127.0.0.1"}
        handler.wfile = BytesIO()
        handler.rfile = BytesIO(json.dumps(body).encode() if body is not None else b"")
        response = {}
        handler.send_response = lambda status: response.update(status=status)
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        if method == "POST":
            handler.headers.update({"Content-Type": "application/json", "X-Linko-CSRF": server.CSRF_TOKEN,
                                    "Content-Length": str(len(handler.rfile.getvalue()))})
            handler.do_POST()
        else:
            handler.do_GET()
        content = handler.wfile.getvalue()
        try:
            return response["status"], json.loads(content)
        except ValueError:
            return response["status"], content

    def test_allowlist_and_preview(self):
        self.assertEqual(200, self.request("GET", "/api/projects")[0])
        self.assertEqual(400, self.request("GET", "/api/status?project=/tmp")[0])
        self.assertEqual(200, self.request("GET", "/site/One/preview/index.html")[0])
        self.assertEqual(200, self.request("GET", f"/versions/One/{self.initial}/preview/index.html")[0])
        self.assertEqual(404, self.request("GET", "/site/Two/preview/index.html")[0])
        self.assertEqual(403, self.request("GET", "/site/One/preview/.git/config")[0])
        self.assertEqual(403, self.request("GET", "/site/One/preview/%2e%2e/secret.html")[0])
        (self.repo / ".secret.html").write_text("secret")
        (self.repo / "public.html").symlink_to(".secret.html")
        self.assertEqual(403, self.request("GET", "/site/One/preview/public.html")[0])
        (self.repo / "public.html").unlink()
        (self.repo / ".secret.html").unlink()
        config = Path(self.temp.name) / "config.json"
        config.write_text(json.dumps({"projects": {"bad": {"path": str(self.repo / 'subdir')}}}))
        (self.repo / "subdir").mkdir()
        with self.assertRaises(ValueError):
            load_projects(config)

    def test_commit_push_pull_and_relationship(self):
        (self.repo / "index.html").write_text("updated\n")
        status, prepared = self.request("POST", "/api/commit/prepare", {"project": "One", "message": "update"})
        self.assertEqual(200, status)
        self.assertEqual(400, self.request("POST", "/api/commit/confirm", {"project": "Two", "confirmation": prepared["confirmation"]})[0])
        status, prepared = self.request("POST", "/api/commit/prepare", {"project": "One", "message": "update"})
        status, result = self.request("POST", "/api/commit/confirm", {"project": "One", "confirmation": prepared["confirmation"]})
        self.assertEqual(200, status, result)
        self.assertEqual(1, result["remote"]["ahead"])
        self.assertEqual(200, self.request("POST", "/api/push", {"project": "One"})[0])
        self.assertEqual(0, self.request("GET", "/api/status?project=One")[1]["remote"]["ahead"])
        git(self.other, "pull", "--ff-only")
        (self.other / "index.html").write_text("remote update\n")
        git(self.other, "add", "-A")
        git(self.other, "commit", "-m", "remote update")
        git(self.other, "push")
        status, pulled = self.request("POST", "/api/pull", {"project": "One"})
        self.assertEqual(200, status, pulled)
        self.assertEqual("remote update\n", (self.repo / "index.html").read_text())
        self.assertEqual(0, pulled["remote"]["behind"])

    def test_restore_review_recovery_and_dirty_guard(self):
        (self.repo / "index.html").write_text("second\n")
        (self.repo / "added.css").write_text("body{}")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "second")
        second = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "untracked.txt").write_text("keep")
        self.assertEqual(400, self.request("POST", "/api/restore/prepare", {"project": "One", "commit": self.initial})[0])
        (self.repo / "untracked.txt").unlink()
        status, prepared = self.request("POST", "/api/restore/prepare", {"project": "One", "commit": self.initial})
        self.assertEqual(200, status, prepared)
        self.assertEqual(second, prepared["current"]["fullHash"])
        self.assertEqual(self.initial, prepared["target"]["fullHash"])
        self.assertTrue(prepared["files"])
        status, restored = self.request("POST", "/api/restore/confirm", {"project": "One", "confirmation": prepared["confirmation"]})
        self.assertEqual(200, status, restored)
        self.assertEqual("initial\n", (self.repo / "index.html").read_text())
        self.assertFalse((self.repo / "added.css").exists())
        self.assertEqual(second, git(self.repo, "rev-parse", "HEAD^"))
        self.assertEqual(self.initial, git(self.repo, "rev-parse", "HEAD~2"))
        self.assertEqual(git(self.repo, "rev-parse", f"{self.initial}^{{tree}}"), git(self.repo, "rev-parse", "HEAD^{tree}"))
        self.assertEqual(200, self.request("GET", f"/api/compare?project=One&commit={second}")[0])
        self.assertEqual(200, self.request("GET", f"/api/history?project=One&offset=0")[0])
        self.assertEqual(200, self.request("POST", "/api/history/view", {"project": "One", "commit": self.initial})[0])
        self.assertEqual("(detached HEAD)", self.request("GET", "/api/status?project=One")[1]["branch"])
        self.assertEqual(400, self.request("POST", "/api/push", {"project": "One"})[0])
        self.assertEqual(200, self.request("POST", "/api/history/return", {"project": "One"})[0])
        self.assertEqual("main", git(self.repo, "branch", "--show-current"))

    def test_changed_content_invalidates_confirmation_and_discard(self):
        (self.repo / "index.html").write_text("draft one\n")
        status, prepared = self.request("POST", "/api/commit/prepare", {"project": "One", "message": "draft"})
        self.assertEqual(200, status)
        (self.repo / "index.html").write_text("draft two\n")
        self.assertEqual(400, self.request("POST", "/api/commit/confirm", {"project": "One", "confirmation": prepared["confirmation"]})[0])
        status, prepared = self.request("POST", "/api/discard/prepare", {"project": "One"})
        self.assertEqual(200, status)
        (self.repo / "index.html").write_text("draft three\n")
        self.assertEqual(400, self.request("POST", "/api/discard/confirm", {"project": "One", "confirmation": prepared["confirmation"]})[0])
        status, prepared = self.request("POST", "/api/discard/prepare", {"project": "One"})
        self.assertEqual(200, status)
        self.assertEqual(200, self.request("POST", "/api/discard/confirm", {"project": "One", "confirmation": prepared["confirmation"]})[0])
        self.assertEqual("initial\n", (self.repo / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
