"""Disposable live panel used by browser terminal tests. Never touches real projects."""
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
from repository import Project

class FixtureHandler(server.Handler):
    def do_POST(self):
        if self.path == "/test/disconnect":
            terminal_backend.disconnect_all()
            self.send_json({"ok": True})
        else:
            super().do_POST()

with tempfile.TemporaryDirectory(prefix="panel-terminal-") as root:
    path = Path(root)
    subprocess.run(["git", "init", "-b", "main", root], check=True, capture_output=True)
    subprocess.run(["git", "-C", root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "--allow-empty", "-m", "fixture"], check=True, capture_output=True)
    (path / "index.html").write_text("<h1>Terminal test preview</h1>")
    project = Project("Test project Georgian ქართული", path, None, "index.html")
    server.HOST = "127.0.0.1"
    server.PROJECTS = {project.name: project}
    terminal_backend.SOCKET_NAME = "panel-terminal-test-" + str(os.getpid())
    panel = server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({"port": panel.server_port, "project": project.name, "path": root,
                      "socket": terminal_backend.SOCKET_NAME, "session": terminal_backend.session_name(project)}), flush=True)
    try:
        panel.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        terminal_backend.disconnect_all()
        panel.server_close()
        # Only the test's isolated tmux socket, never production sessions.
        subprocess.run(["tmux", "-L", terminal_backend.SOCKET_NAME, "kill-server"], capture_output=True)
