# Linko Dev Panel

A tiny Python standard-library control panel for `/home/mint1/projects/Linko`.
It binds to the Mint machine's Tailscale IP by default and serves the current
working tree preview at `/preview/xsecret.html`. The History section pages back
to the first commit, compares old commits with the current branch, and opens
commit-specific previews without changing the working tree or current tab.

Historical mode never moves the branch pointer and never uses `git reset`.
Entering or leaving it requires a completely clean working tree. Save, move,
or otherwise handle modified and untracked files yourself; the panel will not
automatically commit, stash, discard, or delete them.

## Start it

```bash
/home/mint1/projects/dev-panel/start.sh
```

Then open `http://100.65.36.48:8765` from a device on the same Tailscale network.
The panel is also available at `/panel` and `/dev-panel`; `/preview` opens the
current website preview.

To test locally without binding to Tailscale:

```bash
LINKO_PANEL_HOST=127.0.0.1 /home/mint1/projects/dev-panel/start.sh
```

## Optional systemd user service

The included service is only a template; it is not installed or enabled.

```bash
mkdir -p ~/.config/systemd/user
cp /home/mint1/projects/dev-panel/linko-dev-panel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now linko-dev-panel.service
```

Check it with `systemctl --user status linko-dev-panel.service`. To start it
at boot even before interactive login, user lingering may need to be enabled by
an administrator (`sudo loginctl enable-linger "$USER"`).

## Configuration

- `LINKO_PANEL_HOST` — bind address (default `100.65.36.48`)
- `LINKO_PANEL_PORT` — port (default `8765`)
- `LINKO_PANEL_ALLOWED_HOSTS` — optional comma-separated extra HTTP hostnames,
  useful for a Tailscale MagicDNS name

The server has no arbitrary-command endpoint. Git subprocesses use fixed
argument arrays and the fixed `/home/mint1/projects/Linko` repository directory.
Commit IDs are restricted to hexadecimal Git hashes and resolved as commit
objects before use. Mutating requests require a per-process CSRF token; save and
discard also require a short-lived review token.

There is no login screen or TLS. Anyone who can reach this port over the
Tailscale network can view the repository preview and use the controls. Use
Tailscale ACLs/grants and the host firewall to restrict access further if your
tailnet includes people or devices you do not fully trust.
