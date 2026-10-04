"""Generic Linux PTY connections; tmux, never the browser, owns application state."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time

from repository import Project

SOCKET_NAME = "linko-dev-panel"
INPUT_CHUNK = 8192
OUTPUT_CHUNK = 16384
MAX_CONNECTIONS = 16
_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
_lock = threading.Lock()
_session_lock = threading.RLock()
_tickets: dict[str, tuple[str, float]] = {}
_connections: set[socket.socket] = set()


def private_peer(address: str) -> bool:
    """Use actual TCP peer addresses, never forwarded headers."""
    try:
        peer = ipaddress.ip_address(address)
        if isinstance(peer, ipaddress.IPv6Address) and peer.ipv4_mapped:
            peer = peer.ipv4_mapped
        return peer.is_loopback or peer in ipaddress.ip_network("100.64.0.0/10") or peer in ipaddress.ip_network("fd7a:115c:a1e0::/48")
    except ValueError:
        return False


def dependencies():
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Browser terminals require a Linux server. Other panel features remain available.")
    tmux = shutil.which("tmux")
    if not tmux:
        raise RuntimeError("Install tmux on the Linux server to use browser terminals.")
    try:
        from ptyprocess import PtyProcess
        from simple_websocket import AioServer, ConnectionClosed
    except ImportError:
        raise RuntimeError("Install terminal dependencies with: python -m pip install -r requirements.txt") from None
    return tmux, PtyProcess, AioServer, ConnectionClosed


def directory(project: Project):
    path = project.path.resolve(strict=True)
    if path != project.path or not path.is_dir():
        raise ValueError("The configured project directory changed. Check configuration and restart the panel.")
    if project.run("rev-parse", "--show-toplevel").strip() != str(path):
        raise ValueError("The project must still be its configured Git working-tree root.")
    return path


def project_identity(project: Project) -> str:
    identity = json.dumps([project.name, str(project.path)], ensure_ascii=True).encode()
    return "project-" + hashlib.sha256(identity).hexdigest()[:32]


def session_names(tmux: str) -> dict[str, str]:
    result = subprocess.run([tmux, "-L", SOCKET_NAME, "list-sessions", "-F",
                             "#{session_name}\t#{@linko_project}"],
                            capture_output=True, text=True, timeout=5, check=False, shell=False)
    return dict(line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)


def next_session_name(names: dict[str, str]) -> str:
    number = 23
    while str(number) in names:
        number += 1
    return str(number)


def session_name(project: Project) -> str:
    tmux, *_ = dependencies()
    with _session_lock:
        names = session_names(tmux)
        identity = project_identity(project)
        for name, owner in names.items():
            if owner == identity or name == identity:
                return name
        return next_session_name(names)


def tmux_args(project: Project) -> list[str]:
    tmux, *_ = dependencies()
    # -L isolates panel sessions from ordinary tmux; -f prevents user config
    # hooks (including destroy-unattached) from changing persistence semantics.
    return [tmux, "-L", SOCKET_NAME, "-f", "/dev/null", "new-session", "-A",
            "-s", session_name(project), "-c", str(directory(project))]


def prepare_session(project: Project) -> list[str]:
    with _session_lock:
        args = tmux_args(project)
        base, name = args[:5], args[-3]
        identity = project_identity(project)
        def run(*command):
            return subprocess.run([*base, *command], capture_output=True, text=True,
                                  timeout=10, check=False, shell=False)
        # Rename legacy sessions in place, retaining their panes and applications.
        if name == identity:
            new_name = next_session_name(session_names(base[0]))
            if run("rename-session", "-t", "=" + name, new_name).returncode:
                raise RuntimeError("Unable to rename the project tmux session.")
            name = new_name
        if run("has-session", "-t", "=" + name).returncode:
            created = run("new-session", "-d", "-s", name, "-c", str(project.path))
            if created.returncode:
                raise RuntimeError("Unable to create the project tmux session.")
        # Enforce persistence and normal tmux wheel/copy-mode scrolling even
        # if this dedicated server was started with other options previously.
        for command in (("set-option", "-g", "exit-unattached", "off"),
                        ("set-option", "-t", name + ":", "@linko_project", identity),
                        ("set-option", "-t", name + ":", "destroy-unattached", "off"),
                        ("set-option", "-t", name + ":", "mouse", "on"),
                        ("set-option", "-t", name + ":", "history-limit", "10000")):
            result = run(*command)
            if result.returncode:
                raise RuntimeError("Unable to configure tmux: " + result.stderr.strip())
    return [*base, "attach-session", "-t", "=" + name]


def status(project: Project) -> dict:
    try:
        tmux, *_ = dependencies()
    except RuntimeError as exc:
        return {"available": False, "running": False, "error": str(exc)}
    name = session_name(project)
    result = subprocess.run([tmux, "-L", SOCKET_NAME, "has-session", "-t", "=" + name],
                            capture_output=True, timeout=5, check=False, shell=False)
    return {"available": True, "running": result.returncode == 0, "session": name}


def issue_ticket(project: Project) -> str:
    dependencies()
    directory(project)
    with _lock:
        now = time.monotonic()
        for key, (_, expiry) in list(_tickets.items()):
            if expiry <= now:
                del _tickets[key]
        if len(_tickets) >= 128:
            raise RuntimeError("Too many pending terminal connections. Try again shortly.")
        ticket = secrets.token_urlsafe(32)
        _tickets[ticket] = (project_identity(project), now + 30)
        return ticket


def take_ticket(project: Project, ticket: object):
    if not isinstance(ticket, str):
        raise ValueError("Missing terminal connection ticket.")
    with _lock:
        item = _tickets.pop(ticket, None)
    if not item or item[0] != project_identity(project) or item[1] <= time.monotonic():
        raise ValueError("Invalid or expired terminal connection ticket.")


def dimensions(data: dict) -> tuple[int, int]:
    cols, rows = data.get("cols"), data.get("rows")
    if type(cols) is not int or type(rows) is not int or not (2 <= cols <= 1000 and 2 <= rows <= 500):
        raise ValueError("Invalid terminal dimensions.")
    return rows, cols


async def fd_ready(fd: int, *, writable=False):
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    register = loop.add_writer if writable else loop.add_reader
    remove = loop.remove_writer if writable else loop.remove_reader
    def ready():
        if not future.done():
            future.set_result(None)
    register(fd, ready)
    try:
        await future
    finally:
        remove(fd)


async def bridge(connection: socket.socket, headers: dict, project: Project):
    _, PtyProcess, AioServer, ConnectionClosed = dependencies()
    ws, process = None, None
    tasks = []
    try:
        # Public socket integration API; the existing HTTP server keeps its port.
        ws = await AioServer.accept(sock=connection, headers=headers,
                                    ping_interval=20, max_message_size=32768)
        raw = await ws.receive(timeout=10)
        hello = json.loads(raw) if isinstance(raw, str) else {}
        if not isinstance(hello, dict) or hello.get("type") != "connect":
            raise ValueError("Expected a terminal connection ticket.")
        take_ticket(project, hello.get("ticket"))
        size = dimensions(hello)
        env = os.environ.copy()
        env.pop("TMUX", None)
        env["TERM"] = "xterm-256color"
        process = PtyProcess.spawn(prepare_session(project), env=env, cwd=str(project.path), dimensions=size)
        os.set_blocking(process.fd, False)
        await ws.send(json.dumps({"type": "ready", "session": session_name(project)}))
        input_queue = asyncio.Queue(maxsize=2)
        output_ack = asyncio.Event()
        pending_output = 0

        async def receive():
            nonlocal pending_output
            while True:
                raw = await ws.receive(timeout=1)
                if raw is None:
                    continue
                if isinstance(raw, bytes):
                    if not 0 < len(raw) <= INPUT_CHUNK:
                        raise ValueError("Invalid terminal input chunk.")
                    input_queue.put_nowait(raw)
                else:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError("Invalid terminal message.")
                    if data.get("type") == "resize":
                        process.setwinsize(*dimensions(data))
                    elif data.get("type") == "output-ack" and type(data.get("bytes")) is int and data["bytes"] == pending_output and pending_output:
                        pending_output = 0
                        output_ack.set()
                    else:
                        raise ValueError("Invalid terminal control message.")

        async def input_writer():
            while True:
                data = await input_queue.get()
                remaining = memoryview(data)
                while remaining:
                    try:
                        written = os.write(process.fd, remaining)
                        remaining = remaining[written:]
                    except BlockingIOError:
                        await fd_ready(process.fd, writable=True)
                await ws.send(json.dumps({"type": "input-ack", "bytes": len(data)}))

        async def output_reader():
            nonlocal pending_output
            while True:
                await fd_ready(process.fd)
                try:
                    data = os.read(process.fd, OUTPUT_CHUNK)
                except BlockingIOError:
                    continue
                if not data:
                    return
                output_ack.clear()
                pending_output = len(data)
                await ws.send(data)
                # Acknowledge only after xterm has parsed output: bounded buffers
                # even with very fast applications or a sleeping mobile browser.
                await asyncio.wait_for(output_ack.wait(), timeout=45)

        tasks = [asyncio.create_task(fn()) for fn in (receive, input_writer, output_reader)]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (ConnectionClosed, OSError, EOFError):
        pass
    except (ValueError, RuntimeError, asyncio.QueueFull, asyncio.TimeoutError) as exc:
        if ws and ws.connected:
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"type": "error", "message": str(exc) or "Terminal transport timed out. Reconnect to resume."}))
                await ws.close(reason=1008, message="Terminal connection ended. Reconnect to resume tmux.")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if ws and ws.connected:
            with contextlib.suppress(Exception):
                await ws.close()
        # asyncio.run cancels library receive tasks and closes its transports.
        # Closing/reaping this tmux *client* never sends kill-session/server.
        if process:
            process.close(force=True)


def handle(connection: socket.socket, headers: dict, project: Project):
    if not _slots.acquire(blocking=False):
        raise RuntimeError("Too many open terminals. Close an unused terminal and retry.")
    with _lock:
        _connections.add(connection)
    try:
        asyncio.run(bridge(connection, headers, project))
    finally:
        with _lock:
            _connections.discard(connection)
        _slots.release()


def disconnect_all():
    with _lock:
        connections = list(_connections)
    for connection in connections:
        with contextlib.suppress(OSError):
            connection.shutdown(socket.SHUT_RDWR)
