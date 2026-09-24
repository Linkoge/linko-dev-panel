"""Configured Git repositories and operations; no HTTP or UI code lives here."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

COMMIT_ID = re.compile(r"[0-9a-fA-F]{7,40}\Z")
HISTORY_PAGE_SIZE = 20


class GitError(RuntimeError):
    def __init__(self, command: list[str], returncode: int, output: str):
        self.command, self.returncode, self.output = command, returncode, output
        super().__init__(output or f"Git exited with status {returncode}")


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    remote: str | None
    preview: str | None

    def run(self, *args: str, timeout: int = 30, check: bool = True) -> str:
        command = ["git", *args]
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            result = subprocess.run(command, cwd=self.path, env=env, text=True,
                                    encoding="utf-8", errors="surrogateescape",
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise GitError(command, 124, f"Git timed out after {timeout} seconds.") from exc
        if check and result.returncode:
            raise GitError(command, result.returncode, result.stdout.strip())
        return result.stdout

    def blob(self, commit: str, path: str) -> bytes:
        result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=self.path,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=30, check=False)
        if result.returncode:
            raise FileNotFoundError(path)
        return result.stdout

    def head(self) -> str:
        return self.run("rev-parse", "HEAD").strip()

    def branch(self) -> str | None:
        return self.run("branch", "--show-current").strip() or None

    def branch_exists(self, branch: str) -> bool:
        return bool(self.run("show-ref", "--verify", f"refs/heads/{branch}", check=False).strip())

    def return_branch(self, remembered: str | None = None) -> str:
        current = self.branch()
        if current:
            return current
        if remembered and self.branch_exists(remembered):
            return remembered
        if self.branch_exists("main"):
            return "main"
        branches = self.run("for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines()
        if branches:
            return branches[0]
        raise ValueError("No local branch is available to return to.")

    def resolve_commit(self, value: object) -> str:
        if not isinstance(value, str) or not COMMIT_ID.fullmatch(value):
            raise ValueError("Invalid commit identifier.")
        try:
            resolved = self.run("rev-parse", "--verify", f"{value}^{{commit}}").strip()
        except GitError as exc:
            raise ValueError(f"That commit does not exist in {self.name}.") from exc
        if not re.fullmatch(r"[0-9a-f]{40}", resolved):
            raise ValueError("That commit could not be resolved safely.")
        return resolved

    def commit_info(self, commit: str) -> dict[str, str]:
        raw = self.run("show", "-s", "--date=iso-strict", "--format=%H%x00%h%x00%ad%x00%s", commit).rstrip("\n")
        full, short, date, subject = raw.split("\0", 3)
        return {"fullHash": full, "hash": short, "date": date, "subject": subject}

    def porcelain(self) -> str:
        return self.run("status", "--porcelain=v1", "-z", "--untracked-files=all")

    def review_state(self) -> str:
        """Fingerprint HEAD, branch, staged/unstaged content, and untracked metadata."""
        raw = self.porcelain()
        untracked = []
        for item in self.changes(raw):
            if item["untracked"]:
                path = self.path / str(item["path"])
                try:
                    stat = path.lstat()
                    untracked.append(f"{item['path']}:{stat.st_mode}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ino}")
                except OSError:
                    untracked.append(f"{item['path']}:missing")
        return snapshot(self.head(), self.branch() or "", raw,
                        self.run("diff", "--binary", "--no-ext-diff", "--"),
                        self.run("diff", "--cached", "--binary", "--no-ext-diff", "--"),
                        *untracked)

    def changes(self, raw: str | None = None) -> list[dict[str, object]]:
        records = (self.porcelain() if raw is None else raw).split("\0")
        changes: list[dict[str, object]] = []
        i = 0
        while i < len(records):
            record = records[i]
            i += 1
            if len(record) < 4:
                continue
            code, path = record[:2], record[3:]
            if "R" in code or "C" in code:
                i += 1  # -z format includes the rename source after the destination
            if code == "!!":
                continue
            item: dict[str, object] = {"path": path, "status": code, "untracked": code == "??"}
            try:
                modified = (self.path / path).lstat().st_mtime
                local = datetime.fromtimestamp(modified).astimezone()
                item.update(mtime=modified, mtimeExact=local.strftime("%H:%M"),
                            mtimeFull=local.strftime("%Y-%m-%d %H:%M:%S %Z"))
            except OSError:
                item.update(mtime=None, mtimeExact=None, mtimeFull=None)
            changes.append(item)
        return changes

    def upstream(self) -> str | None:
        if not self.branch():
            return None
        value = self.run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False).strip()
        return value if value and not value.startswith("fatal:") else None

    def relationship(self, branch: str | None, upstream: str | None) -> dict[str, object]:
        if not branch or not self.remote:
            return {"available": False, "label": "No branch or remote configured"}
        target = upstream if upstream and upstream.startswith(f"{self.remote}/") else None
        if not target:
            candidate = f"refs/remotes/{self.remote}/{branch}"
            if self.run("show-ref", "--verify", candidate, check=False).strip():
                target = f"{self.remote}/{branch}"
        if not target:
            return {"available": False, "label": "No local remote-tracking branch available"}
        try:
            ahead, behind = map(int, self.run("rev-list", "--left-right", "--count", f"HEAD...{target}").split())
        except (GitError, ValueError):
            return {"available": False, "label": f"Unable to compare with {target}"}
        if ahead == behind == 0:
            label = f"Up to date with {target}"
        elif ahead and behind:
            label = f"{ahead} ahead, {behind} behind {target}"
        elif ahead:
            label = f"{ahead} ahead of {target}"
        else:
            label = f"{behind} behind {target}"
        return {"available": True, "ref": target, "ahead": ahead, "behind": behind, "label": label}

    def status(self, remembered_branch: str | None = None) -> dict[str, object]:
        raw = self.porcelain()
        changes = self.changes(raw)
        tracked = [{"status": x["status"], "path": x["path"]} for x in changes if not x["untracked"]]
        untracked = [str(x["path"]) for x in changes if x["untracked"]]
        branch = self.branch()
        upstream = self.upstream()
        historical = None
        if branch is None:
            historical = {**self.commit_info(self.head()), "returnBranch": self.return_branch(remembered_branch)}
        return {"project": self.name, "branch": branch or "(detached HEAD)", "head": self.head(),
                "upstream": upstream, "remote": self.relationship(branch, upstream),
                "clean": not changes, "tracked": tracked, "untracked": untracked,
                "localChanges": changes, "serverTime": time.time(), "historical": historical,
                "preview": bool(self.preview)}

    def history(self, offset: int, remembered_branch: str | None = None) -> dict[str, object]:
        ref = self.return_branch(remembered_branch)
        raw = self.run("log", ref, f"--skip={offset}", f"-n{HISTORY_PAGE_SIZE + 1}",
                       "--date=iso-strict", "--format=%H%x00%h%x00%ad%x00%s%x1e")
        records = []
        for record in raw.rstrip("\n\x1e").split("\x1e") if raw else []:
            parts = record.strip("\n").split("\0", 3)
            if len(parts) == 4:
                records.append(dict(zip(("fullHash", "hash", "date", "subject"), parts)))
        return {"commits": records[:HISTORY_PAGE_SIZE], "hasMore": len(records) > HISTORY_PAGE_SIZE,
                "nextOffset": offset + HISTORY_PAGE_SIZE}

    def changed_files(self, source: str, target: str) -> list[dict[str, object]]:
        raw = self.run("diff", "--name-status", "-z", "--find-renames", "--no-ext-diff", source, target, "--")
        parts = raw.split("\0")
        files = []
        i = 0
        while i < len(parts) and parts[i]:
            code = parts[i]; i += 1
            count = 2 if code.startswith(("R", "C")) else 1
            paths = parts[i:i + count]; i += count
            category = "added" if code == "A" else "removed" if code == "D" else "modified"
            files.append({"index": len(files), "status": code, "category": category,
                          "label": " → ".join(paths), "paths": paths})
        return files

    def comparison(self, commit: str, remembered_branch: str | None = None) -> dict[str, object]:
        ref = self.return_branch(remembered_branch)
        files = self.changed_files(commit, ref)
        return {"commit": self.commit_info(commit), "currentRef": ref, "files": files,
                "summary": {kind: sum(x["category"] == kind for x in files)
                            for kind in ("added", "removed", "modified")}}

    def diff(self) -> dict[str, object]:
        untracked = [str(x["path"]) for x in self.changes() if x["untracked"]]
        return {"diff": self.run("diff", "--no-ext-diff", "--no-color", "HEAD", "--", check=False),
                "untracked": untracked,
                "note": "Untracked file contents are not included in Git diff."}

    def require_branch(self) -> str:
        branch = self.branch()
        if not branch:
            raise ValueError("This action is unavailable while viewing a historical version. Return to current first.")
        return branch

    def commit(self, message: str) -> str:
        self.run("add", "-A")
        return self.run("commit", "-m", message, timeout=60).strip()

    def push(self) -> str:
        branch = self.require_branch()
        if not self.remote:
            raise ValueError("No remote is configured for this project.")
        return self.run("push", self.remote, f"HEAD:refs/heads/{branch}", timeout=120).strip()

    def pull(self) -> str:
        branch = self.require_branch()
        upstream = self.upstream()
        if not self.remote or not upstream or not upstream.startswith(f"{self.remote}/"):
            raise ValueError("No upstream on the configured remote is set for this branch.")
        return self.run("pull", "--ff-only", self.remote, upstream[len(self.remote) + 1:], timeout=120).strip()

    def restore_version(self, commit: str) -> str:
        """Create a new commit with the target tree, preserving prior history."""
        self.require_branch()
        if self.porcelain():
            raise ValueError("The working tree changed after review. Commit or handle those files first.")
        if self.run("rev-parse", "HEAD^{tree}").strip() == self.run("rev-parse", f"{commit}^{{tree}}").strip():
            raise ValueError("The selected version already matches the current files.")
        self.run("restore", f"--source={commit}", "--staged", "--worktree", "--", ":/")
        return self.run("commit", "-m", f"Restore version {commit[:12]}", timeout=60).strip()


def snapshot(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode("utf-8", "surrogateescape")).hexdigest()


def load_projects(config_path: Path) -> dict[str, Project]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    entries = data.get("projects")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("projects.json must contain a nonempty projects object.")
    projects = {}
    for name, value in entries.items():
        if not isinstance(name, str) or not name or not isinstance(value, dict):
            raise ValueError("Each project needs a name and settings object.")
        raw_path = value.get("path")
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ValueError(f"{name}: path must be absolute.")
        path = Path(raw_path).resolve(strict=True)
        remote = value.get("remote", "origin")
        preview = value.get("preview")
        if remote is not None and (not isinstance(remote, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote)):
            raise ValueError(f"{name}: invalid remote name.")
        if preview is not None and (not isinstance(preview, str) or not preview or
                                    Path(preview).is_absolute() or any(p in (".", "..") or p.startswith(".") for p in Path(preview).parts) or
                                    Path(preview).suffix.lower() != ".html"):
            raise ValueError(f"{name}: preview must be a visible relative HTML path.")
        project = Project(name, path, remote, preview)
        top = project.run("rev-parse", "--show-toplevel").strip()
        if Path(top).resolve() != path:
            raise ValueError(f"{name}: path must be a Git repository root.")
        projects[name] = project
    return projects
