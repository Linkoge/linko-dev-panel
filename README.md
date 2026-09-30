# Dev Panel

**Version 1.5.0** · A phone-friendly web panel for managing a fixed list of local Git repositories and capturing website screenshots. It runs natively on Windows 10/11 and Linux. The HTTP server uses Python's standard library and your installed Git; image validation uses Pillow. Screenshot capture uses Playwright and Chrome or Chromium.

## What it does

- Shows the selected repository's branch, changed files, commit history, and local ahead/behind status.
- Reviews and commits all local changes, then lets you push separately. Pull uses `git pull --ff-only`.
- Shows a tracked diff and lists untracked files. Discard restores only the listed **unstaged tracked** changes after confirmation; staged and untracked files stay.
- Compares a historical commit with the current branch, including file-by-file diffs. You can restore a historical tree by creating a new commit, or check out a commit temporarily in detached HEAD mode and return to a branch.
- Opens a live or committed website preview when a project has a configured HTML entry file. Projects without one still have all Git controls.
- Captures Mobile (390 × 844), Desktop (1440 × 900), or Both as overlapping viewport PNGs after scrolling the page in a real browser. The Screenshots view previews and downloads the images.

Actions apply only to repositories in the configured project allowlist. The panel reads and writes directly in those local checkouts, including files and images you add manually. GitHub remains the Git remote; the panel does not copy repositories or accept arbitrary paths from the browser.

## Linko Products editor

The Linko project has `"catalogue": true` in its project settings, which enables the private **Products** tab for that project only. It edits the catalogue that supplies product, service, and package cards, one-level categories, and optional generated detail pages. You can change titles, prices, availability, visibility, links, descriptions, specifications, galleries, and images; add or duplicate hidden drafts; and reorder cards or category entries. Hidden items can be included while editing. Removing a product from a category removes only its membership, not the product itself.

**Save & Generate** validates the complete catalogue, writes its JSON source files, and regenerates the static HTML pages. A stale editor tab is rejected and must be reloaded. **Preview HTML** opens the local generated page. Saving does not commit, push, or deploy. Use the Repository tab to review and commit, then explicitly push; commit preparation and push check that generated catalogue HTML is current. Other configured projects keep their existing behavior.

The image picker can search approved project images and upload new images (up to 8 MB) to the Linko project's `assets/product-images/` folder. Pillow is installed with `requirements.txt`. The panel uses its existing CSRF token, origin check, and configured project allowlist. It has no login; keep its port restricted to trusted devices. See the Linko repository's `docs/catalogue-editor.md` for editing, recovery, and publishing instructions.

The panel loads `catalogue.py` from the selected Linko checkout. On Windows, a scoped adapter supplies exclusive file locking for older generators that import Linux-only `fcntl`; it uses Python's [native Windows locking API](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking). Generated manifest paths remain in forward-slash form. Linux retains the generator's native locking. This adapter applies to generator calls made by the panel; it does not rewrite Linko's generator or make its standalone CLI/watch command portable.

## Quick start on Linux

You need **Python 3.10+**, **Git**, and your existing local Linko checkout. Install the Python dependency from the panel directory:

```bash
python3 -m pip install -r requirements.txt
```

If your Linux distribution requires a virtual environment, create one with `python3 -m venv .venv`, activate it with `source .venv/bin/activate`, then run that installation command. To use commit and restore, configure `user.name` and `user.email` in Git. Screenshot capture additionally needs **Node.js 20+**, **Google Chrome or Chromium**, and Playwright:

```bash
npm ci
```

The checked-in `projects.json` expects Linko in `../Linko` and the panel in `.` relative to that configuration file. This preserves the original Linux sibling-directory layout. For another Linko location, set:

```bash
export LINKO_REPO_PATH="$HOME/projects/Linko"
```

Alternatively, copy `projects.json` to Git-ignored `projects.local.json` and edit that file. Paths can be absolute or relative to the configuration file's directory. For example:

```json
{
  "projects": {
    "My Project": {
      "path": "../my-project",
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
# Or: python3 server.py
```

Open <http://localhost:8765/>. By default, the server listens on localhost. It prints each resolved repository path at startup. A project path must exist and be a Git working-tree root; configured HTML pages must exist inside it. A catalogue project must contain `catalogue.py`, `data/catalog.json`, `data/products/`, and `templates/products.html`. Invalid configuration stops startup with a readable error.

`remote` defaults to `origin`. Use `null` for a local-only repository; push, pull, and remote comparison will be unavailable. `preview` is optional and must be a relative path to an HTML file in the repository, using forward slashes. `capturePages` is an optional list of additional relative HTML pages available for screenshots; the `preview` page is always included. `capturePages` requires `preview`. Omit both for projects without a website. Restart after changing project settings or environment variables.

## Running on Windows

1. Install **Python 3.10+** and **Git for Windows**, with `python` and `git` available on `PATH`. Open a new PowerShell window and check `python --version` and `git --version`. Use your existing Windows Linko working tree, or clone Linko once if you do not have it yet. This is the checkout both you and the panel will edit. No WSL, Docker, VM, or Tailscale is required.
2. Clone the panel and install its Python dependency:

   ```powershell
   git clone https://github.com/Linkoge/linko-dev-panel.git
   cd linko-dev-panel
   python -m pip install -r requirements.txt
   ```

3. Configure the **existing local Linko checkout**. Replace the example below with its actual location; spaces and non-ASCII folder names are supported:

   ```powershell
   $env:LINKO_REPO_PATH = 'D:\projects\Linko'
   git -C "$env:LINKO_REPO_PATH" rev-parse --show-toplevel
   git -C "$env:LINKO_REPO_PATH" remote -v
   ```

   This environment variable lasts for the current PowerShell session and overrides the `Linko` entry's path. For persistent settings that also work when double-clicking the launcher, run `Copy-Item projects.json projects.local.json`, then `notepad projects.local.json`. Set Linko's `path`, for example to `"D:/projects/Linko"`. JSON also accepts escaped backslashes (`"D:\\projects\\Linko"`). Keep `"catalogue": true` and point `preview` / `capturePages` to pages that exist in your checkout. The supplied Linko defaults are `xsecret.html`, `products.html`, and `settlements.html`. The Dev Panel entry's `"path": "."` points to the panel itself.
4. Configure Git identity if needed:

   ```powershell
   git -C "$env:LINKO_REPO_PATH" config user.name "Your Name"
   git -C "$env:LINKO_REPO_PATH" config user.email "you@example.com"
   ```

   Set up GitHub authentication using your usual Git for Windows credentials or SSH key. The panel disables terminal credential prompts; complete any required authentication from a terminal first.
5. Start the panel from its directory:

   ```powershell
   python server.py
   ```

   You can also run `start-dev-panel.bat`. Check that the printed **Linko** path is your intended checkout, then open **<http://localhost:8765/>**. Stop with Ctrl+C. Files and images added manually to this same checkout appear in local Git status and the approved image picker; reload the Products editor after manually editing its JSON.

Screenshot capture is optional. To retain that feature, install Node.js 20+ and Google Chrome or Chromium, then run `npm ci` in the panel directory. Chrome is detected from `PATH` or standard Windows machine/user installation folders. For custom installations, set `LINKO_PANEL_CHROME` to the full `chrome.exe` path and/or `LINKO_PANEL_NODE` to the full `node.exe` path. Normal preview and product editing do not need Node or Chrome.

Common Windows errors:

- **Python/Git command not found:** install them with command-line access enabled and reopen the terminal. If only the Python launcher is available, use `py -3 -m pip install -r requirements.txt` and `py -3 server.py`.
- **Pillow is missing:** run `python -m pip install -r requirements.txt` using the same Python that starts the server.
- **Repository missing / wrong layout / not a Git root:** check the startup error and your selected settings. Configure the checkout root, which contains the Linko catalogue files and `.git` (a directory or worktree file), rather than a nested asset directory.
- **Bad JSON / backslash escape error:** use forward slashes in JSON paths, or escape every backslash. PowerShell environment-variable strings use ordinary backslashes.
- **Access denied:** use a checkout your Windows account can write to; close programs holding an affected file open and retry.
- **Address already in use / WinError 10048:** stop the other server using port 8765, or explicitly set `$env:LINKO_PANEL_PORT = '8766'` and open that port.
- **Push authentication failure:** verify the configured remote and authenticate Git from a terminal before retrying in the panel.

Manual Windows check: add an image under Linko's `assets/product-images/` in Explorer; select **Linko → Products**, choose that image, edit a product, and **Save & Generate**. Confirm its JSON and generated HTML changed in that exact checkout. Open **Preview HTML**, then use **Repository → Commit changes** to review and confirm. Verify the commit with `git -C "$env:LINKO_REPO_PATH" log -1`, then **Push commits** and confirm it on GitHub. Commit still stages all local changes, so review the entire file list.

## Screenshots

Select a project, open **Screenshots**, choose a configured page and screen size, then click **Capture Screenshots**. The screenshot count depends on the selected page's length. Overlap defaults to 20% and can be set from 0% to 50%. The wait after each scroll defaults to 1300 ms and can be set from 300 to 2500 ms. Each screen size is limited to 100 viewport images; the panel warns if that limit truncates a capture. Only one capture can run at a time across all projects.

A capture continues if you close or refresh the panel while the server stays running. The latest successful session is saved separately for each configured page under the Git-ignored `screenshots/` directory. Changing the page selector shows only that page's saved screenshots; capture that page if none are saved yet. A failed capture leaves that page's previous successful session in place. **Clear saved screenshots** deletes only the selected page's session. **Download Selected** requests one PNG download per selected image; if your browser blocks multiple downloads, use the individual **Download PNG** buttons. Screenshots are stored locally and are not uploaded by the panel.

The panel captures only HTML pages explicitly listed in the selected project settings; it does not accept arbitrary capture URLs. Pillow also improves duplicate-image filtering.

## Configuration and access

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `LINKO_REPO_PATH` | Linko's configured path | Override the `Linko` checkout location |
| `LINKO_PANEL_CONFIG` | `projects.local.json` if present, otherwise `projects.json` | Project settings file; an explicit relative filename is resolved from the launch directory |
| `LINKO_PANEL_HOST` | `127.0.0.1` | Address to listen on |
| `LINKO_PANEL_PORT` | `8765` | HTTP port |
| `LINKO_PANEL_ALLOWED_HOSTS` | Empty | Extra comma-separated hostnames accepted in requests |
| `LINKO_PANEL_NODE` | `node` on `PATH`, then an NVM installation | Node executable used for screenshots |
| `LINKO_PANEL_CHROME` | Chrome/Chromium on `PATH` or standard Windows installation folders | Browser executable used for screenshots |

Selection order is an explicit `LINKO_PANEL_CONFIG`, then local settings, then checked-in settings. `LINKO_REPO_PATH` overrides only the entry named `Linko`; other configured projects keep their own paths. Relative repository paths resolve beside the selected configuration file. Local settings replace the complete allowlist, so retain any projects you want available. Neither a `.env` file nor environment changes in another terminal are loaded automatically.

These `LINKO_PANEL_` names are retained for compatibility with the original installation. To reach the panel from another device, bind to an address that device can reach and restrict access with a firewall or a private network such as Tailscale. **There is no login or TLS. Anyone who can reach the port can use the Git controls.** Mutating requests require a CSRF token and an origin check, but these do not replace network access control.

The included [`linko-dev-panel.service`](linko-dev-panel.service) is a systemd user-service template. It uses `%h` for the user's home directory and assumes the panel is in `~/projects/dev-panel`. Adjust `WorkingDirectory` and `ExecStart` if needed; a virtual environment requires its Python in `ExecStart`. Set `Environment=LINKO_REPO_PATH=...` if Linko is elsewhere. Set `LINKO_PANEL_HOST` and `LINKO_PANEL_ALLOWED_HOSTS` as needed for LAN/Tailscale access; these remain supported. A custom Node installation can use `LINKO_PANEL_NODE`. Existing installed services are not changed by updating this repository. Then install it:

```bash
mkdir -p ~/.config/systemd/user
cp linko-dev-panel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now linko-dev-panel.service
```

After changing Python, HTML, or project settings, restart with `systemctl --user restart linko-dev-panel.service`. After changing the service file, copy it again and run `systemctl --user daemon-reload` before restarting. Restarting during a capture interrupts it.

## Git behavior

Commit stages all changes in the selected repository, including untracked files. Review the file list before confirming. Push is a separate action. Ahead/behind uses local remote-tracking data and may be stale until a pull or fetch elsewhere. Push targets the configured remote and current branch; pull requires an upstream on that remote.

Restoring a version requires a clean working tree and makes a **new commit** with the selected commit's files. Earlier commits remain in history, and the restore is not pushed automatically. Temporary historical checkout also requires a clean working tree. While detached, commit, push, pull, discard, and restore are unavailable; use **Return to current** to switch back to a branch. Preview serves only common web asset types and rejects hidden paths and paths outside the configured repository.

## Development

`server.py` handles HTTP and request checks; `repository.py` contains project configuration, portable preview URLs, and Git operations. `catalogue_backend.py` calls the selected checkout's generator through `catalogue_compat.py`. `index.html` is the interface, and `projects.json` is the default repository allowlist. `screenshots.py` manages capture jobs and saved sessions; `capture.mjs` and `scroll_plan.mjs` drive the browser. Run the Python integration and JavaScript scroll-plan tests with:

```bash
python3 -m unittest discover -s tests -v
node tests/test_scroll_plan.mjs
```

On Windows, use `python` instead of `python3`. Tests use disposable Git repositories and fixed catalogue fixtures; a sibling Linko checkout is not required. `test_cross_platform.py` covers Windows-style paths, URL encoding, shell-free Git execution with explicit working directories, configurable checkout selection, startup errors, Windows browser discovery, and catalogue locking. The native lock test exercises Windows locking when run on Windows, and Linux locking on Linux. Symlink-specific tests require Windows Developer Mode or equivalent permission; only those checks skip if that permission is unavailable.

The compatibility work was verified automatically on Linux with the Python and JavaScript suites, including HTTP handler integration tests. Windows paths and the Windows adapter are also exercised with portable representations/mocks on Linux. This verification environment denies listening sockets, so live server startup could not be tested here. Native Windows execution, Windows browser capture, and GitHub authentication/push from your PC require the manual Windows check above; Linux verification does not establish that those Windows runtime checks have run.

Licensed under the [MIT License](LICENSE).
