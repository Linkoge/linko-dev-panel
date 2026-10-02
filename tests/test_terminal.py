"""Terminal access controls and project mapping, without opening sockets."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server
import terminal_backend as terminal
from repository import Project


class TerminalSecurityTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.project = Project("unsafe; $(touch bad) ქართული", Path(self.root.name), None, None)

    def handler(self, path, origin="http://localhost", peer="127.0.0.1"):
        handler = server.Handler.__new__(server.Handler)
        handler.path = path
        handler.headers = {"Host": "localhost", "Origin": origin}
        handler.client_address = (peer, 10000)
        handler.wfile = BytesIO()
        handler.rfile = BytesIO()
        result = {}
        handler.send_response = lambda code: result.update(status=code)
        handler.send_header = lambda *_: None
        handler.end_headers = lambda: None
        return handler, result

    def test_private_peer_uses_only_tailscale_or_loopback(self):
        for peer in ("127.0.0.1", "::1", "100.100.100.100", "fd7a:115c:a1e0::1", "::ffff:100.100.100.100"):
            self.assertTrue(terminal.private_peer(peer), peer)
        for peer in ("8.8.8.8", "192.168.1.2", "::", "0.0.0.0", "invalid"):
            self.assertFalse(terminal.private_peer(peer), peer)

    def test_origin_and_public_peers_rejected_before_upgrade(self):
        for origin, peer in (("https://evil.invalid", "127.0.0.1"), ("null", "127.0.0.1"),
                             ("", "127.0.0.1"), ("http://localhost", "8.8.8.8")):
            handler, result = self.handler("/api/terminal/ws?project=known", origin, peer)
            with patch.object(terminal, "handle") as bridge:
                handler.do_GET()
                self.assertEqual(result["status"], 403)
                bridge.assert_not_called()

    def test_unknown_project_paths_and_command_parameters_rejected(self):
        with patch.dict(server.PROJECTS, {"known": self.project}, clear=True):
            for query in ("project=/tmp", "project=../known", "project=known&command=bash",
                          "project=known&path=/tmp", "project=known&project=known"):
                handler, result = self.handler("/api/terminal/ws?" + query)
                with patch.object(terminal, "handle") as bridge:
                    handler.do_GET()
                    self.assertEqual(result["status"], 400)
                    bridge.assert_not_called()

    def test_ticket_creation_requires_csrf_origin_private_peer_and_identity_only(self):
        with patch.dict(server.PROJECTS, {"known": self.project}, clear=True):
            for csrf, origin, peer, body, expected in (
                ("wrong", "http://localhost", "127.0.0.1", {"project":"known"}, 403),
                (server.CSRF_TOKEN, "", "127.0.0.1", {"project":"known"}, 403),
                (server.CSRF_TOKEN, "http://localhost", "8.8.8.8", {"project":"known"}, 403),
                (server.CSRF_TOKEN, "http://localhost", "127.0.0.1", {"project":"known","command":"bash"}, 400),
                (server.CSRF_TOKEN, "http://localhost", "127.0.0.1", {"project":"known","path":"/tmp"}, 400),
            ):
                handler, result = self.handler("/api/terminal/connect", origin, peer)
                raw = json.dumps(body).encode()
                handler.rfile = BytesIO(raw)
                handler.headers.update({"Content-Type":"application/json", "Content-Length":str(len(raw)), "X-Linko-CSRF":csrf})
                with patch.object(terminal, "issue_ticket") as issue:
                    handler.do_POST()
                    self.assertEqual(result["status"], expected)
                    issue.assert_not_called()

    def test_session_identity_and_shell_free_argument_arrays(self):
        name = terminal.session_name(self.project)
        self.assertRegex(name, r"^project-[a-f0-9]{32}$")
        self.assertEqual(name, terminal.session_name(self.project))
        self.assertNotEqual(name, terminal.session_name(Project(self.project.name, Path("/another"), None, None)))
        with patch.object(terminal, "dependencies", return_value=("/usr/bin/tmux",)), patch.object(terminal, "directory", return_value=self.project.path):
            args = terminal.tmux_args(self.project)
        self.assertEqual(args[-1], str(self.project.path))
        self.assertIn(name, args)
        self.assertNotIn(self.project.name, args)

    def test_tickets_single_use_expiry_and_project_binding(self):
        other = Project("Other", self.project.path, None, None)
        with patch.object(terminal, "dependencies"), patch.object(terminal, "directory"):
            ticket = terminal.issue_ticket(self.project)
            terminal.take_ticket(self.project, ticket)
            with self.assertRaises(ValueError): terminal.take_ticket(self.project, ticket)
            ticket = terminal.issue_ticket(self.project)
            with self.assertRaises(ValueError): terminal.take_ticket(other, ticket)
            ticket = terminal.issue_ticket(self.project)
            with patch.object(terminal.time, "monotonic", return_value=1e20):
                with self.assertRaises(ValueError): terminal.take_ticket(self.project, ticket)

    def test_replaced_symlink_directory_rejected(self):
        with tempfile.TemporaryDirectory() as target:
            link = self.project.path / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError): terminal.directory(Project("symlink", link, None, None))

    def test_dimensions_reject_wrong_types_and_bounds(self):
        self.assertEqual((24, 80), terminal.dimensions({"rows": 24, "cols": 80}))
        for rows, cols in ((True, 80), (24, "80"), (0, 80), (24, 1001), (501, 80)):
            with self.assertRaises(ValueError): terminal.dimensions({"rows": rows, "cols": cols})


if __name__ == "__main__":
    unittest.main()
