"""Live Phase 2 fixture. Git URL rewrites target disposable local remotes."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import terminal_backend


def git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


with tempfile.TemporaryDirectory(prefix="panel-onboarding-browser-") as temp:
    root = Path(temp)
    projects, remotes = root / "projects", root / "remotes"
    projects.mkdir(); remotes.mkdir()
    empty_start = os.environ.get("PANEL_TEST_EMPTY_START") == "1"
    existing = (root / "source") if empty_start else (projects / "existing")
    git(projects, "init", "-b", "main", str(existing))
    git(existing, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "existing")
    for name in ("empty", "success"):
        git(remotes, "init", "--bare", "-b", "main", str(remotes / (name + ".git")))
    (existing / "keep.txt").write_text("committed original\n")
    git(existing, "add", "keep.txt")
    git(existing, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture file")
    git(existing, "push", str(remotes / "success.git"), "main")
    (existing / "keep.txt").write_text("unsaved original\n")
    git_config = root / "gitconfig"
    git_config.write_text(f'[url "{remotes.as_posix()}/"]\n\tinsteadOf = https://git.fixture.invalid/team/\n\tinsteadOf = git@git.fixture.invalid:team/\n')
    os.environ["GIT_CONFIG_GLOBAL"] = str(git_config)
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    config = root / "projects.json"
    configured = {} if empty_start else {"Existing": {"path":str(existing), "remote":None}}
    if os.environ.get("PANEL_TEST_MISSING_PROJECTS") == "1":
        configured["Missing <script>"] = {"path": str(projects / "missing")}
    config.write_text(json.dumps({"projectsDirectory":str(projects), "projects":configured}))
    server.initialize_projects(config)
    server.HOST = "127.0.0.1"
    terminal_backend.SOCKET_NAME = "panel-onboarding-test-" + str(os.getpid())
    panel = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({"port":panel.server_port, "projects":str(projects), "socket":terminal_backend.SOCKET_NAME}), flush=True)
    try:
        panel.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.CLONES.shutdown()
        terminal_backend.disconnect_all()
        panel.server_close()
        subprocess.run(["tmux", "-L", terminal_backend.SOCKET_NAME, "kill-server"], capture_output=True)
