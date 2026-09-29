# Dev Panel

**Version 1.4.0** · A phone-friendly web panel for managing a fixed list of local Git repositories and capturing website screenshots. The server uses Python's standard library and your installed Git. Screenshot capture uses Playwright and Chrome or Chromium.

## What it does

- Shows the selected repository's branch, changed files, commit history, and local ahead/behind status.
- Reviews and commits all local changes, then lets you push separately. Pull uses `git pull --ff-only`.
- Shows a tracked diff and lists untracked files. Discard restores only the listed **unstaged tracked** changes after confirmation; staged and untracked files stay.
- Compares a historical commit with the current branch, including file-by-file diffs. You can restore a historical tree by creating a new commit, or check out a commit temporarily in detached HEAD mode and return to a branch.
- Opens a live or committed website preview when a project has a configured HTML entry file. Projects without one still have all Git controls.
- Captures Mobile (390 × 844), Desktop (1440 × 900), or Both as overlapping viewport PNGs after scrolling the page in a real browser. The Screenshots view previews and downloads the images.

Actions apply only to repositories named in `projects.json`. The panel does not copy repositories or accept arbitrary paths from the browser.

## Linko Products editor

The Linko project has `"catalogue": true` in `projects.json`, which enables the private **Products** tab for that project only. It edits the catalogue that supplies product, service, and package cards, one-level categories, and optional generated detail pages. You can change titles, prices, availability, visibility, links, descriptions, specifications, galleries, and images; add or duplicate hidden drafts; and reorder cards or category entries. Hidden items can be included while editing. Removing a product from a category removes only its membership, not the product itself.

**Save & Generate** validates the complete catalogue, writes its JSON source files, and regenerates the static HTML pages. A stale editor tab is rejected and must be reloaded. **Preview HTML** opens the local generated page. Saving does not commit, push, or deploy. Use the Repository tab to review and commit, then explicitly push; commit preparation and push check that generated catalogue HTML is current. Other configured projects keep their existing behavior.

The image picker can search approved project images and upload new images (up to 8 MB) to the Linko project's `assets/product-images/` folder. Upload validation requires Python Pillow (`python3 -m pip install Pillow` if it is not already available). The panel uses its existing private-network access, CSRF token, origin check, and configured project allowlist. It has no login; keep its port restricted to trusted devices. See the Linko repository's `docs/catalogue-editor.md` for editing, watcher, recovery, and publishing instructions.

## Quick start

You need **Python 3.10+**, **Git**, and at least one local Git repository. To use the commit and restore controls, configure `user.name` and `user.email` in Git. Screenshot capture also needs **Node.js 20+**, **Google Chrome or Chromium**, and the Playwright package. Install the package from the panel directory with:

```bash
npm ci
```

The checked-in `projects.json` contains paths for the original machine. Edit it before the first run on another computer. Replace its entries with your own absolute repository paths and existing HTML pages, for example:

```json
{
  "projects": {
    "My Project": {
      "path": "/home/you/projects/my-project",
      "remote": "origin",
      "preview": "index.html",
      "capturePages": ["about.html", "products.html"]
    }
  }
}
```

Then run:

```bash
./start.sh
```

Open <http://127.0.0.1:8765/>. By default, the server listens on localhost. A project path must exist and be a Git repository root; configured HTML pages must also exist inside it. Invalid configuration stops the server at startup.

`remote` defaults to `origin`. Use `null` for a local-only repository; push, pull, and remote comparison will be unavailable. `preview` is optional and must be a relative path to an HTML file in the repository. `capturePages` is an optional list of additional relative HTML pages available for screenshots; the `preview` page is always included. `capturePages` requires `preview`. Omit both for projects without a website. Restart the server after changing `projects.json`.

## Screenshots

Select a project, open **Screenshots**, choose a configured page and screen size, then click **Capture Screenshots**. The screenshot count depends on the selected page's length. Overlap defaults to 20% and can be set from 0% to 50%. The wait after each scroll defaults to 1300 ms and can be set from 300 to 2500 ms. Each screen size is limited to 100 viewport images; the panel warns if that limit truncates a capture. Only one capture can run at a time across all projects.

A capture continues if you close or refresh the panel while the server stays running. The latest successful session is saved separately for each configured page under the Git-ignored `screenshots/` directory. Changing the page selector shows only that page's saved screenshots; capture that page if none are saved yet. A failed capture leaves that page's previous successful session in place. **Clear saved screenshots** deletes only the selected page's session. **Download Selected** requests one PNG download per selected image; if your browser blocks multiple downloads, use the individual **Download PNG** buttons. Screenshots are stored locally and are not uploaded by the panel.

The panel captures only HTML pages explicitly listed in `projects.json`; it does not accept arbitrary capture URLs. The optional Python Pillow package improves duplicate-image filtering. Without it, only byte-identical neighboring images can be removed.

## Configuration and access

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `LINKO_PANEL_HOST` | `127.0.0.1` | Address to listen on |
| `LINKO_PANEL_PORT` | `8765` | HTTP port |
| `LINKO_PANEL_ALLOWED_HOSTS` | Empty | Extra comma-separated hostnames accepted in requests |
| `LINKO_PANEL_NODE` | `node` on `PATH`, then an NVM installation | Node executable used for screenshots |
| `LINKO_PANEL_CHROME` | `google-chrome` or `chromium` on `PATH` | Browser executable used for screenshots |

These `LINKO_PANEL_` names are retained for compatibility with the original installation. To reach the panel from another device, bind to an address that device can reach and restrict access with a firewall or a private network such as Tailscale. **There is no login or TLS. Anyone who can reach the port can use the Git controls.** Mutating requests require a CSRF token and an origin check, but these do not replace network access control.

The included [`linko-dev-panel.service`](linko-dev-panel.service) is a systemd user service for the original installation. Before using it elsewhere, edit `WorkingDirectory`, `ExecStart`, and the environment variables in the file, especially `LINKO_PANEL_HOST` and `LINKO_PANEL_NODE`. Then install it:

```bash
mkdir -p ~/.config/systemd/user
cp linko-dev-panel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now linko-dev-panel.service
```

After changing Python, HTML, or `projects.json`, restart with `systemctl --user restart linko-dev-panel.service`. After changing the service file, copy it again and run `systemctl --user daemon-reload` before restarting. Restarting during a capture interrupts it.

## Git behavior

Commit stages all changes in the selected repository, including untracked files. Review the file list before confirming. Push is a separate action. Ahead/behind uses local remote-tracking data and may be stale until a pull or fetch elsewhere. Push targets the configured remote and current branch; pull requires an upstream on that remote.

Restoring a version requires a clean working tree and makes a **new commit** with the selected commit's files. Earlier commits remain in history, and the restore is not pushed automatically. Temporary historical checkout also requires a clean working tree. While detached, commit, push, pull, discard, and restore are unavailable; use **Return to current** to switch back to a branch. Preview serves only common web asset types and rejects hidden paths and paths outside the configured repository.

## Development

`server.py` handles HTTP and request checks, `repository.py` contains Git operations, `index.html` is the interface, and `projects.json` is the repository allowlist. `screenshots.py` manages capture jobs and saved sessions; `capture.mjs` and `scroll_plan.mjs` drive the browser. Run the Python integration and JavaScript scroll-plan tests with:

```bash
python3 -m unittest discover -s tests -v
node tests/test_scroll_plan.mjs
```

Licensed under the [MIT License](LICENSE).
