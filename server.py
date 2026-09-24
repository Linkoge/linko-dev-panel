#!/usr/bin/env python3
"""Private web UI for the explicitly configured Git projects."""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlsplit

from repository import GitError, Project, load_projects, snapshot

PANEL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PANEL_DIR / "projects.json"
PROJECTS = load_projects(CONFIG_PATH)
HOST = os.environ.get("LINKO_PANEL_HOST", "100.65.36.48")
PORT = int(os.environ.get("LINKO_PANEL_PORT", "8765"))
MAX_BODY = 16_384
TOKEN_TTL = 300
PREVIEW_EXTENSIONS = {".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg",
                      ".webp", ".avif", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".otf",
                      ".mp4", ".webm"}
CSRF_TOKEN = secrets.token_urlsafe(32)
OPERATION_LOCK = threading.Lock()
CONFIRMATIONS: dict[str, dict[str, object]] = {}
CONFIRMATIONS_LOCK = threading.Lock()
RETURN_BRANCHES: dict[str, str] = {}


def project_from(value: object) -> Project:
    if not isinstance(value, str) or value not in PROJECTS:
        raise ValueError("Unknown project. Select a configured repository.")
    return PROJECTS[value]


def make_confirmation(kind: str, project: Project, state: str, **details: object) -> str:
    token = secrets.token_urlsafe(24)
    with CONFIRMATIONS_LOCK:
        now = time.time()
        for key, item in list(CONFIRMATIONS.items()):
            if float(item["expires"]) < now:
                CONFIRMATIONS.pop(key, None)
        CONFIRMATIONS[token] = {"kind": kind, "project": project.name,
                                "state": state, "expires": now + TOKEN_TTL, **details}
    return token


def take_confirmation(value: object, kind: str, project: Project) -> dict[str, object]:
    if not isinstance(value, str):
        raise ValueError("Missing confirmation.")
    with CONFIRMATIONS_LOCK:
        item = CONFIRMATIONS.pop(value, None)
    if not item or item.get("kind") != kind or item.get("project") != project.name or float(item["expires"]) < time.time():
        raise ValueError("Confirmation expired or belongs to another project. Review again.")
    return item


class Handler(BaseHTTPRequestHandler):
    server_version = "DevPanel/2.0"

    def allowed_host(self) -> bool:
        try:
            hostname = urlsplit(f"//{self.headers.get('Host', '')}").hostname or ""
        except ValueError:
            return False
        extras = {x.strip() for x in os.environ.get("LINKO_PANEL_ALLOWED_HOSTS", "").split(",") if x.strip()}
        return hostname in {HOST, "127.0.0.1", "localhost", *extras}

    def security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def send_json(self, data: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.security_headers()
        self.end_headers()
        self.wfile.write(body)

    def error(self, message: str, status: int = HTTPStatus.BAD_REQUEST, output: str = "") -> None:
        self.send_json({"ok": False, "error": message, "output": output}, status)

    def read_json(self) -> dict[str, object]:
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise ValueError("Content-Type must be application/json.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request size.") from exc
        if length < 0 or length > MAX_BODY:
            raise ValueError("Request is too large.")
        try:
            value = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON request.") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON request must be an object.")
        return value

    def valid_post_security(self) -> bool:
        if not secrets.compare_digest(self.headers.get("X-Linko-CSRF", ""), CSRF_TOKEN):
            self.error("Invalid security token. Reload the panel.", HTTPStatus.FORBIDDEN)
            return False
        origin = self.headers.get("Origin")
        if origin:
            try:
                parts = urlsplit(origin)
            except ValueError:
                self.error("Invalid request origin.", HTTPStatus.FORBIDDEN)
                return False
            if parts.scheme != "http" or parts.netloc != self.headers.get("Host"):
                self.error("Cross-origin requests are not allowed.", HTTPStatus.FORBIDDEN)
                return False
        return True

    def do_GET(self) -> None:
        if not self.allowed_host():
            self.error("Host is not allowed.", HTTPStatus.FORBIDDEN)
            return
        url = urlsplit(self.path)
        path = url.path
        query = parse_qs(url.query)
        try:
            if path in {"/", "/index.html", "/panel", "/panel/", "/dev-panel", "/dev-panel/"}:
                self.serve_file(PANEL_DIR / "index.html", panel=True)
            elif path == "/api/projects":
                self.send_json({"ok": True, "projects": [{"name": p.name, "previewUrl":
                                f"/site/{quote(p.name, safe='')}/preview/{quote(p.preview, safe='/')}" if p.preview else None}
                                for p in PROJECTS.values()],
                                "csrfToken": CSRF_TOKEN})
            elif path.startswith("/api/"):
                project = project_from(query.get("project", [None])[0])
                if path == "/api/status":
                    self.send_json({"ok": True, **project.status(RETURN_BRANCHES.get(project.name))})
                elif path == "/api/diff":
                    self.send_json({"ok": True, **project.diff()})
                elif path == "/api/history":
                    offset = query.get("offset", ["0"])[0]
                    if not offset.isdigit() or int(offset) > 1_000_000:
                        raise ValueError("Invalid history offset.")
                    self.send_json({"ok": True, **project.history(int(offset), RETURN_BRANCHES.get(project.name))})
                elif path in {"/api/compare", "/api/compare/file"}:
                    commit = project.resolve_commit(query.get("commit", [None])[0])
                    data = project.comparison(commit, RETURN_BRANCHES.get(project.name))
                    if path == "/api/compare":
                        self.send_json({"ok": True, **data})
                    else:
                        index = query.get("index", [""])[0]
                        if not index.isdigit() or int(index) >= len(data["files"]):
                            raise ValueError("Invalid comparison file.")
                        item = data["files"][int(index)]
                        diff = project.run("diff", "--no-ext-diff", "--no-color", commit, str(data["currentRef"]), "--", *item["paths"])
                        self.send_json({"ok": True, "file": item, "diff": diff or "No textual diff is available for this file."})
                else:
                    self.error("Not found.", HTTPStatus.NOT_FOUND)
            elif path.startswith("/site/") or path.startswith("/versions/"):
                self.preview_route(path)
            elif path.startswith("/preview") and "Linko" in PROJECTS and PROJECTS["Linko"].preview:
                # Existing bookmarks retain their entry point.
                self.redirect(f"/site/Linko/preview/{quote(PROJECTS['Linko'].preview, safe='/')}")
            elif path.startswith("/history-preview/") and "Linko" in PROJECTS and PROJECTS["Linko"].preview:
                parts = path.removeprefix("/history-preview/").split("/", 1)
                if len(parts) != 2:
                    raise ValueError("Invalid historical preview path.")
                commit = PROJECTS["Linko"].resolve_commit(parts[0])
                self.redirect(f"/versions/Linko/{commit}/{parts[1]}")
            else:
                self.error("Not found.", HTTPStatus.NOT_FOUND)
        except GitError as exc:
            self.error("Git operation failed.", HTTPStatus.INTERNAL_SERVER_ERROR, exc.output)
        except ValueError as exc:
            self.error(str(exc))
        except OSError as exc:
            self.error("Unable to read the requested file.", HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        if not self.allowed_host():
            self.error("Host is not allowed.", HTTPStatus.FORBIDDEN)
            return
        if not self.valid_post_security():
            return
        try:
            body = self.read_json()
            project = project_from(body.get("project"))
            path = urlsplit(self.path).path
            if path == "/api/commit/prepare":
                self.prepare_commit(project, body)
            elif path == "/api/commit/confirm":
                self.confirm_commit(project, body)
            elif path == "/api/push":
                with OPERATION_LOCK:
                    output = project.push()
                self.send_json({"ok": True, "output": output, **project.status(RETURN_BRANCHES.get(project.name))})
            elif path == "/api/pull":
                with OPERATION_LOCK:
                    output = project.pull()
                self.send_json({"ok": True, "output": output, **project.status(RETURN_BRANCHES.get(project.name))})
            elif path == "/api/discard/prepare":
                self.prepare_discard(project)
            elif path == "/api/discard/confirm":
                self.confirm_discard(project, body)
            elif path == "/api/restore/prepare":
                self.prepare_restore(project, body)
            elif path == "/api/restore/confirm":
                self.confirm_restore(project, body)
            elif path == "/api/history/view":
                self.view_historical(project, body)
            elif path == "/api/history/return":
                self.return_current(project)
            else:
                self.error("Not found.", HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.error(str(exc))
        except GitError as exc:
            self.error("Git operation failed.", HTTPStatus.CONFLICT, exc.output)
        except Exception as exc:
            self.error("Unexpected server error.", HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def prepare_commit(self, project: Project, body: dict[str, object]) -> None:
        project.require_branch()
        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Enter a commit message.")
        message = message.strip()
        if len(message) > 200 or any(ch in message for ch in ("\x00", "\n", "\r")):
            raise ValueError("Use a single-line commit message of at most 200 characters.")
        raw = project.porcelain()
        changes = project.changes(raw)
        if not changes:
            raise ValueError("The working tree is clean; there is nothing to commit.")
        state = project.review_state()
        token = make_confirmation("commit", project, state, message=message)
        self.send_json({"ok": True, "confirmation": token, "message": message, "files": changes, "expiresIn": TOKEN_TTL})

    def confirm_commit(self, project: Project, body: dict[str, object]) -> None:
        with OPERATION_LOCK:
            item = take_confirmation(body.get("confirmation"), "commit", project)
            project.require_branch()
            if project.review_state() != item["state"]:
                raise ValueError("Files or HEAD changed after review. Review the commit again.")
            output = project.commit(str(item["message"]))
        self.send_json({"ok": True, "output": output, **project.status()})

    def prepare_discard(self, project: Project) -> None:
        project.require_branch()
        candidates = project.run("diff", "--name-only", "-z", "--no-ext-diff", "--").strip("\0").split("\0")
        candidates = [x for x in candidates if x]
        if not candidates:
            raise ValueError("There are no unstaged tracked changes to restore.")
        raw = project.porcelain()
        token = make_confirmation("discard", project, project.review_state(), files=candidates)
        self.send_json({"ok": True, "confirmation": token, "tracked": candidates,
                        "untracked": [x["path"] for x in project.changes(raw) if x["untracked"]],
                        "warning": "Only listed unstaged tracked changes are restored. Staged and untracked files remain.",
                        "expiresIn": TOKEN_TTL})

    def confirm_discard(self, project: Project, body: dict[str, object]) -> None:
        with OPERATION_LOCK:
            item = take_confirmation(body.get("confirmation"), "discard", project)
            project.require_branch()
            if project.review_state() != item["state"]:
                raise ValueError("Files changed after review. Review the discard list again.")
            project.run("restore", "--worktree", "--", *item["files"])
        self.send_json({"ok": True, "output": "Restored listed unstaged changes.", **project.status()})

    def prepare_restore(self, project: Project, body: dict[str, object]) -> None:
        project.require_branch()
        if project.porcelain():
            raise ValueError("Commit or otherwise handle all modified and untracked files before restoring a version. Nothing changed.")
        target = project.resolve_commit(body.get("commit"))
        current = project.head()
        if project.run("rev-parse", "HEAD^{tree}").strip() == project.run("rev-parse", f"{target}^{{tree}}").strip():
            raise ValueError("The selected version already matches the current files.")
        files = project.changed_files(current, target)
        token = make_confirmation("restore", project, project.review_state(), target=target)
        self.send_json({"ok": True, "confirmation": token, "target": project.commit_info(target),
                        "current": project.commit_info(current), "files": files,
                        "warning": "These committed file changes will be replaced by the selected version. A new restore commit preserves the current commit and makes recovery possible.",
                        "expiresIn": TOKEN_TTL})

    def confirm_restore(self, project: Project, body: dict[str, object]) -> None:
        with OPERATION_LOCK:
            item = take_confirmation(body.get("confirmation"), "restore", project)
            project.require_branch()
            if project.review_state() != item["state"]:
                raise ValueError("HEAD or working tree changed after review. Review the restore again.")
            output = project.restore_version(str(item["target"]))
        self.send_json({"ok": True, "output": output, **project.status()})

    def view_historical(self, project: Project, body: dict[str, object]) -> None:
        commit = project.resolve_commit(body.get("commit"))
        with OPERATION_LOCK:
            if project.porcelain():
                raise ValueError("Handle modified and untracked files before viewing a historical version. Nothing changed.")
            RETURN_BRANCHES[project.name] = project.return_branch(RETURN_BRANCHES.get(project.name))
            project.run("switch", "--detach", commit)
        self.send_json({"ok": True, "output": "Historical version is now active.",
                        **project.status(RETURN_BRANCHES.get(project.name))})

    def return_current(self, project: Project) -> None:
        with OPERATION_LOCK:
            if project.branch():
                raise ValueError("The repository is already on a branch.")
            if project.porcelain():
                raise ValueError("Handle modified and untracked files before returning. Nothing changed.")
            branch = project.return_branch(RETURN_BRANCHES.get(project.name))
            project.run("switch", branch)
            RETURN_BRANCHES.pop(project.name, None)
        self.send_json({"ok": True, "output": f"Returned to {branch}.", **project.status()})

    def preview_route(self, path: str) -> None:
        parts = path.strip("/").split("/")
        historical = parts[0] == "versions"
        if len(parts) < (4 if historical else 3):
            raise ValueError("Invalid preview path.")
        project = project_from(unquote(parts[1]))
        if not project.preview:
            self.error("This project has no website preview.", HTTPStatus.NOT_FOUND)
            return
        commit = project.resolve_commit(parts[2]) if historical else None
        relative_parts = parts[3:] if historical else parts[2:]
        if relative_parts[0] == "preview":
            relative_parts = relative_parts[1:]
        decoded = unquote("/".join(relative_parts))
        relative = PurePosixPath(decoded)
        if not decoded or relative.is_absolute() or any(x in ("", ".", "..") or x.startswith(".") or "\\" in x for x in relative.parts):
            self.error("Invalid preview path.", HTTPStatus.FORBIDDEN)
            return
        if relative.suffix.lower() not in PREVIEW_EXTENSIONS:
            self.error("This file type is not available through preview.", HTTPStatus.FORBIDDEN)
            return
        if historical:
            try:
                body = project.blob(commit, relative.as_posix())
            except FileNotFoundError:
                self.error("Not found.", HTTPStatus.NOT_FOUND)
                return
            self.send_file_bytes(body, relative.name, panel=False)
        else:
            candidate = (project.path / relative).resolve()
            try:
                resolved_relative = candidate.relative_to(project.path)
            except ValueError:
                self.error("Invalid preview path.", HTTPStatus.FORBIDDEN)
                return
            if any(part.startswith(".") for part in resolved_relative.parts) or candidate.suffix.lower() not in PREVIEW_EXTENSIONS:
                self.error("Invalid preview path.", HTTPStatus.FORBIDDEN)
                return
            self.serve_file(candidate, panel=False)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.security_headers()
        self.end_headers()

    def serve_file(self, path: Path, panel: bool) -> None:
        if not path.is_file():
            self.error("Not found.", HTTPStatus.NOT_FOUND)
            return
        self.send_file_bytes(path.read_bytes(), path.name, panel)

    def send_file_bytes(self, body: bytes, name: str, panel: bool) -> None:
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith(("text/", "application/javascript", "application/json")) else content_type)
        self.send_header("Content-Length", str(len(body)))
        self.security_headers()
        if panel:
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Dev Panel: http://{HOST}:{PORT}")
    print("Configured projects: " + ", ".join(PROJECTS))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Dev Panel.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
