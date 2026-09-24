# Dev Panel

**Version 1.1** · A small, phone-friendly web panel for managing a fixed list of local Git repositories. It runs on Python's standard library and calls your installed Git; there is no package install or build step.

## What it does

- Shows the selected repository's branch, changed files, commit history, and local ahead/behind status.
- Reviews and commits all local changes, then lets you push separately. Pull uses `git pull --ff-only`.
- Shows a tracked diff and lists untracked files. Discard restores only the listed **unstaged tracked** changes after confirmation; staged and untracked files stay.
- Compares a historical commit with the current branch, including file-by-file diffs. You can restore a historical tree by creating a new commit, or check out a commit temporarily in detached HEAD mode and return to a branch.
- Opens a live or committed website preview when a project has a configured HTML entry file. Projects without one still have all Git controls.

Actions apply only to repositories named in `projects.json`. The panel does not copy repositories or accept arbitrary paths from the browser.

## Quick start

You need **Python 3.10+**, **Git**, and at least one local Git repository. The checked-in `projects.json` contains paths for the original machine, so edit it before the first run on another computer. Replace its entries with your own absolute paths, for example:

```json
{
  "projects": {
    "My Project": {
      "path": "/home/you/projects/my-project",
      "remote": "origin",
      "preview": "index.html"
    }
  }
}
```

Then run:

```bash
./start.sh
```

Open <http://127.0.0.1:8765/>. By default, the server listens on localhost. If the example path does not exist or is not a Git repository root, startup fails with a configuration error.

`remote` defaults to `origin`. Use `null` for a local-only repository; push and remote comparison will be unavailable. `preview` is optional and must be a relative path to an HTML file in that repository. Remove it for projects without a website. Restart the server after changing `projects.json`.

## Configuration and access

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `LINKO_PANEL_HOST` | `127.0.0.1` | Address to listen on |
| `LINKO_PANEL_PORT` | `8765` | HTTP port |
| `LINKO_PANEL_ALLOWED_HOSTS` | Empty | Extra comma-separated hostnames accepted in requests |

These `LINKO_PANEL_` names are retained for compatibility with the original installation. To reach the panel from another device, bind to an address that device can reach and restrict access with a firewall or a private network such as Tailscale. **There is no login or TLS. Anyone who can reach the port can use the Git controls.** Mutating requests require a CSRF token and an origin check, but these do not replace network access control.

The included [`linko-dev-panel.service`](linko-dev-panel.service) is a systemd user service for the original installation. Before using it elsewhere, edit `WorkingDirectory`, `ExecStart`, and `LINKO_PANEL_HOST` in the file. Then install it:

```bash
mkdir -p ~/.config/systemd/user
cp linko-dev-panel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now linko-dev-panel.service
```

After changing Python, HTML, or `projects.json`, restart with `systemctl --user restart linko-dev-panel.service`. After changing the service file, copy it again and run `systemctl --user daemon-reload` before restarting.

## Git behavior

Commit stages all changes in the selected repository, including untracked files. Review the file list before confirming. Push is a separate action. Ahead/behind uses local remote-tracking data and may be stale until a pull or fetch elsewhere. Push targets the configured remote and current branch; pull requires an upstream on that remote.

Restoring a version requires a clean working tree and makes a **new commit** with the selected commit's files. Earlier commits remain in history, and the restore is not pushed automatically. Temporary historical checkout also requires a clean working tree. While detached, commit, push, pull, discard, and restore are unavailable; use **Return to current** to switch back to a branch. Preview serves only common web asset types and rejects hidden paths and paths outside the configured repository.

## Development

`server.py` handles HTTP and request checks, `repository.py` contains Git operations, `index.html` is the interface, and `projects.json` is the repository allowlist. Run the integration tests with:

```bash
python3 -m unittest discover -s tests -v
```

Licensed under the [MIT License](LICENSE).
