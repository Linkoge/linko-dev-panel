"""Read-only project discovery and bounded, shell-free repository clone jobs."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
from urllib.parse import urlsplit

from repository import GitError, Project, load_projects

SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*\Z")
HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\Z")
USER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*\Z")
CLONE_TIMEOUT = 300


def repository_url(value: object) -> dict[str, str]:
    """Accept network Git URLs only; never paths, options or credential URLs."""
    error = "Use an SSH or HTTPS Git URL, such as git@host:owner/repo.git or https://host/owner/repo.git. URLs cannot contain credentials, query strings, spaces, escapes or shell characters."
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError(error)
    value = value.strip()
    if any(ord(c) < 33 or ord(c) > 126 or c in "\\'\"$`()[]{};!|&%?#<>" for c in value):
        raise ValueError(error)
    if "://" in value:
        try:
            parts = urlsplit(value)
            if (parts.scheme not in {"ssh", "https"} or not parts.hostname
                    or not HOST.fullmatch(parts.hostname) or ".." in parts.hostname
                    or parts.query or parts.fragment or parts.password is not None
                    or (parts.scheme == "https" and parts.username is not None)
                    or (parts.username is not None and not USER.fullmatch(parts.username))
                    or (parts.port is not None and not 1 <= parts.port <= 65535)):
                raise ValueError(error)
            # Reject escapes, empty authority ports and ambiguous URL syntax.
            authority = re.fullmatch(r"(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9.-]+(?::[0-9]+)?", parts.netloc)
            if not authority or not parts.path.startswith("/"):
                raise ValueError(error)
            path = parts.path[1:]
        except ValueError:
            raise ValueError(error) from None
    else:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)@([A-Za-z0-9.-]+):(.+)", value)
        if not match or not USER.fullmatch(match[1]) or not HOST.fullmatch(match[2]) or ".." in match[2]:
            raise ValueError(error)
        path = match[3]
    segments = path.split("/")
    if not segments or any(not SEGMENT.fullmatch(s) or len(s) > 180 for s in segments):
        raise ValueError(error)
    name = segments[-1].removesuffix(".git")
    if not SEGMENT.fullmatch(name) or name.endswith("."):
        raise ValueError("The repository must have a safe project name using letters, numbers, underscores, dots or hyphens.")
    return {"url": value, "repository": "/".join([*segments[:-1], name]), "name": name}


def projects_directory(panel_dir: Path, config: Path) -> Path:
    try:
        data = json.loads(config.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to read project configuration {config}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("projects.json must contain a projects object.")
    raw = os.environ.get("LINKO_PROJECTS_DIR", data.get("projectsDirectory"))
    if raw is None:
        return panel_dir.resolve().parent
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("projectsDirectory / LINKO_PROJECTS_DIR must be a directory path.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = config.resolve().parent / path
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("The configured projects directory must exist and be a directory.")
    return path


def git_root(path: Path) -> bool:
    if not (path / ".git").exists():
        return False
    try:
        probe = Project(path.name, path, "origin", None)
        return Path(probe.run("rev-parse", "--show-toplevel", timeout=5).strip()).resolve() == path
    except (GitError, OSError, ValueError):
        return False


class ProjectRegistry:
    def __init__(self, root: Path, configured: dict[str, Project], config_path: Path | None = None):
        self.root = root.resolve(strict=True)
        self.configured = configured.copy()
        self.config_path = config_path
        self.project_errors: list[dict[str, str]] = []
        self.lock = threading.Lock()

    def refresh(self, excluded=()) -> dict[str, Project]:
        """Configured names/metadata win; only immediate, real Git roots qualify."""
        with self.lock:
            configured_paths: set[Path] = set()
            if self.config_path is not None:
                errors: list[dict[str, str]] = []
                self.configured = load_projects(self.config_path, errors=errors,
                                                configured_paths=configured_paths)
                if errors != self.project_errors:
                    for item in errors:
                        logging.getLogger(__name__).warning("Project unavailable (%s): %s", item["name"], item["error"])
                self.project_errors = errors
            projects = self.configured.copy()
            paths = configured_paths | {p.path for p in projects.values()}
            if self.root.resolve(strict=True) != self.root:
                raise ValueError("The projects directory changed. Check settings and restart the panel.")
            for entry in sorted(self.root.iterdir(), key=lambda p: p.name):
                if entry.name.startswith(".") or entry.is_symlink() or not entry.is_dir():
                    continue
                path = entry.resolve()
                if (path in paths or path in excluded or not path.is_relative_to(self.root)
                        or not git_root(path)):
                    continue
                name = entry.name
                # Deterministic collision handling preserves configured identities.
                if name in projects:
                    name += " (local)"
                while name in projects:
                    name += " (local)"
                projects[name] = Project(name, path, "origin", None)
                paths.add(path)
            return projects

    def destination(self, name: str) -> Path:
        if not SEGMENT.fullmatch(name) or name.endswith("."):
            raise ValueError("Invalid project name.")
        if self.root.resolve(strict=True) != self.root:
            raise ValueError("The projects directory changed. Check settings and restart the panel.")
        path = self.root / name
        canonical = path.resolve()
        if canonical.parent != self.root or not canonical.is_relative_to(self.root):
            raise ValueError("The destination must remain inside the projects directory.")
        return path

    def preview(self, value: object, excluded=()) -> dict:
        parsed = repository_url(value)
        path = self.destination(parsed["name"])
        projects = self.refresh(excluded)
        existing = next((p.name for p in projects.values() if p.path == path), None)
        try:
            local = "~/" + path.relative_to(Path.home()).as_posix()
        except ValueError:
            local = str(path)
        return {"repository": parsed["repository"], "name": parsed["name"],
                "localPath": local, "exists": os.path.lexists(path), "existingProject": existing}


def safe_output(value: str, url: str) -> str:
    value = value.replace(url, "[repository URL]")
    value = re.sub(r"(?:https?|ssh)://[^\s'\"<>]+|[\w.-]+@[\w.-]+:[^\s'\"<>]+", "[repository URL]", value)
    return "".join(c for c in value if c in "\n\r\t" or (ord(c) >= 32 and ord(c) != 127))


def clone_error(output: str) -> str:
    lower = output.lower()
    if any(s in lower for s in ("authentication", "permission denied", "could not read username", "terminal prompts disabled", "host key verification failed")):
        return "Git authentication failed. Check the server user's existing SSH key, trusted host entry or Git credential setup, then retry."
    if any(s in lower for s in ("not found", "does not exist", "not a git repository", "could not read from remote")):
        return "Repository unavailable. Check the URL and the server user's access to the repository."
    if any(s in lower for s in ("resolve host", "resolve hostname", "connection", "network", "timed out", "unreachable")):
        return "Could not connect to the Git server. Check the host and network, then retry."
    return "Git clone failed. Check the Git output below, then retry."


class CloneManager:
    def __init__(self, registry: ProjectRegistry, refresh):
        self.registry, self.refresh = registry, refresh
        self.lock = threading.Lock()
        self.jobs = {}
        self.stopping = False

    def excluded(self):
        with self.lock:
            return {job["destination"] for job in self.jobs.values() if job["state"] == "cloning"}

    def discover(self):
        # Keep clone reservation and discovery atomic with respect to each other.
        with self.lock:
            excluded = {j["destination"] for j in self.jobs.values() if j["state"] == "cloning"}
            return self.registry.refresh(excluded)

    def preview(self, value):
        with self.lock:
            excluded = {j["destination"] for j in self.jobs.values() if j["state"] == "cloning"}
            return self.registry.preview(value, excluded)

    def start(self, value: object) -> dict:
        parsed = repository_url(value)
        path = self.registry.destination(parsed["name"])
        with self.lock:
            if self.stopping:
                raise ValueError("The panel is stopping. Retry after it starts.")
            if any(j["state"] == "cloning" for j in self.jobs.values()):
                raise ValueError("Another project is being cloned. Wait for it to finish.")
            # Atomic exclusive creation: never adopt an existing destination.
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                raise ValueError("The local project already exists. Select it if available; no files were changed.") from None
            except OSError:
                raise ValueError("Unable to create the local project directory. Check projects-directory permissions and available disk space.") from None
            identity = path.lstat()
            job_id = secrets.token_urlsafe(24)
            job = {"id": job_id, "state": "cloning", "output": "", "error": "", "project": None,
                   "destination": path, "identity": (identity.st_dev, identity.st_ino),
                   "cancel": threading.Event(), "name": parsed["name"]}
            # Bounded, in-memory status history. No URLs or credentials retained.
            if len(self.jobs) >= 32:
                self.jobs.pop(next(iter(self.jobs)))
            self.jobs[job_id] = job
            thread = threading.Thread(target=self._clone, args=(job, parsed["url"]), daemon=True)
            job["thread"] = thread
            try:
                thread.start()
            except RuntimeError:
                self._cleanup(job)
                del self.jobs[job_id]
                raise
        return self.status(job_id)

    def status(self, job_id: object) -> dict:
        with self.lock:
            if not isinstance(job_id, str) or job_id not in self.jobs:
                raise ValueError("Clone job not found. Refresh the project list to check for the repository.")
            return {key: self.jobs[job_id][key] for key in ("id", "state", "output", "error", "project", "name")}

    def cancel(self, job_id: object):
        with self.lock:
            if not isinstance(job_id, str) or job_id not in self.jobs:
                raise ValueError("Clone job not found.")
            self.jobs[job_id]["cancel"].set()
        return self.status(job_id)

    def _owned(self, job) -> bool:
        path = job["destination"]
        try:
            st = path.lstat()
            return (not path.is_symlink() and path.is_dir() and path.resolve() == path
                    and self.registry.root.resolve(strict=True) == self.registry.root
                    and path.parent == self.registry.root
                    and (st.st_dev, st.st_ino) == job["identity"])
        except OSError:
            return False

    def _cleanup(self, job) -> str:
        if not os.path.lexists(job["destination"]):
            return ""
        if not self._owned(job):
            return " Cleanup skipped because the directory identity changed. Inspect the local directory before retrying."
        try:
            # Python's Linux rmtree uses descriptors and rejects symlink swaps.
            shutil.rmtree(job["destination"])
            return " Partial clone removed; you can retry."
        except OSError:
            return " The partial clone could not be removed. Inspect the local directory before retrying."

    def _append(self, job, value):
        with self.lock:
            job["output"] = (job["output"] + value)[-12000:]

    def _clone(self, job, url):
        process = None
        reader = None
        failure = ""
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("GIT_TRACE") or key == "GIT_CURL_VERBOSE":
                env.pop(key)
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never", GIT_SSH_COMMAND=env.get("GIT_SSH_COMMAND", "ssh") + " -oBatchMode=yes -oStrictHostKeyChecking=yes", LC_ALL="C")
        try:
            if not self._owned(job):
                raise ValueError("The clone directory changed before Git started.")
            process = subprocess.Popen(
                ["git", "-c", "protocol.ext.allow=never", "clone", "--progress", "--", url, "."],
                cwd=job["destination"], env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
                start_new_session=os.name == "posix")
            def read_output():
                # Redact whole progress records, including carriage-return updates.
                # Drop oversized records instead of buffering unbounded remote text.
                pending = b""
                dropping = False
                while chunk := process.stdout.read1(4096):
                    for part in re.split(b"([\r\n])", chunk):
                        if part in (b"\r", b"\n"):
                            if not dropping:
                                self._append(job, safe_output(pending.decode("utf-8", "replace"), url) + "\n")
                            pending, dropping = b"", False
                        elif not dropping:
                            pending += part
                            if len(pending) > 4096:
                                pending, dropping = b"", True
                if pending and not dropping:
                    self._append(job, safe_output(pending.decode("utf-8", "replace"), url))
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            deadline = time.monotonic() + CLONE_TIMEOUT
            while process.poll() is None:
                if job["cancel"].wait(0.1):
                    failure = "Clone interrupted."
                    break
                if time.monotonic() >= deadline:
                    failure = "Clone timed out after five minutes. Check the network and server authentication, then retry."
                    break
            if failure:
                self._stop_process(process)
            process.wait()
            # A transport/helper must not keep the output pipe open after Git exits.
            self._stop_process(process)
            reader.join(timeout=5)
            if failure:
                raise ValueError(failure)
            if process.returncode:
                raise ValueError(clone_error(job["output"]))
            if not self._owned(job) or not git_root(job["destination"]):
                raise ValueError("The cloned directory could not be verified as a Git repository.")
            # Expose only fully successful clones to discovery.
            with self.lock:
                job["state"] = "registering"
            projects = self.refresh()
            project = next((p.name for p in projects.values() if p.path == job["destination"]), None)
            if not project:
                raise ValueError("The cloned project could not be discovered.")
            with self.lock:
                job.update(state="complete", project=project)
        except Exception as exc:
            if process is not None:
                self._stop_process(process)
            if reader is not None:
                reader.join(timeout=5)
            message = str(exc) if isinstance(exc, ValueError) else "Unable to run Git clone. Check Git installation and projects-directory permissions."
            cleanup = self._cleanup(job)
            with self.lock:
                job.update(state="failed", error=message + cleanup)
        finally:
            if process is not None and process.stdout is not None:
                process.stdout.close()

    @staticmethod
    def _stop_process(process):
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait()

    def shutdown(self):
        with self.lock:
            self.stopping = True
            threads = []
            for job in self.jobs.values():
                job["cancel"].set()
                threads.append(job["thread"])
        for thread in threads:
            thread.join(timeout=10)
