# Dev Panel

A small, mobile-friendly Git project manager for explicitly configured local repositories. It uses Python's standard library and keeps this panel in its own repository. It does not copy managed repositories into the panel directory.

## Architecture

- `projects.json` is the allowlist of repositories. The server loads and validates it at startup.
- `repository.py` contains repository-specific Git operations. Every operation runs from the selected configured repository root.
- `server.py` handles HTTP, request validation, confirmation tokens, and preview files.
- `index.html` is the phone-friendly interface. The selected project is remembered in the browser.

The current configuration manages `/home/mint1/projects/Linko` and this panel at `/home/mint1/projects/dev-panel`. Linko has a website preview; Dev Panel has none. The project selector controls status, files, diff, history, commit, push, pull, discard, restore, and historical checkout. Unknown project names and arbitrary paths are rejected by the server.

## Run

Requires Python 3.10 or newer, Git, and the configured repositories checked out locally.

```bash
LINKO_PANEL_HOST=127.0.0.1 ./start.sh
```

Open <http://127.0.0.1:8765/>. On the Mint machine, the default bind address is `100.65.36.48` for Tailscale access. `LINKO_PANEL_HOST`, `LINKO_PANEL_PORT`, and `LINKO_PANEL_ALLOWED_HOSTS` (comma-separated extra hostnames) are the available environment settings.

## Add a repository

Add an entry to `projects.json`, then restart the service. The path must be an absolute path to a Git repository root. Only entries in this file can be selected or used by Git operations.

```json
{
  "projects": {
    "Linko": {
      "path": "/home/mint1/projects/Linko",
      "remote": "origin",
      "preview": "xsecret.html"
    },
    "Dev Panel": {
      "path": "/home/mint1/projects/dev-panel",
      "remote": "origin"
    },
    "Another Project": {
      "path": "/home/mint1/projects/another-project",
      "remote": "origin"
    }
  }
}
```

`remote` defaults to `origin`. Set it to `null` for a local-only repository; Push will be unavailable and ahead/behind will not be reported. The optional `preview` is a relative HTML file path inside the repository. Omit it for projects without a website. Preview and historical preview serve only common web asset file types, reject hidden paths and paths outside the configured repository, and are unavailable for projects without `preview`.

Ahead/behind compares against the selected branch's upstream on the configured remote, or the matching local remote-tracking branch if no upstream is set. It uses local tracking data; it does not fetch automatically, so it may be stale until a pull or external fetch. Push targets the configured remote and current branch. Pull requires an upstream on that remote and uses `--ff-only`.

## Git and version actions

- **Commit changes** reviews the file list and creates a local commit. **Push commits** is a separate action; neither operation runs automatically.
- **View changes** displays the tracked diff and lists untracked files. **Discard current changes** reviews and restores only listed unstaged tracked files. Staged and untracked files remain.
- **History** loads recent commits and can compare each with the current branch. For preview-enabled projects, **View version** opens committed website files without changing the working tree.
- **Check out version** preserves the older detached-HEAD browsing flow. It requires a clean working tree; **Return to current** switches back to the original branch. Commit, push, pull, and discard are disabled while detached.
- **Restore version** requires a clean working tree. The confirmation shows the target commit, current commit, and files that will change. It creates a new commit with the target's tree on the current branch. The old commit and later history remain available, so an accidental restore can be recovered with another restore. It does not push automatically.

The panel never silently deletes uncommitted work during version checkout or restore. Commit review tokens expire after five minutes and are tied to a single project and Git state.

## Service

The included `linko-dev-panel.service` is a systemd user service template. Its paths match this checkout. To install it:

```bash
mkdir -p ~/.config/systemd/user
cp /home/mint1/projects/dev-panel/linko-dev-panel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now linko-dev-panel.service
```

After changing Python, HTML, or `projects.json`, restart the running service with `systemctl --user restart linko-dev-panel.service`. If only the service file changes, copy it again and run `systemctl --user daemon-reload` before restarting.

## Access

The panel has no login or TLS. Anyone who can reach its port over the network can use the controls. Restrict access with Tailscale ACLs or a firewall. Mutating requests use a per-process CSRF token and an origin check. There is no endpoint to supply a repository path or arbitrary Git command.
