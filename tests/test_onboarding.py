"""Phase 2 tests: disposable repositories, real Git clones, no remote writes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import server
import terminal_backend
from project_onboarding import CloneManager, ProjectRegistry, projects_directory, repository_url, safe_output
from repository import Project, load_projects
import test_panel
from test_panel import git

REAL_POPEN = subprocess.Popen


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="panel-onboarding-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.remote = self.root / "remote.git"
        git(self.root, "init", "--bare", str(self.remote))
        self.existing = self.projects / "existing"
        git(self.projects, "init", "-b", "main", str(self.existing))
        git(self.existing, "config", "user.name", "Test")
        git(self.existing, "config", "user.email", "test@example.invalid")
        (self.existing / "page.html").write_text("existing\n")
        git(self.existing, "add", ".")
        git(self.existing, "commit", "-m", "initial")
        (self.existing / "page.html").write_text("unsaved change\n")
        (self.existing / "untracked.txt").write_text("do not touch\n")
        self.configured = Project("Existing display name", self.existing, None, "page.html")
        self.registry = ProjectRegistry(self.projects, {self.configured.name: self.configured})
        self.latest = {}
        def refresh():
            self.latest = self.registry.refresh(self.manager.excluded())
            return self.latest
        self.manager = CloneManager(self.registry, refresh)
        self.addCleanup(self.manager.shutdown)
        self.calls = []

    def local_transport(self, command, **kwargs):
        # Replace ONLY the verified remote URL at Git's process boundary. URL
        # validation, clone argv, cwd, actual Git and cleanup remain production code.
        if command[:1] == ["git"] and "clone" in command:
            self.calls.append((command.copy(), kwargs.copy()))
            command = command.copy()
            command[-2] = str(self.remote)
        return REAL_POPEN(command, **kwargs)

    def wait_job(self, job):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = self.manager.status(job["id"])
            if result["state"] in {"complete", "failed"}:
                return result
            time.sleep(.02)
        self.fail("Clone did not finish")

    def clone(self, url):
        with patch("project_onboarding.subprocess.Popen", side_effect=self.local_transport):
            return self.wait_job(self.manager.start(url))

    def test_url_forms_and_invalid_inputs(self):
        for url in ("git@github.com:Linkoge/example-project.git", "https://github.com/Linkoge/example-project.git",
                    "ssh://git@git.example.org:2222/team/example-project.git", "https://git.example.org/team/example-project"):
            with self.subTest(url=url):
                self.assertEqual("example-project", repository_url(url)["name"])
        invalid = (None, "", "example", "file:///tmp/repo", "/tmp/repo", "-u", "ext::touch /tmp/hacked",
                   "https://host/../escape.git", "git@host:team/../../escape.git", "https://host/team/.git",
                   "https://host/team/%2e%2e/repo.git", "https://host/team/repo.git;touch_X", "git@host:team/$(touch_X).git",
                   "https://host/team/`touch_X`.git", "https://host/team/repo.git\nwhoami", "https://user:token@host/team/repo.git",
                   "https://host/repo.git?token=secret", "https://host/repo.git?", "https://host/repo.git#", "git@host:/absolute.git",
                   "ssh://git:secret@host/repo.git", "git@host:team/-repo.git", "https://host/team/repo.git\\other")
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.manager.start(url)
        self.assertEqual([self.existing], list(self.projects.iterdir()))

    def test_discovery_preserves_metadata_and_does_not_modify_existing(self):
        before = git(self.existing, "status", "--porcelain=v1")
        index = (self.existing / ".git/index").read_bytes()
        config = (self.existing / ".git/config").read_bytes()
        for name in ("plain", "fake", "bare.git"):
            (self.projects / name).mkdir()
        (self.projects / "fake/.git").mkdir()
        git(self.projects / "bare.git", "init", "--bare")
        empty = self.projects / "empty"
        git(self.projects, "init", str(empty))
        outside = self.root / "outside"
        git(self.root, "init", str(outside))
        (self.projects / "escape").symlink_to(outside, target_is_directory=True)
        # A valid worktree .git file is discoverable as well as a .git directory.
        worktree = self.projects / "worktree"
        git(self.existing, "worktree", "add", "-b", "worktree", str(worktree))
        for _ in range(2):
            found = self.registry.refresh()
            self.assertEqual({self.configured.name, "empty", "worktree"}, set(found))
            self.assertIs(self.configured, found[self.configured.name])
        self.assertEqual(before, git(self.existing, "status", "--porcelain=v1"))
        self.assertEqual(index, (self.existing / ".git/index").read_bytes())
        self.assertEqual(config, (self.existing / ".git/config").read_bytes())
        self.assertEqual("unsaved change\n", (self.existing / "page.html").read_text())

    def test_config_root_and_names(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"projectsDirectory": "projects", "projects": {}}))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.projects, projects_directory(self.root / "panel", config))
            self.assertEqual({}, load_projects(config))
            config.write_text(json.dumps({"projects": {}}))
            self.assertEqual(self.root, projects_directory(self.root / "panel", config))
            os.environ["LINKO_PROJECTS_DIR"] = str(self.projects)
            self.assertEqual(self.projects, projects_directory(self.root / "panel", config))
        conflict = self.projects / self.configured.name
        git(self.projects, "init", str(conflict))
        found = self.registry.refresh()
        self.assertIs(self.configured, found[self.configured.name])
        self.assertEqual(conflict, found[self.configured.name + " (local)"].path)

    def test_empty_clone_ssh_and_https_and_terminal_mapping(self):
        for scheme, name in (("git@github.com:Linkoge/", "ssh-empty"), ("https://github.com/Linkoge/", "https-empty")):
            url = scheme + name + ".git"
            preview = self.registry.preview(url)
            self.assertEqual("Linkoge/" + name, preview["repository"])
            self.assertEqual(str(self.projects / name), preview["localPath"])
            result = self.clone(url)
            self.assertEqual("complete", result["state"], result)
            p = self.latest[name]
            self.assertEqual([".git"], os.listdir(p.path))
            self.assertTrue(p.status()["empty"])
            self.assertEqual([], p.history(0)["commits"])
            self.assertEqual("", p.diff()["diff"])
            self.assertEqual(p.path, terminal_backend.directory(p))
            self.assertIn(str(p.path), terminal_backend.tmux_args(p))
            self.assertNotIn(url, result["output"])
        command, kwargs = self.calls[0]
        self.assertEqual(["--", "git@github.com:Linkoge/ssh-empty.git", "."], command[-3:])
        self.assertFalse(kwargs["shell"])
        self.assertEqual(self.projects / "ssh-empty", kwargs["cwd"])
        self.assertEqual("0", kwargs["env"]["GIT_TERMINAL_PROMPT"])
        self.assertIn("BatchMode=yes", kwargs["env"]["GIT_SSH_COMMAND"])
        p = self.latest["https-empty"]
        git(p.path, "config", "user.name", "Test")
        git(p.path, "config", "user.email", "test@example.invalid")
        (p.path / "first.txt").write_text("first file\n")
        self.assertTrue(p.review_state())
        p.commit("first commit")
        self.assertFalse(p.status()["empty"])
        self.assertEqual("first commit", p.history(0)["commits"][0]["subject"])

    def test_success_nonempty_and_duplicate_never_modified(self):
        git(self.existing, "push", str(self.remote), "main")
        git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        result = self.clone("https://git.example.org/team/success.git")
        self.assertEqual("complete", result["state"], result)
        p = self.latest["success"]
        self.assertEqual("existing\n", (p.path / "page.html").read_text())
        self.assertEqual("initial", p.history(0)["commits"][0]["subject"])
        self.assertTrue(p.status()["clean"])
        (p.path / "page.html").write_text("unsaved\n")
        before = git(p.path, "status", "--porcelain")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.manager.start("git@host:team/success.git")
        self.assertEqual(before, git(p.path, "status", "--porcelain"))
        self.assertEqual("success", self.registry.preview("git@host:team/success.git")["existingProject"])
        for name in ("file", "plain"):
            path = self.projects / name
            path.write_text("keep") if name == "file" else path.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.manager.start("git@host:team/" + name + ".git")
            self.assertTrue(path.exists())

    def test_failed_clone_cleanup_and_retry(self):
        real_remote = self.remote
        self.remote = self.root / "nonexistent.git"
        result = self.clone("https://host/team/retry.git")
        self.assertEqual("failed", result["state"])
        self.assertIn("Repository unavailable", result["error"])
        self.assertIn("you can retry", result["error"])
        self.assertFalse((self.projects / "retry").exists())
        self.remote = real_remote
        self.assertEqual("complete", self.clone("https://host/team/retry.git")["state"])

    def test_authentication_network_errors_partial_cleanup_and_redaction(self):
        for name, output, expected in (("auth", "Permission denied (publickey).", "authentication"),
                                       ("network", "Could not resolve host: host", "connect")):
            url = "https://host/team/" + name + ".git"
            def fail(command, **kwargs):
                (Path(kwargs["cwd"]) / "partial").write_text("partial data")
                (Path(kwargs["cwd"]) / "outside-link").symlink_to(self.existing, target_is_directory=True)
                return REAL_POPEN(["python3", "-c", "import sys; print(sys.argv[1], file=sys.stderr); sys.exit(1)", output + " " + url], **kwargs)
            with patch("project_onboarding.subprocess.Popen", side_effect=fail):
                result = self.wait_job(self.manager.start(url))
            self.assertIn(expected, result["error"])
            self.assertFalse((self.projects / name).exists())
            self.assertNotIn(url, result["output"])
            self.assertEqual("unsaved change\n", (self.existing / "page.html").read_text())
        self.assertNotIn("SECRET", safe_output("fatal https://token:SECRET@host/private/repo.git", "unused"))

    def test_interrupted_clone_timeout_and_active_discovery(self):
        prepared = threading.Event()
        def slow(command, **kwargs):
            if "clone" not in command:
                return REAL_POPEN(command, **kwargs)
            git(Path(kwargs["cwd"]), "init")
            (Path(kwargs["cwd"]) / "partial").write_text("partial")
            prepared.set()
            return REAL_POPEN(["python3", "-c", "import time; print('Working', flush=True); time.sleep(30)"], **kwargs)
        with patch("project_onboarding.subprocess.Popen", side_effect=slow):
            job = self.manager.start("git@host:team/interrupted.git")
            self.assertTrue(prepared.wait(5))
            self.assertNotIn("interrupted", self.manager.discover())
            with self.assertRaisesRegex(ValueError, "Another"):
                self.manager.start("git@host:team/second.git")
            self.manager.cancel(job["id"])
            result = self.wait_job(job)
            self.assertIn("interrupted", result["error"])
            self.assertFalse((self.projects / "interrupted").exists())
            with patch("project_onboarding.CLONE_TIMEOUT", .1):
                result = self.wait_job(self.manager.start("git@host:team/timeout.git"))
            self.assertIn("timed out", result["error"])
            self.assertFalse((self.projects / "timeout").exists())

    def test_git_startup_failure_permissions_and_shutdown_cleanup(self):
        with patch("project_onboarding.subprocess.Popen", side_effect=FileNotFoundError):
            result = self.wait_job(self.manager.start("git@host:team/missing-git.git"))
        self.assertIn("Git installation", result["error"])
        self.assertFalse((self.projects / "missing-git").exists())
        with patch.object(Path, "mkdir", side_effect=PermissionError), self.assertRaisesRegex(ValueError, "permissions"):
            self.manager.start("git@host:team/no-permission.git")
        def slow(command, **kwargs):
            return REAL_POPEN(["python3", "-c", "import time;time.sleep(30)"], **kwargs)
        with patch("project_onboarding.subprocess.Popen", side_effect=slow):
            job = self.manager.start("git@host:team/shutdown.git")
            self.manager.shutdown()
        self.assertEqual("failed", self.manager.status(job["id"])["state"])
        self.assertFalse((self.projects / "shutdown").exists())

    def test_cleanup_refuses_replaced_directory_and_symlink_escape(self):
        started, finish = threading.Event(), threading.Event()
        def blocked(command, **kwargs):
            started.set()
            finish.wait(5)
            return REAL_POPEN(["python3", "-c", "import sys;sys.exit(1)"], **kwargs)
        with patch("project_onboarding.subprocess.Popen", side_effect=blocked):
            job = self.manager.start("git@host:team/replaced.git")
            self.assertTrue(started.wait(5))
            path = self.projects / "replaced"
            path.rename(self.projects / "original-owned")
            path.mkdir()
            (path / "keep.txt").write_text("preexisting replacement")
            finish.set()
            result = self.wait_job(job)
        self.assertIn("identity changed", result["error"])
        self.assertEqual("preexisting replacement", (path / "keep.txt").read_text())
        (self.projects / "escape").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "inside"):
            self.manager.start("git@host:team/escape.git")


class OnboardingHTTPTests(test_panel.PanelTests):
    # Inherit the existing selector/status/history/Git regression suite with the
    # new registry enabled, rather than duplicating those expectations.
    def setUp(self):
        super().setUp()
        registry = ProjectRegistry(Path(self.temp.name), server.PROJECTS)
        manager = CloneManager(registry, server.refresh_projects)
        p1 = patch.object(server, "PROJECT_REGISTRY", registry)
        p2 = patch.object(server, "CLONES", manager)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)
        self.addCleanup(manager.shutdown)

    def test_onboarding_routes_duplicate_invalid_and_security(self):
        status, preview = self.request("POST", "/api/projects/preview", {"url":"git@host:team/one.git"})
        self.assertEqual(200, status)
        self.assertEqual("One", preview["existingProject"])
        self.assertEqual(409, self.request("POST", "/api/projects/clone", {"url":"git@host:team/one.git"})[0])
        self.assertEqual(400, self.request("POST", "/api/projects/clone", {"url":"https://host/../escape.git"})[0])
        self.assertEqual(400, self.request("GET", "/api/projects/clone-status?id=unknown")[0])
        with patch.object(server, "CSRF_TOKEN", "different-token"):
            handler = server.Handler.__new__(server.Handler)
            handler.headers = {"X-Linko-CSRF":"old-token"}
            response = []
            handler.error = lambda *args: response.append(args)
            self.assertFalse(handler.valid_post_security())
            self.assertEqual(403, response[0][1])

    def test_new_project_discovered_without_restart_and_empty_routes(self):
        path = Path(self.temp.name) / "new-empty"
        git(Path(self.temp.name), "init", str(path))
        status, data = self.request("GET", "/api/projects")
        self.assertEqual(200, status)
        self.assertIn("new-empty", [p["name"] for p in data["projects"]])
        for route in ("status", "history", "diff", "terminal/status"):
            self.assertEqual(200, self.request("GET", "/api/" + route + "?project=new-empty")[0])
        self.assertEqual(path, terminal_backend.directory(server.PROJECTS["new-empty"]))
