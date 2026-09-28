"""Screenshot configuration, security, and session lifecycle tests."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import screenshots
from repository import Project, load_projects


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = Project("Demo", self.root, None, "home.html", ("home.html", "about.html"))
        self.root_patch = patch.object(screenshots, "ROOT", self.root / "screenshots")
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        screenshots.JOBS.clear()

    def test_targets_and_options_are_restricted(self):
        self.assertEqual(("home.html", ["mobile", "desktop"], 20, 1300),
                         screenshots.validate(self.project, {"page": "home.html", "devices": "both"}))
        for body in (
            {"page": "https://example.com", "devices": "both"},
            {"page": "../private.html", "devices": "both"},
            {"page": "home.html", "devices": "tablet"},
            {"page": "home.html", "devices": "mobile", "overlap": 60},
            {"page": "home.html", "devices": "mobile", "overlap": True},
            {"page": "home.html", "devices": "mobile", "settleMs": 10},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                screenshots.validate(self.project, body)

    def test_capture_pages_are_validated_on_load(self):
        import subprocess
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "home.html").write_text("home")
        (self.root / "about.html").write_text("about")
        config = self.root / "projects.json"
        def configure(pages):
            config.write_text(json.dumps({"projects": {"Demo": {
                "path": str(self.root), "preview": "home.html", "capturePages": pages}}}))
            return load_projects(config)
        self.assertEqual(("home.html", "about.html"), configure(["about.html", "home.html"])["Demo"].capture_pages)
        for value in (["../secret.html"], ["https://example.com"], ["missing.html"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configure(value)

    def test_session_keeps_latest_and_only_serves_manifest_images(self):
        def fake_engine(_command, *, input, **_kwargs):
            config = json.loads(input)
            folder = Path(config["outputDir"])
            (folder / "mobile-raw-001.png").write_bytes(config["url"].encode())
            (folder / "mobile-raw-002.png").write_bytes(b"second")
            return SimpleNamespace(returncode=0, stdout=json.dumps({"groups": [{
                "device": "mobile", "truncated": False, "images": [
                    {"file": "mobile-raw-001.png", "scrollY": 0, "activeText": "one"},
                    {"file": "mobile-raw-002.png", "scrollY": 700, "activeText": "two"}
                ]}]}), stderr="")
        with patch.object(screenshots.subprocess, "run", side_effect=fake_engine):
            for page in ("home.html", "about.html"):
                config = {"outputDir": str(screenshots.page_dir(self.project, page) / "work-first"),
                          "url": f"http://127.0.0.1/site/Demo/preview/{page}"}
                Path(config["outputDir"]).mkdir(parents=True)
                screenshots._run(self.project, page, ["mobile"], 20, 900, "node", config, "work-first")
        session = screenshots.latest(self.project)
        self.assertEqual(["home-mobile-01.png", "home-mobile-02.png"],
                         [image["file"] for image in session["groups"][0]["images"]])
        self.assertEqual("about.html", screenshots.status(self.project, "about.html")["session"]["page"])
        self.assertEqual("home.html", screenshots.status(self.project, "home.html")["session"]["page"])
        self.assertIn(b"about.html", screenshots.image_path(self.project, "about-mobile-01.png", "about.html").read_bytes())
        self.assertIsNotNone(screenshots.image_path(self.project, "home-mobile-01.png", "home.html"))
        self.assertIsNone(screenshots.image_path(self.project, "home-mobile-01.png", "about.html"))
        self.assertIsNone(screenshots.image_path(self.project, "../home-mobile-01.png"))
        self.assertIsNone(screenshots.image_path(self.project, "mobile-raw-001.png"))
        with self.assertRaises(ValueError):
            screenshots.status(self.project, "unconfigured.html")
        screenshots.clear(self.project, "about.html")
        self.assertIsNone(screenshots.latest(self.project, "about.html"))
        self.assertIsNotNone(screenshots.latest(self.project, "home.html"))
        screenshots.clear(self.project)
        self.assertIsNone(screenshots.latest(self.project))

    def test_previous_single_session_remains_available_for_its_page(self):
        legacy = screenshots.project_dir(self.project) / "latest"
        legacy.mkdir(parents=True)
        (legacy / "session.json").write_text(json.dumps({"page": "about.html", "groups": [{
            "images": [{"file": "about-mobile-01.png"}]}]}))
        (legacy / "about-mobile-01.png").write_bytes(b"old screenshot")
        self.assertIsNone(screenshots.latest(self.project, "home.html"))
        self.assertEqual(b"old screenshot", screenshots.image_path(
            self.project, "about-mobile-01.png", "about.html").read_bytes())
        screenshots.clear(self.project, "about.html")
        self.assertIsNone(screenshots.latest(self.project, "about.html"))


if __name__ == "__main__":
    unittest.main()
