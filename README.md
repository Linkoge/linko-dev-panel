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

Each card's **Edit product page** button opens a full-width view of the existing page fields. It shares all pending catalogue edits; **Back (keep edits)** retains them. Description sections have large textareas with Bold/List controls, followed by specifications, included items and gallery/alt controls. Select ka/en/ru to edit localized fields. **Preview saved page** opens the last successfully saved generated page. The toolbar stays visible while scrolling. Saving includes pending card edits too. The existing navigation/reload warnings protect unsaved changes.

Direct editor links use `/?project=Linko&view=products&product=<product-id>`; for example `/?project=Linko&view=products&product=starlink-installation`. The detail template and optional localized `priceNote` field are supplied by the updated Linko generator. Older gallery path strings remain supported alongside image objects with localized alt text.

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

The browser terminal described below runs on a **Linux server**. Windows and Android can use it as browser clients. A panel hosted natively on Windows keeps its existing Git/product/preview features; opening Terminal explains that a Linux server is required.

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

## Browser terminal (Phase 1)

Select a configured repository and click **OPEN TERMINAL**. It opens a dedicated, full-window workspace in a new tab. It starts the user's normal Linux shell in that project's directory, or returns to whatever application is already running in its tmux session. Run `bash`, `python`, `git`, `htop`, a development agent, or another ordinary terminal application yourself. No agent is automatically launched, and no application-specific session model is used.

The architecture is **xterm.js → same-port WebSocket → real Linux PTY → tmux → shell/application**. `terminal_backend.py` attaches a temporary tmux client for each browser connection. Session creation uses process argument arrays, never a shell command assembled from browser input. The browser submits only a known project identity; the existing server project allowlist resolves and revalidates its canonical Git root. This phase adds no repository onboarding or image/file clipboard uploads.

### Dependencies and startup

On the Linux server, install **tmux** through your distribution's package manager (for Debian/Ubuntu: `sudo apt install tmux`). Then, from the panel directory:

```bash
python3 -m pip install -r requirements.txt
npm ci
```

Use a virtual environment when required by the distribution. `simple-websocket` (1.1.0, backed by wsproto) handles WebSocket framing, heartbeat and socket integration with the existing HTTP server. `ptyprocess` (0.7.0, Linux only) handles PTY creation, terminal dimensions and child cleanup. `@xterm/xterm` (6.0.0) supplies maintained terminal emulation and native browser paste handling; `@xterm/addon-fit` (0.11.0) measures browser terminal dimensions. npm assets are served locally from an explicit three-file allowlist; no CDN or browser network dependency is introduced. Node is needed to install these assets, but the terminal bridge runs in Python and tmux, without a Node server. Existing Pillow and Playwright dependencies are retained.

`start.sh`, `python3 server.py`, host/port settings, and existing project configuration continue to work. Restart the running panel after installing dependencies. If systemd uses a virtual environment, set `ExecStart` to that environment's Python, as described in Configuration and access.

The updated service template uses `KillMode=process`, allowing tmux and its applications to outlive a panel service restart. Existing installed units need the same setting (copy/reinstall the template or use a `[Service]` drop-in), followed by `systemctl --user daemon-reload` and a restart. With systemd's default `KillMode=control-group`, stopping/restarting a service can kill tmux even though browser disconnects do not. Preserving processes means stopping the panel does not stop applications already running inside tmux. To keep a user service running after the last Linux login ends, configure systemd user lingering according to your host's policy.

### Persistence, reconnects, and multiple devices

The dedicated tmux socket name is `linko-dev-panel` (`tmux -L linko-dev-panel ...`), separate from your default tmux server. Each session is named `project-` followed by the first 32 hexadecimal characters of SHA-256 over JSON containing the project name and canonical configured path. Names are deterministic and contain only safe characters; projects in different directories have different sessions. Renaming a project or moving its checkout creates a different mapping. The previous session remains until you end it yourself. `/api/terminal/status?project=...` reports availability and the mapped session name.

Closing or refreshing a tab, closing a client computer, changing devices, or losing Tailscale connectivity leaves tmux and its applications running on Linux. After an abnormal disconnect the page reconnects automatically with bounded backoff, or immediately through **Reconnect**. A normal tmux detach/application exit leaves the page disconnected until you click Reconnect. It gets a fresh connection ticket and attaches to the same session; tmux redraws the current screen. It does not replay pending terminal input after a disconnect: an explicit message warns that in-flight paste delivery may be partial. Check the application before sending that text again.

Two browsers attach as normal tmux clients to the same session. They share applications and input, rather than creating duplicate shells. tmux chooses pane dimensions according to its normal window-size policy; a phone or desktop can therefore change the shared display size. This is not a collaboration system. Wheel scrolling uses tmux copy mode; **Scroll history**, **PgUp**, **PgDn**, and **Esc** provide equivalent controls when a wheel is unavailable. Use Shift+drag to select visible terminal text when tmux mouse handling is active, or **Select all → Copy selection**. Normal tmux prefix commands use Ctrl+B, including `[` for copy mode and `d` to detach.

Temporary clients, PTY descriptors, tasks and WebSocket connections are cleaned up on disconnect. Heartbeats detect a silent network failure, and an unresponsive output consumer is disconnected after 45 seconds. There are at most 16 simultaneous bridges. tmux owns the session independently of these resources. Ending the last shell, explicitly killing the tmux session/server, Linux shutdown/reboot, or account/service policy can end persistent state; this is not disk-backed application restoration.

### Text clipboard and Android

Native browser paste (Ctrl+V, Ctrl+Shift+V where supported, or the browser/Android paste action) goes through xterm's paste event, the WebSocket and the PTY. It requires **no Linux X11 clipboard**, `xclip`, SSH clipboard, or server-side graphical environment. Newlines follow terminal conventions: LF and CRLF become carriage returns on the wire. Applications that enable bracketed paste receive its normal delimiters, protecting multiline text according to that application's behavior. Without bracketed paste, pasted newlines can execute commands just as they do in a normal terminal.

**Paste text** uses the browser Clipboard API when permitted. Plain HTTP on a Tailscale hostname/address generally lacks that API; in that case it opens a large text area where Windows/Android can paste normally, then **Send to terminal** passes the text through the same xterm input path. **Copy selection** similarly tries the browser API and falls back to a browser copy command. Select all is useful on touch devices. Clipboard permission denials are reported or handled with the paste dialog; server clipboard access is never substituted.

Input is UTF-8, split into 8 KiB chunks and acknowledged only after each full chunk is written to the PTY, including partial OS writes. Large pasted prompts are not silently truncated. The pending input limit is **16 MiB**: an input event that would exceed it is rejected in full with a visible message. Terminal output is acknowledged only after xterm processes it, limiting browser/bridge buffering. Scrollback remains bounded by xterm/tmux limits, as in a normal terminal.

The mobile layout responds to the visual viewport and Android's on-screen keyboard. Compact Esc, Tab, Ctrl+C, Ctrl+B, arrow and history keys cover missing keyboard controls. Physical-keyboard desktop use remains available. Mobile IME, selection gestures and clipboard menus vary by browser; use the paste dialog when direct terminal paste is awkward.

### Security and private deployment

**There is no application login, user authentication, or built-in TLS. Terminal access is full shell access as the Linux account running the panel.** CSRF tokens and one-use connection tickets are request protections, not authentication. Keep the panel bound to localhost or your Tailscale interface, restrict tailnet access to trusted devices/users with Tailscale ACLs, and do not port-forward it or publish it through a public proxy/Funnel.

The terminal requires the existing accepted Host, an exact same-origin HTTP Origin on ticket requests and WebSocket upgrades, and an actual TCP peer in localhost or Tailscale's IPv4/IPv6 ranges. It ignores forwarded peer/origin headers. Creating a ticket also requires the existing CSRF token. Tickets expire after 30 seconds, are project-bound and single-use, and are sent in the first WebSocket message instead of URLs/logs. No PTY or tmux session starts until the ticket is validated. Unknown projects, browser paths, command parameters, changed symlink directories and invalid terminal dimensions are rejected. The terminal page has a restrictive CSP and uses only local scripts.

IP range checks are an additional boundary, not proof of Tailscale identity: bind/firewall/ACL isolation remains essential. Reverse proxies are not configured by this phase; a local proxy would appear as a trusted loopback peer and must enforce its own private access boundary. Existing preview pages share the panel's origin, so configured repository HTML/JavaScript and terminal output must be trusted. Do not add untrusted projects or serve hostile content through the private panel.

### Verification

```bash
python3 -m unittest discover -s tests -v
node tests/test_scroll_plan.mjs
node tests/test_detail_editor.mjs
# Live localhost server + real tmux + Chrome, only disposable test projects:
PANEL_TEST_PYTHON=.venv/bin/python node tests/test_terminal_browser.mjs
```

The browser suite checks correct cwd, shell input, rendered ANSI colors, wheel/copy-mode scrolling, Ctrl+C, PTY resize, native browser clipboard copy and Ctrl+V, exact UTF-8 paste receipt for short text/paragraph/code/Unicode/Georgian and a large multiline prompt, a curses TUI surviving refresh/offline/reopen, two simultaneous clients, repeated reconnects, and child/descriptor cleanup. It also covers missing connection authorization, cross-origin rejection, mobile layout/paste fallback and existing read-only HTTP routes. Tests use a unique disposable tmux socket; cleanup never kills real project sessions. Set `LINKO_PANEL_CHROME` if Chrome is elsewhere, and `PANEL_TEST_PYTHON` to the Python that has requirements installed. Native Windows and physical Android clipboard/IME behavior still require device checks; Chrome mobile emulation does not establish those results.

Phase 1 verification passed the live browser suite, including a **1,032,890-byte** multiline paste with exact content comparison, native Ctrl+V and browser copy (including the fallback with the Clipboard API disabled), abrupt TCP disconnect with automatic reconnect, normal tmux detach, oversized-paste rejection, and cleanup with no remaining PTY children/zombies or descriptor growth. It passed with `DISPLAY`, `WAYLAND_DISPLAY` and `XAUTHORITY` cleared. The Python suite passed **41 of 42** tests. The remaining pre-existing `test_detail_workflow` fixture does not copy the `sitemap.py` module now imported by the sibling Linko generator; that unrelated fixture was left unchanged. Both existing JavaScript suites passed. The installed private service also passed terminal/selector/cwd/cleanup/persistence and read-only status, history, diff, preview and catalogue smoke checks; the same tmux pane survived an actual service restart. `tests/test_terminal_live.mjs` optionally repeats that installed-service check; it expects the configured Dev Panel project and leaves its shell session persistent. Its `--restart` option additionally restarts the service (only if no capture is active) to verify tmux survival.

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
