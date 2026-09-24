#!/usr/bin/env python3
"""Small, private Git control panel for the Linko working tree."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit


REPO = Path("/home/mint1/projects/Linko").resolve()
PANEL_DIR = Path(__file__).resolve().parent
HOST = os.environ.get("LINKO_PANEL_HOST", "100.65.36.48")
PORT = int(os.environ.get("LINKO_PANEL_PORT", "8765"))
MAX_BODY = 16_384
TOKEN_TTL = 300
HISTORY_PAGE_SIZE = 20
COMMIT_ID = re.compile(r"[0-9a-fA-F]{7,40}")
PREVIEW_EXTENSIONS = {
    ".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg",
    ".webp", ".avif", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".otf",
    ".mp4", ".webm",
}

CSRF_TOKEN = secrets.token_urlsafe(32)
OPERATION_LOCK = threading.Lock()
CONFIRMATIONS: dict[str, dict[str, object]] = {}
CONFIRMATIONS_LOCK = threading.Lock()
HISTORICAL_RETURN_BRANCH: str | None = None


class GitError(RuntimeError):
    def __init__(self, command: list[str], returncode: int, output: str):
        self.command = command
        self.returncode = returncode
        self.output = output
        super().__init__(output or f"Git exited with status {returncode}")


def git(*args: str, timeout: int = 30, check: bool = True) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(["git", *args], 124, f"Git timed out after {timeout} seconds.") from exc
    if check and result.returncode:
        raise GitError(["git", *args], result.returncode, result.stdout.strip())
    return result.stdout


def git_blob(commit: str, path: str) -> bytes:
    """Read a file exactly as stored in a commit, without changing HEAD."""
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise FileNotFoundError(path)
    return result.stdout


def porcelain() -> str:
    return git("status", "--porcelain=v1", "--untracked-files=all")


def current_branch() -> str | None:
    return git("branch", "--show-current").strip() or None


def local_branch_exists(branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def default_branch() -> str:
    """Choose a safe local return branch if the server starts while detached."""
    if local_branch_exists("main"):
        return "main"
    remote_head = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if remote_head.startswith("origin/") and local_branch_exists(remote_head[7:]):
        return remote_head[7:]
    branches = git("for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines()
    if branches:
        return branches[0]
    raise ValueError("No local branch is available to return to.")


def current_version_ref() -> str:
    branch = current_branch()
    if branch:
        return branch
    if HISTORICAL_RETURN_BRANCH and local_branch_exists(HISTORICAL_RETURN_BRANCH):
        return HISTORICAL_RETURN_BRANCH
    return default_branch()


def resolve_commit(value: object) -> str:
    if not isinstance(value, str) or not COMMIT_ID.fullmatch(value):
        raise ValueError("Invalid commit identifier.")
    try:
        resolved = git("rev-parse", "--verify", f"{value}^{{commit}}").strip()
    except GitError as exc:
        raise ValueError("That commit does not exist in the Linko repository.") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise ValueError("That commit could not be resolved safely.")
    return resolved


def commit_info(commit: str) -> dict[str, str]:
    raw = git("show", "-s", "--date=iso-strict", "--format=%H%x00%h%x00%ad%x00%s", commit).rstrip("\n")
    full_hash, short_hash, date, subject = raw.split("\0", 3)
    return {"fullHash": full_hash, "hash": short_hash, "date": date, "subject": subject}


def history_payload(offset: int) -> dict[str, object]:
    ref = current_version_ref()
    raw = git(
        "log", ref, f"--skip={offset}", f"-n{HISTORY_PAGE_SIZE + 1}",
        "--date=iso-strict", "--format=%H%x00%h%x00%ad%x00%s%x1e",
    )
    records = []
    for record in raw.rstrip("\n\x1e").split("\x1e") if raw else []:
        parts = record.strip("\n").split("\0", 3)
        if len(parts) == 4:
            records.append({"fullHash": parts[0], "hash": parts[1], "date": parts[2], "subject": parts[3]})
    has_more = len(records) > HISTORY_PAGE_SIZE
    return {"commits": records[:HISTORY_PAGE_SIZE], "hasMore": has_more, "nextOffset": offset + HISTORY_PAGE_SIZE}


def comparison_files(commit: str) -> tuple[str, list[dict[str, object]]]:
    current_ref = current_version_ref()
    raw = git("diff", "--name-status", "--find-renames", "--no-ext-diff", commit, current_ref, "--")
    files: list[dict[str, object]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0]
        if code == "A":
            category = "added"
        elif code == "D":
            category = "removed"
        else:
            category = "modified"
        paths = parts[1:3] if code.startswith(("R", "C")) and len(parts) >= 3 else [parts[1]]
        label = " → ".join(paths)
        files.append({"index": len(files), "status": code, "category": category, "label": label, "paths": paths})
    return current_ref, files


def historical_status() -> dict[str, object] | None:
    if current_branch() is not None:
        return None
    info = commit_info(git("rev-parse", "HEAD").strip())
    info["returnBranch"] = current_version_ref()
    return info


def require_normal_mode() -> None:
    if current_branch() is None:
        raise ValueError("This action is disabled while viewing a historical version. Return to current first.")


def parse_status(raw: str) -> tuple[list[dict[str, str]], list[str]]:
    tracked: list[dict[str, str]] = []
    untracked: list[str] = []
    for line in raw.splitlines():
        if len(line) < 3:
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            untracked.append(path)
        elif code != "!!":
            tracked.append({"status": code, "path": path})
    return tracked, untracked


def local_changes() -> list[dict[str, object]]:
    """Return Git changes with mtimes from this machine's local filesystem."""
    raw = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = raw.split("\0")
    changes: list[dict[str, object]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 4:
            continue
        status, path = record[:2], record[3:]
        if status == "!!":
            continue
        # In -z format a rename/copy's destination is first and its source is
        # the following NUL-delimited field. The destination is the useful path
        # for its current filesystem timestamp.
        if "R" in status or "C" in status:
            index += 1

        change: dict[str, object] = {
            "path": path,
            "status": status,
            "untracked": status == "??",
        }
        try:
            modified = (REPO / path).lstat().st_mtime
        except (FileNotFoundError, NotADirectoryError, OSError):
            change["mtime"] = None
            change["mtimeExact"] = None
            change["mtimeFull"] = None
        else:
            local_modified = datetime.fromtimestamp(modified).astimezone()
            change["mtime"] = modified
            change["mtimeExact"] = local_modified.strftime("%H:%M")
            change["mtimeFull"] = local_modified.strftime("%Y-%m-%d %H:%M:%S %Z")
        changes.append(change)
    return changes


def discard_candidates() -> list[str]:
    output = git("diff", "--name-only", "--no-ext-diff", "--")
    return [line for line in output.splitlines() if line]


def origin_main_relationship() -> dict[str, object]:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        return {"available": False, "label": "origin/main is not available locally"}
    counts = git("rev-list", "--left-right", "--count", f"{current_version_ref()}...origin/main").strip().split()
    ahead, behind = (int(counts[0]), int(counts[1]))
    if ahead == behind == 0:
        label = "up to date with origin/main"
    elif ahead and behind:
        label = f"diverged: {ahead} ahead, {behind} behind origin/main"
    elif ahead:
        label = f"{ahead} commit{'s' if ahead != 1 else ''} ahead of origin/main"
    else:
        label = f"{behind} commit{'s' if behind != 1 else ''} behind origin/main"
    return {"available": True, "ahead": ahead, "behind": behind, "label": label}


def status_payload(include_csrf: bool = False) -> dict[str, object]:
    raw = porcelain()
    tracked, untracked = parse_status(raw)
    branch_name = current_branch()
    branch = branch_name or "(detached HEAD)"
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False).strip() if branch_name else ""
    payload: dict[str, object] = {
        "online": True,
        "branch": branch,
        "upstream": upstream or None,
        "clean": not tracked and not untracked,
        "tracked": tracked,
        "untracked": untracked,
        "localChanges": local_changes(),
        "serverTime": time.time(),
        "discardCandidates": discard_candidates(),
        "originMain": origin_main_relationship(),
        "historical": historical_status(),
    }
    if include_csrf:
        payload["csrfToken"] = CSRF_TOKEN
    return payload


def diff_payload() -> dict[str, object]:
    raw = porcelain()
    _, untracked = parse_status(raw)
    diff = git("diff", "--no-ext-diff", "--no-color", "HEAD", "--", check=False)
    return {
        "diff": diff,
        "untracked": untracked,
        "note": "Untracked file contents are not included in Git diff and will not be shown here.",
    }


def snapshot_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8", "surrogateescape")).hexdigest()


def make_confirmation(kind: str, snapshot: str, **details: object) -> str:
    token = secrets.token_urlsafe(24)
    with CONFIRMATIONS_LOCK:
        now = time.time()
        expired = [key for key, item in CONFIRMATIONS.items() if float(item["expires"]) < now]
        for key in expired:
            CONFIRMATIONS.pop(key, None)
        CONFIRMATIONS[token] = {
            "kind": kind,
            "snapshot": snapshot,
            "expires": now + TOKEN_TTL,
            **details,
        }
    return token


def take_confirmation(token: str, kind: str) -> dict[str, object]:
    with CONFIRMATIONS_LOCK:
        item = CONFIRMATIONS.pop(token, None)
    if not item or item.get("kind") != kind or float(item["expires"]) < time.time():
        raise ValueError("Confirmation expired or is invalid. Review the files again.")
    return item


class Handler(BaseHTTPRequestHandler):
    server_version = "LinkoDevPanel/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def allowed_host(self) -> bool:
        raw_host = self.headers.get("Host", "")
        try:
            hostname = urlsplit(f"//{raw_host}").hostname or ""
        except ValueError:
            return False
        extras = {item.strip() for item in os.environ.get("LINKO_PANEL_ALLOWED_HOSTS", "").split(",") if item.strip()}
        return hostname in {HOST, "127.0.0.1", "localhost", *extras}

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def send_json(self, data: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = HTTPStatus.BAD_REQUEST, output: str = "") -> None:
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
            self.send_error_json("Invalid security token. Reload the panel.", HTTPStatus.FORBIDDEN)
            return False
        origin = self.headers.get("Origin")
        if origin:
            try:
                origin_parts = urlsplit(origin)
            except ValueError:
                self.send_error_json("Invalid request origin.", HTTPStatus.FORBIDDEN)
                return False
            if origin_parts.scheme != "http" or origin_parts.netloc != self.headers.get("Host"):
                self.send_error_json("Cross-origin requests are not allowed.", HTTPStatus.FORBIDDEN)
                return False
        return True

    def do_GET(self) -> None:
        if not self.allowed_host():
            self.send_error_json("Host is not allowed.", HTTPStatus.FORBIDDEN)
            return
        parsed_url = urlsplit(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        try:
            if path in {"/", "/index.html"}:
                self.serve_file(PANEL_DIR / "index.html", panel=True)
            elif path == "/api/status":
                self.send_json({"ok": True, **status_payload(include_csrf=True)})
            elif path == "/api/diff":
                self.send_json({"ok": True, **diff_payload()})
            elif path == "/api/history":
                raw_offset = query.get("offset", ["0"])[0]
                if not raw_offset.isdigit() or int(raw_offset) > 1_000_000:
                    raise ValueError("Invalid history offset.")
                self.send_json({"ok": True, **history_payload(int(raw_offset))})
            elif path == "/api/compare":
                commit = resolve_commit(query.get("commit", [None])[0])
                current_ref, files = comparison_files(commit)
                summary = {kind: sum(item["category"] == kind for item in files) for kind in ("added", "removed", "modified")}
                self.send_json({
                    "ok": True, "commit": commit_info(commit), "currentRef": current_ref,
                    "files": files, "summary": summary,
                })
            elif path == "/api/compare/file":
                commit = resolve_commit(query.get("commit", [None])[0])
                raw_index = query.get("index", [""])[0]
                if not raw_index.isdigit():
                    raise ValueError("Invalid comparison file.")
                current_ref, files = comparison_files(commit)
                index = int(raw_index)
                if index >= len(files):
                    raise ValueError("Comparison file no longer exists.")
                item = files[index]
                diff = git("diff", "--no-ext-diff", "--no-color", commit, current_ref, "--", *item["paths"])
                self.send_json({"ok": True, "file": item, "diff": diff or "No textual diff is available for this file."})
            elif path == "/preview" or path == "/preview/":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/preview/xsecret.html")
                self.send_security_headers()
                self.end_headers()
            elif path.startswith("/preview/"):
                self.serve_preview(path[len("/preview/"):])
            elif path.startswith("/history-preview/"):
                parts = path.removeprefix("/history-preview/").split("/", 1)
                if len(parts) != 2:
                    raise ValueError("Invalid historical preview path.")
                commit, relative = parts
                # Keep the same virtual /preview/ directory used by the live
                # site, so both sibling and ../asset references resolve to the
                # selected commit's files.
                if relative.startswith("preview/"):
                    relative = relative[len("preview/"):]
                self.serve_historical_preview(commit, relative)
            elif path.startswith("/api/"):
                self.send_error_json("Not found.", HTTPStatus.NOT_FOUND)
            else:
                # Treat the repository as the website document root. This is
                # required for references such as ../assets/... from a page
                # under /preview/, which browsers normalize to /assets/....
                # serve_preview still enforces the web-extension allowlist and
                # rejects hidden components, traversal, and anything outside
                # the repository.
                self.serve_preview(path.removeprefix("/"))
        except GitError as exc:
            self.send_error_json("Git operation failed.", HTTPStatus.INTERNAL_SERVER_ERROR, exc.output)
        except ValueError as exc:
            self.send_error_json(str(exc))
        except OSError as exc:
            self.send_error_json("Unable to read the requested file.", HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        if not self.allowed_host():
            self.send_error_json("Host is not allowed.", HTTPStatus.FORBIDDEN)
            return
        if not self.valid_post_security():
            return
        path = urlsplit(self.path).path
        try:
            body = self.read_json()
            if path == "/api/save/prepare":
                self.prepare_save(body)
            elif path == "/api/save/confirm":
                self.confirm_save(body)
            elif path == "/api/pull":
                self.pull()
            elif path == "/api/discard/prepare":
                self.prepare_discard()
            elif path == "/api/discard/confirm":
                self.confirm_discard(body)
            elif path == "/api/history/view":
                self.view_historical(body)
            elif path == "/api/history/return":
                self.return_to_current()
            else:
                self.send_error_json("Not found.", HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_error_json(str(exc))
        except GitError as exc:
            self.send_error_json("Git operation failed.", HTTPStatus.CONFLICT, exc.output)
        except Exception as exc:
            self.send_error_json("Unexpected server error.", HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def prepare_save(self, body: dict[str, object]) -> None:
        require_normal_mode()
        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Enter a commit message.")
        message = message.strip()
        if len(message) > 200 or "\x00" in message or "\n" in message or "\r" in message:
            raise ValueError("Use a single-line commit message of at most 200 characters.")
        raw = porcelain()
        tracked, untracked = parse_status(raw)
        if not tracked and not untracked:
            raise ValueError("The working tree is already clean; there is nothing to commit.")
        token = make_confirmation("save", snapshot_digest(raw), message=message)
        self.send_json({
            "ok": True,
            "confirmation": token,
            "message": message,
            "tracked": tracked,
            "untracked": untracked,
            "expiresIn": TOKEN_TTL,
        })

    def confirm_save(self, body: dict[str, object]) -> None:
        require_normal_mode()
        token = body.get("confirmation")
        if not isinstance(token, str):
            raise ValueError("Missing confirmation.")
        with OPERATION_LOCK:
            item = take_confirmation(token, "save")
            if snapshot_digest(porcelain()) != item["snapshot"]:
                raise ValueError("Files changed after review. Review the commit again.")
            git("add", "-A")
            try:
                commit_output = git("commit", "-m", str(item["message"]), timeout=60)
            except GitError:
                # Keep the index intact so the user can inspect/retry; never rewrite history.
                raise
            try:
                push_output = git("push", timeout=120)
            except GitError as exc:
                raise GitError(exc.command, exc.returncode, f"Commit created locally, but push failed:\n{exc.output}") from exc
        self.send_json({"ok": True, "output": (commit_output + "\n" + push_output).strip(), **status_payload()})

    def pull(self) -> None:
        require_normal_mode()
        with OPERATION_LOCK:
            output = git("pull", "--ff-only", timeout=120)
        self.send_json({"ok": True, "output": output.strip(), **status_payload()})

    def prepare_discard(self) -> None:
        require_normal_mode()
        candidates = discard_candidates()
        _, untracked = parse_status(porcelain())
        if not candidates:
            raise ValueError("There are no unstaged tracked changes to restore. Staged and untracked files are left untouched.")
        snapshot = "\0".join(candidates)
        token = make_confirmation("discard", snapshot_digest(snapshot))
        self.send_json({
            "ok": True,
            "confirmation": token,
            "tracked": candidates,
            "untracked": untracked,
            "warning": "Only the listed unstaged tracked changes will be restored. Staged changes and untracked files will remain.",
            "expiresIn": TOKEN_TTL,
        })

    def confirm_discard(self, body: dict[str, object]) -> None:
        require_normal_mode()
        token = body.get("confirmation")
        if not isinstance(token, str):
            raise ValueError("Missing confirmation.")
        with OPERATION_LOCK:
            item = take_confirmation(token, "discard")
            current = "\0".join(discard_candidates())
            if snapshot_digest(current) != item["snapshot"]:
                raise ValueError("Tracked changes changed after review. Review the discard list again.")
            git("restore", "--worktree", "--", ".")
        self.send_json({"ok": True, "output": "Restored the reviewed unstaged tracked changes. Untracked and staged changes were not removed.", **status_payload()})

    def view_historical(self, body: dict[str, object]) -> None:
        global HISTORICAL_RETURN_BRANCH
        commit = resolve_commit(body.get("commit"))
        with OPERATION_LOCK:
            raw = porcelain()
            if raw:
                raise ValueError(
                    "The working tree is not clean. Save, commit, or otherwise handle all modified and untracked files before viewing a historical version. Nothing was changed."
                )
            branch = current_branch()
            if branch:
                HISTORICAL_RETURN_BRANCH = branch
            elif not HISTORICAL_RETURN_BRANCH:
                HISTORICAL_RETURN_BRANCH = default_branch()
            git("switch", "--detach", commit)
        self.send_json({"ok": True, "output": "Historical version is now active.", **status_payload()})

    def return_to_current(self) -> None:
        global HISTORICAL_RETURN_BRANCH
        with OPERATION_LOCK:
            if current_branch() is not None:
                raise ValueError("The repository is already on its current branch.")
            if porcelain():
                raise ValueError(
                    "The historical working tree is not clean. Handle its modified or untracked files before returning; nothing was changed."
                )
            branch = HISTORICAL_RETURN_BRANCH or default_branch()
            if not local_branch_exists(branch):
                raise ValueError("The original branch is no longer available locally.")
            git("switch", branch)
            HISTORICAL_RETURN_BRANCH = None
        self.send_json({"ok": True, "output": f"Returned to {branch}.", **status_payload()})

    def serve_preview(self, raw_relative: str) -> None:
        decoded = unquote(raw_relative)
        relative = Path(decoded)
        if relative.is_absolute() or any(part in {"", ".", ".."} or part.startswith(".") for part in relative.parts):
            self.send_error_json("Invalid preview path.", HTTPStatus.FORBIDDEN)
            return
        candidate = (REPO / relative).resolve()
        try:
            candidate.relative_to(REPO)
        except ValueError:
            self.send_error_json("Invalid preview path.", HTTPStatus.FORBIDDEN)
            return
        if candidate.suffix.lower() not in PREVIEW_EXTENSIONS:
            self.send_error_json("This file type is not available through preview.", HTTPStatus.FORBIDDEN)
            return
        self.serve_file(candidate, panel=False)

    def serve_historical_preview(self, raw_commit: str, raw_relative: str) -> None:
        commit = resolve_commit(raw_commit)
        decoded = unquote(raw_relative)
        relative = PurePosixPath(decoded)
        if relative.is_absolute() or any(part in {"", ".", ".."} or part.startswith(".") for part in relative.parts):
            self.send_error_json("Invalid preview path.", HTTPStatus.FORBIDDEN)
            return
        if Path(decoded).suffix.lower() not in PREVIEW_EXTENSIONS:
            self.send_error_json("This file type is not available through preview.", HTTPStatus.FORBIDDEN)
            return
        try:
            body = git_blob(commit, relative.as_posix())
        except FileNotFoundError:
            self.send_error_json("Not found.", HTTPStatus.NOT_FOUND)
            return
        self.send_file_bytes(body, Path(decoded).name, panel=False)

    def serve_file(self, path: Path, panel: bool) -> None:
        if not path.is_file():
            self.send_error_json("Not found.", HTTPStatus.NOT_FOUND)
            return
        self.send_file_bytes(path.read_bytes(), path.name, panel)

    def send_file_bytes(self, body: bytes, name: str, panel: bool) -> None:
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith(("text/", "application/javascript", "application/json")) else content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if panel:
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    if not REPO.is_dir() or not (REPO / ".git").exists():
        raise SystemExit(f"Linko Git repository not found at {REPO}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Linko Dev Panel: http://{HOST}:{PORT}")
    print(f"Website preview: http://{HOST}:{PORT}/preview/xsecret.html")
    print(f"Repository: {REPO}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Linko Dev Panel.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
