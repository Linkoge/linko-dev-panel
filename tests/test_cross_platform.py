"""Portable configuration, URLs, native subprocesses, and catalogue locking."""
import base64
import builtins
import errno
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
import catalogue_backend as catalogue
import catalogue_compat
import screenshots
import server
from repository import GitError, Project, configuration_path, load_projects, preview_url, web_path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "linko"


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "Linko space ქართული"
        shutil.copytree(FIXTURE, self.repo)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "products.html").write_text("preview", encoding="utf-8")
        self.config = self.root / "projects.json"
        clean_env = patch.dict(os.environ)
        clean_env.start()
        self.addCleanup(clean_env.stop)
        for key in ("LINKO_REPO_PATH", "LINKO_PANEL_CONFIG", "LINKO_PANEL_PORT"):
            os.environ.pop(key, None)

    def configure(self, path=None, **settings):
        value = {"path": str(self.repo) if path is None else path,
                 "preview": "products.html", "catalogue": True, **settings}
        self.config.write_text(json.dumps({"projects": {"Linko": value}}), encoding="utf-8-sig")
        return load_projects(self.config)["Linko"]

    def test_relative_configuration_is_independent_of_launch_directory(self):
        project = self.configure(self.repo.name)
        self.assertEqual(self.repo.resolve(), project.path)
        self.assertTrue(catalogue.enabled(project))
        self.assertEqual("/site/Linko/preview/products.html", preview_url(project.name, project.preview))

    def test_environment_override_drives_git_catalogue_and_images(self):
        os.environ["LINKO_REPO_PATH"] = str(self.repo)
        project = self.configure("missing-old-machine-checkout")
        self.assertEqual(self.repo.resolve(), project.path)
        self.assertTrue(catalogue.enabled(project))
        self.assertEqual(self.repo.resolve(), Path(project.run("rev-parse", "--show-toplevel").strip()).resolve())
        model = catalogue.engine(project.path)
        model.generate()
        snapshot = catalogue.snapshot(project)
        (self.repo / "assets/product-images/manual folder").mkdir()
        image = self.repo / "assets/product-images/manual folder/new # photo.svg"
        image.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        # URL-special characters in filenames are encoded, not treated as URL syntax.
        picked = next(item for item in catalogue.images(project) if item["name"] == image.name)
        self.assertEqual("assets/product-images/manual folder/new # photo.svg", picked["path"])
        self.assertIn("manual%20folder/new%20%23%20photo.svg", picked["url"])
        self.assertEqual("/site/Linko/preview/products.html", snapshot["previewUrl"])

    def test_config_file_selection(self):
        self.assertEqual(self.config, configuration_path(self.root))
        local = self.root / "projects.local.json"
        local.write_text("{}", encoding="utf-8")
        self.assertEqual(local, configuration_path(self.root))
        os.environ["LINKO_PANEL_CONFIG"] = str(self.config)
        self.assertEqual(self.config, configuration_path(self.root))

    def test_invalid_directory_and_expected_layout_errors(self):
        for path, message in ((str(self.root / "missing"), "directory does not exist"),
                              (str(self.repo / "catalogue.py"), "not a directory"),
                              ("", "set a repository path")):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, message):
                self.configure(path)
        (self.repo / "catalogue.py").unlink()
        with self.assertRaisesRegex(ValueError, "expected a Linko catalogue repository; missing catalogue.py"):
            self.configure()

    def test_git_tree_validation_and_missing_git_errors(self):
        plain = self.root / "plain"
        plain.mkdir()
        (plain / "products.html").write_text("page", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot identify.*Git working tree"):
            self.configure(str(plain), catalogue=False)
        nested = self.repo / "nested"
        nested.mkdir()
        (nested / "products.html").write_text("page", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Git repository root"):
            self.configure(str(nested), catalogue=False)
        with patch("repository.subprocess.run", side_effect=FileNotFoundError), self.assertRaisesRegex(ValueError, "Install Git.*PATH"):
            self.configure()

    def test_bad_json_and_startup_errors_have_no_traceback(self):
        self.config.write_text("{broken", encoding="utf-8")
        os.environ["LINKO_PANEL_CONFIG"] = str(self.config)
        error = io.StringIO()
        with redirect_stderr(error), patch.object(server, "ThreadingHTTPServer") as http:
            self.assertEqual(1, server.main())
            http.assert_not_called()
        self.assertIn("Unable to read project configuration", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
        os.environ["LINKO_PANEL_PORT"] = "not-a-port"
        with redirect_stderr(io.StringIO()):
            self.assertEqual(1, server.main())


class PathAndExecutionTests(unittest.TestCase):
    def test_windows_path_stays_native_and_git_uses_no_shell(self):
        path = PureWindowsPath(r"C:\Users\Developer\Linko space ქართული")
        project = Project("Linko", path, "origin", "products.html")
        with patch("repository.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="ok")) as run:
            self.assertEqual("ok", project.run("commit", "-m", "literal & | $(text)"))
            self.assertEqual(["git", "commit", "-m", "literal & | $(text)"], run.call_args.args[0])
            self.assertEqual(path, run.call_args.kwargs["cwd"])
            self.assertIs(False, run.call_args.kwargs["shell"])
            self.assertEqual("0", run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"])
        with patch("repository.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=b"html")) as run:
            self.assertEqual(b"html", project.blob("abc1234", "assets/photo.webp"))
            self.assertEqual(["git", "show", "abc1234:assets/photo.webp"], run.call_args.args[0])
            self.assertEqual(path, run.call_args.kwargs["cwd"])
            self.assertIs(False, run.call_args.kwargs["shell"])
        with patch("repository.subprocess.run", side_effect=FileNotFoundError), self.assertRaisesRegex(GitError, "Install Git"):
            project.run("status")

    def test_windows_relative_paths_generate_encoded_browser_urls(self):
        relative = PureWindowsPath(r"assets\products\star link\photo #1.webp")
        self.assertEqual("/site/My%20Project/preview/assets/products/star%20link/photo%20%231.webp",
                         preview_url("My Project", relative))
        self.assertNotIn("\\", preview_url("Linko", relative, "abc1234"))
        self.assertEqual("/versions/Linko/abc1234/preview/products.html",
                         preview_url("Linko", PureWindowsPath("products.html"), "abc1234"))
        for path in (r"C:\Linko\index.html", "C:index.html", "index.html:stream", r"assets\photo.webp",
                     "../secret.html", ".git/config", "assets/./file.html", "/index.html"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                web_path(path)

    def test_windows_browser_discovery_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as temp:
            chrome = Path(temp) / "Google/Chrome/Application/chrome.exe"
            chrome.parent.mkdir(parents=True)
            chrome.touch()
            with patch.dict(os.environ, {"PROGRAMFILES": temp}, clear=True), patch("screenshots.shutil.which", return_value=None):
                self.assertEqual(str(chrome), screenshots.chrome_binary())
                os.environ["LINKO_PANEL_CHROME"] = r"D:\Browser folder\chrome.exe"
                self.assertEqual(os.environ["LINKO_PANEL_CHROME"], screenshots.chrome_binary())
        with patch.dict(os.environ, {"LINKO_PANEL_NODE": r"D:\Node folder\node.exe"}):
            self.assertEqual(r"D:\Node folder\node.exe", screenshots.node_binary())


class CatalogueCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Linko space ქართული"
        shutil.copytree(FIXTURE, self.root)
        self.project = Project("My Linko", self.root, None, "products.html", catalogue=True)

    def test_legacy_windows_import_is_scoped_and_outputs_are_portable(self):
        source = (self.root / "catalogue.py").read_bytes()
        imports = builtins.__import__
        lock = SimpleNamespace(LOCK_EX=2, LOCK_UN=8, flock=unittest.mock.Mock())
        with patch.object(catalogue_compat, "WINDOWS", True), patch.object(catalogue_compat, "_WINDOWS_FCNTL", lock):
            model = catalogue.engine(self.root)
            self.assertEqual("data/catalogue-generated.json", str(model.MANIFEST))
            model.generate()
            self.assertEqual([], model.generate(check=True))
            snapshot = catalogue.snapshot(self.project)
            snapshot["products"]["mounts"]["title"]["ka"] = "განახლება"
            catalogue.save(self.project, snapshot)
            self.assertIn("განახლება", (self.root / "products.html").read_text(encoding="utf-8"))
            self.assertTrue(lock.flock.called)
        self.assertIs(imports, builtins.__import__)
        self.assertEqual(source, (self.root / "catalogue.py").read_bytes())

    def test_windows_manifest_keeps_forward_slashes(self):
        (self.root / "catalogue.py").write_text(
            'from pathlib import PureWindowsPath\nMANIFEST = PureWindowsPath("data/catalogue-generated.json")\n',
            encoding="utf-8")
        self.assertEqual("data/catalogue-generated.json", str(catalogue.engine(self.root).MANIFEST))

    def test_windows_byte_lock_retries_contention_unlocks_and_restores_position(self):
        fake = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=unittest.mock.Mock(
            side_effect=[OSError(errno.EACCES, "busy"), None, None]))
        with (self.root / ".catalogue.lock").open("a+b") as stream:
            stream.write(b"lock")
            stream.flush()
            position = stream.tell()
            with patch.dict(sys.modules, {"msvcrt": fake}), patch("catalogue_compat.time.sleep") as sleep:
                catalogue_compat.windows_flock(stream, catalogue_compat.LOCK_EX)
                self.assertEqual(position, stream.tell())
                catalogue_compat.windows_flock(stream, catalogue_compat.LOCK_UN)
                self.assertEqual(position, stream.tell())
                sleep.assert_called_once_with(0.1)
                self.assertEqual([(stream.fileno(), 2, 1), (stream.fileno(), 2, 1), (stream.fileno(), 0, 1)],
                                 [call.args for call in fake.locking.call_args_list])
                fake.locking.side_effect = OSError(errno.EBADF, "bad descriptor")
                with self.assertRaises(OSError):
                    catalogue_compat.windows_flock(stream, catalogue_compat.LOCK_EX)

    def test_native_build_lock_excludes_other_processes_and_releases(self):
        code = ("import sys; from pathlib import Path; from catalogue_backend import engine; "
                "model=engine(Path(sys.argv[1])); print('ready',flush=True)\n"
                "with model.build_lock(): print('acquired',flush=True)\n")
        model = catalogue.engine(self.root)
        with model.build_lock():
            process = subprocess.Popen([sys.executable, "-c", code, str(self.root)],
                                       cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8")
            self.addCleanup(lambda: process.kill() if process.poll() is None else None)
            self.assertEqual("ready", process.stdout.readline().strip())
            with self.assertRaises(subprocess.TimeoutExpired):
                process.communicate(timeout=0.2)
        output, errors = process.communicate(timeout=10)
        self.assertEqual(0, process.returncode, errors)
        self.assertIn("acquired", output)

    def test_manual_images_and_uploads_keep_relative_posix_paths(self):
        manual = self.root / "assets/product-images/manual folder"
        manual.mkdir()
        (manual / "photo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        picked = next(item for item in catalogue.images(self.project) if item["name"] == "photo.svg")
        self.assertEqual("assets/product-images/manual folder/photo.svg", picked["path"])
        self.assertEqual("/site/My%20Linko/preview/assets/product-images/manual%20folder/photo.svg", picked["url"])
        shutil.rmtree(self.root / "assets/product-images")
        data = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(data, format="PNG")
        uploaded = catalogue.upload(self.project, {"name": "CON.png", "data": base64.b64encode(data.getvalue()).decode()})
        self.assertEqual("assets/product-images/image-con.png", uploaded["path"])
        self.assertEqual("/site/My%20Linko/preview/assets/product-images/image-con.png", uploaded["url"])
        self.assertTrue((self.root / uploaded["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
