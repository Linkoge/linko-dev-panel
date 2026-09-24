"""Capture jobs and bounded on-disk sessions for configured preview pages."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from repository import Project

ROOT = Path(__file__).resolve().parent / "screenshots"
ENGINE = Path(__file__).resolve().parent / "capture.mjs"
LOCK = threading.Lock()
JOBS: dict[str, dict[str, object]] = {}

# Interrupted captures never become the latest session. Recover a prior session
# if the process stopped during the brief rename between old and latest.
for directory in ROOT.glob("*"):
    if not directory.is_dir():
        continue
    old = directory / "old"
    if old.exists() and not (directory / "latest").exists():
        old.rename(directory / "latest")
    else:
        shutil.rmtree(old, ignore_errors=True)
    for orphan in directory.glob("work-*"):
        shutil.rmtree(orphan, ignore_errors=True)


def pages(project: Project) -> tuple[str, ...]:
    return project.capture_pages or ((project.preview,) if project.preview else ())


def project_dir(project: Project) -> Path:
    key = f"{project.name}\0{project.path}".encode("utf-8")
    return ROOT / hashlib.sha256(key).hexdigest()[:16]


def latest(project: Project) -> dict[str, object] | None:
    path = project_dir(project) / "latest" / "session.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def status(project: Project) -> dict[str, object]:
    with LOCK:
        job = dict(JOBS.get(project.name, {}))
    if job.get("running"):
        progress_path = project_dir(project) / str(job["work"]) / "progress.json"
        try:
            job.update(json.loads(progress_path.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    job.pop("work", None)
    return {"job": job or None, "session": latest(project)}


def validate(project: Project, body: dict[str, object]) -> tuple[str, list[str], int, int]:
    page = body.get("page")
    if page not in pages(project):
        raise ValueError("Select a configured screenshot page.")
    devices = body.get("devices")
    if devices not in ("mobile", "desktop", "both"):
        raise ValueError("Select Mobile, Desktop, or Both.")
    overlap = body.get("overlap", 20)
    settle_ms = body.get("settleMs", 1300)
    if type(overlap) is not int or not 0 <= overlap <= 50:
        raise ValueError("Overlap must be from 0 to 50 percent.")
    if type(settle_ms) is not int or not 300 <= settle_ms <= 2500:
        raise ValueError("Settle time must be from 300 to 2500 milliseconds.")
    return str(page), (["mobile", "desktop"] if devices == "both" else [str(devices)]), overlap, settle_ms


def node_binary() -> str | None:
    configured = os.environ.get("LINKO_PANEL_NODE") or shutil.which("node")
    if configured:
        return configured
    candidates = sorted((Path.home() / ".nvm" / "versions" / "node").glob("*/bin/node"))
    return str(candidates[-1]) if candidates else None


def start(project: Project, body: dict[str, object], origin: str) -> None:
    page, devices, overlap, settle_ms = validate(project, body)
    node = node_binary()
    chrome = os.environ.get("LINKO_PANEL_CHROME") or shutil.which("google-chrome") or shutil.which("chromium")
    if not node or not chrome or not (ENGINE.parent / "node_modules" / "playwright").is_dir():
        raise RuntimeError("Screenshot browser is unavailable. Install Node, Playwright (npm ci), and Chromium; configure LINKO_PANEL_NODE or LINKO_PANEL_CHROME if needed.")
    directory = project_dir(project)
    work = f"work-{uuid.uuid4().hex}"
    with LOCK:
        if any(item.get("running") for item in JOBS.values()):
            raise ValueError("A screenshot capture is already running.")
        (directory / work).mkdir(parents=True)
        JOBS[project.name] = {"running": True, "phase": "Starting browser", "work": work}
    config = {"url": f"{origin}/site/{quote(project.name, safe='')}/preview/{quote(page, safe='/')}",
              "origin": origin, "outputDir": str(directory / work), "devices": devices,
              "overlap": overlap, "settleMs": settle_ms, "chromeBinary": chrome}
    threading.Thread(target=_run, args=(project, page, devices, overlap, settle_ms, node, config, work), daemon=True).start()


def _similar(previous: Path, current: Path) -> bool:
    """Skip only almost identical neighboring views; Pillow is optional."""
    try:
        from PIL import Image, ImageChops
        with Image.open(previous) as first, Image.open(current) as second:
            size = (128, 128)
            a = first.convert("RGB").resize(size)
            b = second.convert("RGB").resize(size)
            if a.tobytes() == b.tobytes():
                return True
            diff = ImageChops.difference(a, b).convert("L")
            strong = sum(count for value, count in enumerate(diff.histogram()) if value > 24)
            return strong / (size[0] * size[1]) < 0.001
    except (ImportError, OSError):
        return previous.read_bytes() == current.read_bytes()


def _run(project: Project, page: str, devices: list[str], overlap: int, settle_ms: int,
         node: str, config: dict[str, object], work: str) -> None:
    directory = project_dir(project)
    folder = directory / work
    try:
        result = subprocess.run([node, str(ENGINE)], input=json.dumps(config), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600,
                                cwd=ENGINE.parent, check=False)
        if result.returncode:
            raise RuntimeError((result.stderr or "Browser capture failed.").strip()[-2000:])
        raw = json.loads(result.stdout)
        slug = re.sub(r"[^a-z0-9]+", "-", Path(page).stem.lower()).strip("-")[:50] or "page"
        groups = []
        for group in raw["groups"]:
            device = group["device"]
            kept = []
            previous = None
            for item in group["images"]:
                source = folder / item["file"]
                if previous and item["activeText"] == previous["activeText"] and _similar(folder / previous["file"], source):
                    source.unlink()
                    continue
                filename = f"{slug}-{device}-{len(kept) + 1:02d}.png"
                # Compare with the retained source before renaming the next item.
                source.rename(folder / filename)
                kept.append({"file": filename, "number": len(kept) + 1, "scrollY": item["scrollY"]})
                previous = {**item, "file": filename}
            groups.append({"device": device, "images": kept, "truncated": group["truncated"]})
        session = {"id": work, "project": project.name, "page": page, "createdAt": int(time.time()),
                   "overlap": overlap, "settleMs": settle_ms, "groups": groups}
        (folder / "session.json").write_text(json.dumps(session), encoding="utf-8")
        (folder / "progress.json").unlink(missing_ok=True)
        old = directory / "old"
        shutil.rmtree(old, ignore_errors=True)
        current = directory / "latest"
        if current.exists():
            current.rename(old)
        folder.rename(current)
        shutil.rmtree(old, ignore_errors=True)
        with LOCK:
            JOBS[project.name] = {"running": False, "phase": "Complete"}
    except Exception as exc:
        if not (directory / "latest").exists() and (directory / "old").exists():
            (directory / "old").rename(directory / "latest")
        shutil.rmtree(folder, ignore_errors=True)
        with LOCK:
            JOBS[project.name] = {"running": False, "phase": "Failed", "error": str(exc)}


def clear(project: Project) -> None:
    with LOCK:
        if JOBS.get(project.name, {}).get("running"):
            raise ValueError("Wait for the current capture to finish before clearing screenshots.")
        JOBS.pop(project.name, None)
        shutil.rmtree(project_dir(project), ignore_errors=True)


def image_path(project: Project, filename: str) -> Path | None:
    session = latest(project)
    if not session or not isinstance(filename, str):
        return None
    if not any(image["file"] == filename for group in session["groups"] for image in group["images"]):
        return None
    path = project_dir(project) / "latest" / filename
    return path if path.is_file() else None
