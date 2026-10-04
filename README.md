# Dev Panel

**Version 1.5.0** · A phone-friendly web panel for onboarding and managing local Git repositories and capturing website screenshots. It runs natively on Windows 10/11 and Linux. The HTTP server uses Python's standard library and your installed Git; image validation uses Pillow. Screenshot capture uses Playwright and Chrome or Chromium.

## What it does

- Shows the selected repository's branch, changed files, commit history, and local ahead/behind status.
- Clones SSH/HTTPS repositories through **+ Add Project** and automatically discovers Git projects in the projects directory.
- Reviews and commits all local changes, then lets you push separately. Pull uses `git pull --ff-only`.
- Shows a tracked diff and lists untracked files. Discard restores only the listed **unstaged tracked** changes after confirmation; staged and untracked files stay.
- Compares a historical commit with the current branch, including file-by-file diffs. You can restore a historical tree by creating a new commit, or check out a commit temporarily in detached HEAD mode and return to a branch.
- Opens a live or committed website preview when a project has a configured HTML entry file. Projects without one still have all Git controls.
- Captures Mobile (390 × 844), Desktop (1440 × 900), or Both as overlapping viewport PNGs after scrolling the page in a real browser. The Screenshots view previews and downloads the images.

Actions apply to the server's registry of configured and discovered repositories. The panel reads and writes directly in those local checkouts, including files and images you add manually. GitHub and other Git providers work through standard Git URLs; the browser cannot choose arbitrary local paths.

## Linko Products editor

The Linko project has `"catalogue": true` in its project settings, which enables the private **Products** tab for that project only. It edits the catalogue that supplies product, service, and package cards, one-level categories, and optional generated detail pages. You can change titles, prices, availability, visibility, links, descriptions, specifications, galleries, and images; add or duplicate hidden drafts; and reorder cards or category entries. Hidden items can be included while editing. Removing a product from a category removes only its membership, not the product itself.

Each card's **Edit product page** button opens a full-width view of the existing page fields. It shares all pending catalogue edits; **Back (keep edits)** retains them. Description sections have large textareas with Bold/List controls, followed by specifications, included items and ordered product-image controls. Select ka/en/ru to edit localized fields. **Preview saved page** opens the last successfully saved generated page. The toolbar stays visible while scrolling. Saving includes pending card edits too. The existing navigation/reload warnings protect unsaved changes.

Direct editor links use `/?project=Linko&view=products&product=<product-id>`; for example `/?project=Linko&view=products&product=starlink-installation`. The detail template and optional localized `priceNote` field are supplied by the updated Linko generator. Legacy image objects and gallery path strings remain readable without reopening or resaving products.

With Linko catalogue schema v2, **Add Product**, **Add Service** and **Add Package**
create pending drafts. The server assigns a read-only permanent Pxx/Sxx ID on the
first successful save; duplicates get a new identity. Ordering remains separate.
The editor displays IDs, editable Latin slugs, **Suggest slug**, and generated URLs.
Blank draft slugs are generated from English/Latin title words on save. Existing
names, prices, images, visibility and order can be edited without changing identity.
New direct editor links use `product=P01`; old-ID bookmarks still resolve.

Saved previews follow `/products/P01-starlink-standard-4x` or `/services/S01-…`,
prefixed with `/en` or `/ru` for those languages, inside the panel's project scope.
Current and historical previews resolve clean routes. Incomplete translated pages
remain non-indexable until complete. Historical catalogue views are read-only.
Catalogue restoration retains current routing infrastructure/templates and issued
IDs/aliases while restoring item content, order and assets; it then regenerates
and creates the normal restore commit. The website's ignored issuance ledger also
preserves numbers across discarded edits. Copy it when moving the authoritative
editing checkout; use one panel checkout for ID allocation. Other projects and
older catalogue schemas retain their existing behavior.

**Save & Generate** validates the complete catalogue, writes its JSON source files, and regenerates the static HTML pages. A stale editor tab is rejected and must be reloaded. **Preview HTML** opens the local generated page. Saving does not commit, push, or deploy. Use the Repository tab to review and commit, then explicitly push; commit preparation and push check that generated catalogue HTML is current. Other configured projects keep their existing behavior.

Product images use one ordered `images` array of objects, for example:

```json
"images": [
  {"path": "assets/product-images/front.jpg", "alt": {"ka": "Front"}, "width": 800, "height": 600, "presentation": "cover"},
  {"path": "assets/product-images/side.jpg", "alt": {"ka": "Side"}, "width": 600, "height": 800}
]
```

`images[0]` is the primary/cover image used by catalogue cards. **Manage images** on a card opens the existing product-page editor. **Product images** shows numbered thumbnails and marks the primary cover. **+ Add image** opens the existing picker/upload dialog and appends an image. **Choose image** replaces that individual entry while keeping its alt text. Reorder with desktop drag/drop, **Move left/right**, or **Make primary**; the explicit buttons work on touch screens. Save & Generate persists the order. At least one image is required. **Remove image** removes only the product reference: asset files are never deleted by this control, including shared assets and unused uploads.

Legacy products retain `image`, optional `image.secondary`, and `gallery` until their images are edited. A shared accessor reads them in that order; an image edit converts that product to `images`, preserving the original cover, all references, localized alt text and image metadata, and removes the old fields. Editing unrelated product fields does not migrate images. Legacy paired-card presentation stays intact until image editing; canonical arrays show one cover on cards. The compatibility loader projects arrays in memory for older checkout generators without writing duplicate fields. Update the Linko generator for the current public gallery behavior.

Generated detail pages and saved-page previews use the same existing gallery. A single image has no thumbnail strip. Multiple images have selectable thumbnails with a visible selected state and fit within a stable desktop/mobile image area without stretching or cropping. Broken gallery images are disabled; remaining images still work. If all images fail at runtime, a stable localized placeholder remains. New-array secondary paths may be missing while still subject to path/asset checks; the cover must exist at save/build time. Older generators retain their existing stricter file validation and detail layout.

The image picker can search approved project images and upload new images (up to 8 MB) to the Linko project's `assets/product-images/` folder. Pillow is installed with `requirements.txt`. The panel uses its existing CSRF token, origin check, and configured project allowlist. It has no login; keep its port restricted to trusted devices. See the Linko repository's `docs/catalogue-editor.md` for editing, recovery, and publishing instructions.

The panel loads `catalogue.py` from the selected Linko checkout. On Windows, a scoped adapter supplies exclusive file locking for older generators that import Linux-only `fcntl`; it uses Python's [native Windows locking API](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking). Generated manifest paths remain in forward-slash form. Linux retains the generator's native locking. This adapter applies to generator calls made by the panel; it does not rewrite Linko's generator or make its standalone CLI/watch command portable.

## Quick start on Linux

This is the installation runbook for AI agents as well as humans. When asked to set up the panel, complete dependency installation, project configuration, persistent startup, and the checks below. Report the resulting browser URL and any feature that remains unavailable. Use the existing checkout and inspect any installed service before changing it; preserve its project paths and custom environment settings.

### 1. Install dependencies

Run as the Linux account that owns the repositories. You need **Python 3.10+**, **Git**, and the local repositories you want to manage. The browser terminal also needs **tmux**, **Node.js 20+**, and **npm** to install its browser assets. Screenshot capture additionally needs **Google Chrome or Chromium**. Node does not run the panel server.

Check the available commands first:

```bash
python3 --version
git --version
tmux -V
node --version
npm --version
```

On Debian/Ubuntu, install missing packages using the host's package manager, for example:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv git tmux nodejs npm curl
```

Verify that the installed Node version is at least 20. If the distribution provides an older version, install a supported Node LTS release from [Node.js](https://nodejs.org/en/download). For an installation without root access, its official Linux archive can be extracted under `~/.local/share/dev-panel/`; verify it against the release's `SHASUMS256.txt`, choose the host's architecture, and add the extracted `bin` directory to `PATH` before running npm. Reuse an existing suitable installation rather than installing a second copy. A user-installed Node also needs an explicit path in the service settings below.

Use the existing panel checkout. For a new installation, the standard layout is `~/projects/linko-dev-panel`; clone `git@github.com:Linkoge/linko-dev-panel.git` there if the owner's existing SSH setup has access. HTTPS cloning from `https://github.com/Linkoge/linko-dev-panel.git` also works, but pushing needs a noninteractive credential helper. A successful public clone does not verify push authentication. Preserve working remotes in existing checkouts. From the actual panel directory, install into a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
```

`npm ci` is required for the browser terminal even if screenshot capture is unused. Install Chrome/Chromium through the host's supported installation method if screenshots are needed. Set `LINKO_PANEL_CHROME` to its absolute executable path if it is not on `PATH`. Normal Git controls, products, previews, and terminals do not need Chrome. The screenshot code uses this Chrome/Chromium executable; installing Playwright's bundled browser alone does not configure it.

### 2. Configure the repositories

The checked-in `projects.json` expects Linko in `../Linko` and the panel in `.` relative to that configuration file. This preserves the original Linux sibling-directory layout. For another Linko location, set:

```bash
export LINKO_REPO_PATH="$HOME/projects/Linko"
```

Alternatively, copy `projects.json` to Git-ignored `projects.local.json` if a local configuration does not already exist, and configure the intended repositories there. Paths can be absolute or relative to the configuration file's directory. Local settings replace the configured entries; automatic discovery adds eligible repositories from the projects directory. If Linko is absent, remove its entry from the local configuration and retain the repositories that exist; no Linko checkout is required for projects without catalogue features. An empty `"projects": {}` also works for an installation using discovery and Add Project. For example:

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

The projects directory defaults to the panel checkout's parent, normally `~/projects`. Verify it is the intended directory for discovery and cloning; set `LINKO_PROJECTS_DIR` or the local configuration's `projectsDirectory` to override it. It must exist and be writable for cloning. Preserve explicit settings for repositories needing previews or catalogue features; discovered repositories have Git and terminal controls without those extra settings. See [Add Project and discovery](#add-project-and-discovery-phase-2) for details.

To use commit and restore, ensure `user.name` and `user.email` are configured in Git. Reuse the owner's existing identity; do not invent one. Push/pull additionally need working remote authentication, configured through the owner's normal Git credentials or SSH setup. The panel disables interactive Git credential prompts.

#### Git authentication checks

Check every repository whose push support you are setting up, including **Dev Panel** itself. Repositories can use different authentication: a working Linko push does not verify Dev Panel's push. Inspect both fetch and push URLs, the configured credential helper and any SSH agent. Run checks as the account running the panel, with the actual service's environment (including `HOME`, `PATH` and `SSH_AUTH_SOCK` when used). A login shell or coding agent can have credentials the systemd service cannot access. Inspect configuration and availability without printing tokens, private keys or the full process environment.

From the intended repository, substitute its configured remote if it is not `origin`:

```bash
git remote get-url origin
git remote get-url --push --all origin
panel_git_branch=$(git branch --show-current)
if [ -n "$panel_git_branch" ]; then
  GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes -oStrictHostKeyChecking=yes' \
    git push --dry-run origin "HEAD:refs/heads/$panel_git_branch"
fi
```

These commands assume ordinary SSH configuration; preserve any existing custom `GIT_SSH_COMMAND` and add the batch/host-key options to it instead of replacing it. A detached checkout cannot use the panel's push control; return to its current branch before checking. A dry run checks authentication and the proposed update without publishing commits. It does not guarantee that a later push will pass all server-side checks. Reading or cloning a public HTTPS repository does not test write access.

If push reports `fatal: could not read Username for 'https://github.com': terminal prompts disabled`, HTTPS credentials are unavailable to that Git process. The commit can still have succeeded locally. Keep prompts disabled and reuse the owner's credential helper or existing SSH setup. When switching to SSH, first verify a push dry run to the **same owner/repository**, then update the affected remote and repeat the configured-remote check. For this panel's repository, when it has no separate push URL:

```bash
panel_git_branch=$(git branch --show-current)
if [ -n "$panel_git_branch" ] && \
  GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes -oStrictHostKeyChecking=yes' \
    git push --dry-run git@github.com:Linkoge/linko-dev-panel.git "HEAD:refs/heads/$panel_git_branch"; then
  git remote set-url origin git@github.com:Linkoge/linko-dev-panel.git
  GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes -oStrictHostKeyChecking=yes' \
    git push --dry-run origin "HEAD:refs/heads/$panel_git_branch"
fi
```

Preserve separate push URLs and other remotes; changing the fetch URL alone does not replace an explicit push URL. Never put tokens in remote URLs or service files. Git remote changes take effect on the next operation without restarting the panel. Do not publish pending commits merely to test setup.

**Verify publication separately.** History in the panel lists local commits. Ahead/behind counts use local remote-tracking refs and can be stale. After an explicitly requested real push, compare `git rev-parse HEAD` with `git ls-remote <push-url> refs/heads/<current-branch>` using the actual push destination. Matching hashes confirm that branch points to the local commit; a failed push must be reported as failed, with any local commits still pending.

Validate the configuration without starting a server:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from project_onboarding import ProjectRegistry, projects_directory
from repository import configuration_path, load_projects
panel = Path.cwd()
config = configuration_path(panel)
registry = ProjectRegistry(projects_directory(panel, config), load_projects(config))
print(f"Projects directory: {registry.root}")
for name, project in registry.refresh().items():
    print(f"{name}: {project.path}")
PY
```

A project path must exist and be a Git working-tree root; configured HTML pages must exist inside it. A catalogue project must contain `catalogue.py`, `data/catalog.json`, `data/products/`, and `templates/products.html`. Invalid configuration stops startup with a readable error.

`remote` defaults to `origin`. Use `null` for a local-only repository; push, pull, and remote comparison will be unavailable. `preview` is optional and must be a relative path to an HTML file in the repository, using forward slashes. `capturePages` is an optional list of additional relative HTML pages available for screenshots; the `preview` page is always included. `capturePages` requires `preview`. Omit both for projects without a website. Restart after changing project settings or environment variables.

### 3. Choose localhost or Tailscale access

The default is `127.0.0.1:8765`, reachable only on the server itself. For a temporary foreground run:

```bash
.venv/bin/python server.py
# Or, after activating the virtual environment:
# source .venv/bin/activate
# ./start.sh
```

Open <http://localhost:8765/> and stop with Ctrl+C. For a persistent installation, use the service in the next step instead of leaving a foreground process running.

For phone access, the Linux host and phone must be connected to the same Tailscale network with permission to reach the panel's port. Check the host's existing Tailscale connection:

```bash
tailscale status
tailscale ip -4
```

Use the host's actual Tailscale IPv4 address as `LINKO_PANEL_HOST`, port `8765` as `LINKO_PANEL_PORT`, and its Tailscale hostname(s) as comma-separated `LINKO_PANEL_ALLOWED_HOSTS` if hostname access is desired. The bound IP is already accepted as a Host. Discover these values on each installation; do not copy another machine's IP. If Tailscale is missing or disconnected, complete that host's Tailscale setup first; account/device authorization may require the owner.

Bind to the Tailscale address for private phone access. The panel has no login, and its terminal grants shell access as its Linux account. Restrict access to trusted devices/users; do not bind to all interfaces or publish it through Funnel or a public proxy.

### 4. Install a persistent systemd user service

Run `systemctl --user` as the repository owner, without sudo. First inspect any existing installation:

```bash
systemctl --user cat linko-dev-panel.service
systemctl --user status linko-dev-panel.service --no-pager
ss -ltnp 'sport = :8765'
```

A missing unit is expected on a fresh host. The checked-in service assumes `~/projects/linko-dev-panel` and uses its `.venv/bin/python`. For a fresh installation:

```bash
mkdir -p ~/.config/systemd/user
cp linko-dev-panel.service ~/.config/systemd/user/
```

Before enabling it, update the installed unit's `WorkingDirectory` and `ExecStart` if the checkout is elsewhere. For an existing service, update only the required settings and preserve its custom configuration. For Tailscale access, set these environment lines in the installed unit's `[Service]` section, replacing the example values with those discovered above:

```ini
Environment=LINKO_PANEL_HOST=100.x.y.z
Environment=LINKO_PANEL_PORT=8765
Environment=LINKO_PANEL_ALLOWED_HOSTS=host-name,host-name.tail-example.ts.net
```

Persist any `LINKO_REPO_PATH`, `LINKO_PANEL_CONFIG`, `LINKO_PROJECTS_DIR`, `LINKO_PANEL_NODE`, or `LINKO_PANEL_CHROME` overrides in that same section. For a user-installed Node, set `LINKO_PANEL_NODE` to the absolute path returned by `command -v node`; set the service's `PATH` too if terminal applications need tools outside the usual system directories. The service does not inherit exports from your current terminal and does not load `.env`. Keep `KillMode=process` so panel restarts preserve tmux sessions.

Then start it (restart an already-running service after a settings change):

```bash
systemctl --user daemon-reload
systemctl --user enable --now linko-dev-panel.service
# After changing an already-running service:
# systemctl --user restart linko-dev-panel.service
systemctl --user status linko-dev-panel.service --no-pager
```

Check user lingering so the service starts at boot and continues after logout:

```bash
loginctl show-user "$(id -un)" -p Linger
# If Linger=no and this host permits it:
sudo loginctl enable-linger "$(id -un)"
```

If `systemctl --user` cannot connect to the user bus, run these commands in the owner's normal login session or arrange the host's user-service support. Do not substitute a root service. A foreground run is only a temporary fallback and ends when its process/session ends.

### 5. Verify and return the URL

Use the configured host and port. For Tailscale, the following discovers this host's IP; for localhost, use `PANEL_URL=http://127.0.0.1:8765` instead:

```bash
set -euo pipefail
PANEL_IP=$(tailscale ip -4)
test -n "$PANEL_IP"
PANEL_URL="http://$PANEL_IP:8765"
systemctl --user is-active linko-dev-panel.service
systemctl --user is-enabled linko-dev-panel.service
ss -ltnp 'sport = :8765'
curl --fail --silent --show-error "$PANEL_URL/" -o /dev/null
curl --fail --silent --show-error "$PANEL_URL/api/projects" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"]; print("Projects:", ", ".join(p["name"] for p in d["projects"]))'
curl --fail --silent --show-error "$PANEL_URL/terminal-assets/xterm.js" -o /dev/null
curl --fail --silent --show-error "$PANEL_URL/terminal-assets/xterm.css" -o /dev/null
curl --fail --silent --show-error "$PANEL_URL/terminal-assets/addon-fit.js" -o /dev/null
printf 'Browser URL: %s/\n' "$PANEL_URL"
```

For each configured or discovered project returned by `/api/projects`, check `/api/status?project=<URL-encoded-name>` and `/api/terminal/status?project=<URL-encoded-name>`. The terminal should report `available: true`; `running: false` is normal before the first terminal connection. Check `/terminal?project=<URL-encoded-name>` loads too. These checks do not create a terminal or change a repository. Report screenshot capture as available only after checking its browser dependency; HTTP success alone does not verify that feature.

On the phone, connect Tailscale and open the returned **HTTP URL including `:8765`**. A check from the server verifies its listener and responses, but does not establish that the phone's Tailscale policy/connectivity works.

If startup or access fails:

- **Service exits:** inspect `journalctl --user -u linko-dev-panel.service -n 50 --no-pager`; check its Python path, dependencies, and project configuration.
- **Pillow or terminal dependencies missing:** install `requirements.txt` with the same `.venv/bin/python` used by `ExecStart`.
- **Terminal assets return 404:** run `npm ci` in the actual panel checkout.
- **Address already in use:** identify the existing listener/service before starting another copy. Reuse it or configure another port explicitly.
- **Cannot assign requested address:** check Tailscale is connected and the configured bind IP belongs to this host.
- **HTTP 403 / Host is not allowed:** add the hostname used in the browser to `LINKO_PANEL_ALLOWED_HOSTS` and restart.
- **Phone times out while host checks pass:** check the phone's Tailscale connection, tailnet access rules, and host firewall for the configured port.

## Add Project and discovery (Phase 2)

The standard projects directory is the **parent of the installed Dev Panel directory**, normally `~/projects` when the panel is in `~/projects/linko-dev-panel`. To override it, set `LINKO_PROJECTS_DIR` or add a top-level `"projectsDirectory"` to the selected settings file. The environment variable takes precedence. Relative paths resolve beside that settings file; `~` expands to the server user's home. The directory must already exist and be writable for cloning. For example:

```json
{
  "projectsDirectory": "~/projects",
  "projects": {}
}
```

Configured entries still load first and keep their display names, paths, remote, preview, screenshot and catalogue settings. The panel then discovers immediate child directories containing a valid `.git` directory or Git worktree `.git` file, verified with `git rev-parse --show-toplevel`. Plain folders, fake `.git` folders, bare repositories, hidden directories, symlinked project directories and unfinished panel clones are excluded. Discovery does not recurse, fetch, pull, stage, reset, run generators or change repository files. Discovered projects use their directory name, `origin`, and no website/catalogue configuration. If a name conflicts with a different configured project, a deterministic ` (local)` suffix distinguishes it. Repositories already configured by path appear only once.

Discovery runs at startup and whenever the browser requests the project list, including Add Project checks and clone completion. Repositories cloned by the panel become selectable automatically without a restart or configuration edit. To see a repository added outside the panel, reload the page. Installing this phase requires one panel restart to load the changed Python backend; subsequent clones require none. Settings-file and environment changes still require a restart. `"projects": {}` supports a fresh installation with no configured repositories; configured paths that are supplied must still be valid.

1. Create a repository at your Git provider.
2. In Dev Panel, click **+ Add Project** beside the repository selector and paste its URL.
3. Check **Repository** (for example `Linkoge/example-project`) and **Local project** (`~/projects/example-project`).
4. Click **Clone Project**. The dialog shows clone status and bounded Git output, and offers **Cancel clone**. Closing it leaves the job running; reopen Add Project to check it. A refresh in the same tab can recover job status while the panel process remains running.
5. A successful clone refreshes the selector and selects the project when the dialog is open. If the dialog was closed, reopen it and choose **Open project**, or use the selector. Click **OPEN TERMINAL** to start working in that repository with the unchanged Phase 1 tmux/session architecture. An unsaved Products edit retains its existing confirmation before switching projects.

Supported network forms include:

- `git@github.com:Linkoge/example-project.git` (SSH SCP-style).
- `https://github.com/Linkoge/example-project.git` (HTTPS).
- `ssh://git@git.example.org:2222/team/example-project.git` (SSH with optional port).

The `.git` suffix is optional, nested provider namespaces are supported, and no GitHub API is required. Repository path segments use ASCII letters, numbers, underscores, dots and hyphens, starting with a letter, number or underscore. Hostnames use DNS/IPv4 forms; IPv6 URL literals and unusual escaped/Unicode repository paths are outside this simple onboarding interface. Local/file URLs and Git external-helper URLs are rejected.

Empty remotes clone normally without adding README, LICENSE or other starter files. They appear in the selector, show an empty history and open in the browser terminal. You can create files and make the first commit through the existing Git controls.

If the destination already exists, cloning is blocked even when it is a plain folder, file or symlink. The panel never overwrites, deletes, resets or pulls that destination. When it is an available Git project, **Open existing project** selects it. Local names come from the repository's final path segment, so two providers/namespaces with the same repository name share a destination and the second clone is blocked.

Authentication uses the **server user's existing Git credentials or SSH setup**. HTTPS URLs containing usernames/passwords/tokens, query strings or fragments are rejected; use a credential helper instead. SSH runs in batch mode with strict host-key verification, so a previously unknown host must first be trusted through your usual server setup. SSH keys and tokens are neither requested by the interface nor returned in its status. Authentication/access failures and network errors appear with useful explanations and redacted Git output. No interactive password prompt is opened by the panel.

Clones use subprocess argument arrays with `shell=False`, a validated network URL after `--`, a fixed working directory and destination `.`. Project names reject traversal, separators, option prefixes, command substitution and shell characters. The server canonicalizes the projects root and destination and checks containment, then atomically creates a new private destination directory without adopting an existing one. Only one clone runs at a time, with a five-minute timeout. Output is bounded and repository URLs are redacted; request logs contain route/job IDs rather than the submitted URL. The existing Host, CSRF and origin checks protect onboarding requests.

Git can leave partial files after a failed clone. On failure, cancellation, timeout or graceful panel shutdown, the panel removes the partial destination only when its canonical path and device/inode identity still match the directory that this clone exclusively created. A replaced directory or symlink is preserved, with an explanation; cleanup permission failures are reported. A cleaned failure can be retried immediately. A forced process kill, machine crash or power loss can leave a partial directory; inspect it manually before retrying because ownership records and jobs are kept in memory and are never inferred after restart. Completed repositories persist and are rediscovered normally.

Phase 2 checks use disposable repositories and no remote repository writes:

```bash
python3 -m unittest discover -s tests -p test_onboarding.py -v
PANEL_TEST_PYTHON=.venv/bin/python node tests/test_onboarding_browser.mjs
PANEL_TEST_PYTHON=.venv/bin/python node tests/test_terminal_browser.mjs
```

The onboarding browser fixture passes real SSH/HTTPS-form URLs to Git with private `insteadOf` rewrites to local disposable remotes. It exercises the dialog, empty and populated clones, duplicate selection, missing-repository cleanup, discovery without restart, existing Git views, mobile layout and the new project's real tmux cwd/file creation. This verifies the workflow without requiring GitHub credentials; real provider authentication and network failures require your server/provider setup. Backend tests additionally cover authentication/network diagnostics, malformed URLs, traversal/shell characters, cancellation, timeout, ownership replacement and preservation of existing repositories.

Phase 2 verification passed all 20 onboarding Python checks, the live onboarding browser suite (including an initially empty project list), the complete Phase 1 terminal browser suite and both existing JavaScript suites. The full Python suite passed 61 of 62 checks; the remaining pre-existing `test_detail_workflow` fixture still omits `sitemap.py` required by the sibling Linko generator. That unrelated fixture and the product-image system were left unchanged. Real provider credentials, physical Android behavior and native Windows onboarding were not exercised.

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

Select a configured or discovered repository and click **OPEN TERMINAL**. It opens a dedicated, full-window workspace in a new tab. It starts the user's normal Linux shell in that project's directory, or returns to whatever application is already running in its tmux session. Run `bash`, `python`, `git`, `htop`, a development agent, or another ordinary terminal application yourself. No agent is automatically launched, and no application-specific session model is used.

Terminal sessions use short numeric names starting at `23`. A new project gets the first available number (`24`, `25`, and so on if earlier numbers are taken). Reopening a project's terminal reconnects to its existing session, including after a panel restart. Older hash-named project sessions are renamed in place on connection, preserving their running applications.

The architecture is **xterm.js → same-port WebSocket → real Linux PTY → tmux → shell/application**. `terminal_backend.py` attaches a temporary tmux client for each browser connection. Session creation uses process argument arrays, never a shell command assembled from browser input. The browser submits only a known project identity; the server project registry resolves and revalidates its canonical Git root. Phase 2 adds onboarding to this registry without changing the terminal implementation. Image/file clipboard uploads remain outside these phases.

### Dependencies and startup

On the Linux server, install **tmux** through your distribution's package manager (for Debian/Ubuntu: `sudo apt install tmux`). Then, from the panel directory:

```bash
.venv/bin/python -m pip install -r requirements.txt
npm ci
```

Create `.venv` first as described in [Quick start on Linux](#quick-start-on-linux). `simple-websocket` (1.1.0, backed by wsproto) handles WebSocket framing, heartbeat and socket integration with the existing HTTP server. `ptyprocess` (0.7.0, Linux only) handles PTY creation, terminal dimensions and child cleanup. `@xterm/xterm` (6.0.0) supplies maintained terminal emulation and native browser paste handling; `@xterm/addon-fit` (0.11.0) measures browser terminal dimensions. npm assets are served locally from an explicit three-file allowlist; no CDN or browser network dependency is introduced. Node is needed to install these assets, but the terminal bridge runs in Python and tmux, without a Node server. Existing Pillow and Playwright dependencies are retained.

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
| `LINKO_PROJECTS_DIR` | Parent of the installed panel directory | Directory scanned for Git projects and used for Add Project clones; overrides `projectsDirectory` |
| `LINKO_PANEL_HOST` | `127.0.0.1` | Address to listen on |
| `LINKO_PANEL_PORT` | `8765` | HTTP port |
| `LINKO_PANEL_ALLOWED_HOSTS` | Empty | Extra comma-separated hostnames accepted in requests |
| `LINKO_PANEL_NODE` | `node` on `PATH`, then an NVM installation | Node executable used for screenshots |
| `LINKO_PANEL_CHROME` | Chrome/Chromium on `PATH` or standard Windows installation folders | Browser executable used for screenshots |

Selection order is an explicit `LINKO_PANEL_CONFIG`, then local settings, then checked-in settings. `LINKO_REPO_PATH` overrides only the entry named `Linko`; other configured projects keep their own paths. Relative repository paths resolve beside the selected configuration file. Local settings replace the configured entries, so retain the settings for projects needing special metadata; automatic discovery adds eligible repositories from the projects directory. Neither a `.env` file nor environment changes in another terminal are loaded automatically.

These `LINKO_PANEL_` names are retained for compatibility with the original installation. To reach the panel from another device, bind to an address that device can reach and restrict access with a firewall or a private network such as Tailscale. **There is no login or TLS. Anyone who can reach the port can use the Git controls.** Mutating requests require a CSRF token and an origin check, but these do not replace network access control.

The included [`linko-dev-panel.service`](linko-dev-panel.service) is a systemd user-service template. It uses `%h` for the user's home directory, assumes `~/projects/linko-dev-panel`, and starts that checkout's virtual-environment Python. Follow [the Linux installation runbook](#quick-start-on-linux) to configure paths, private access, persistent startup, and verification. Existing installed services are not changed by updating this repository.

After changing Python, HTML, or project settings, restart with `systemctl --user restart linko-dev-panel.service`. After editing the installed service file, run `systemctl --user daemon-reload` before restarting. Restarting during a capture interrupts it.

## Git behavior

Commit stages all changes in the selected repository, including untracked files. Review the file list before confirming. Push is a separate action. Ahead/behind uses local remote-tracking data and may be stale until a pull or fetch elsewhere. Push targets the configured remote and current branch; pull requires an upstream on that remote.

Restoring a version requires a clean working tree and makes a **new commit** with the selected commit's files. Earlier commits remain in history, and the restore is not pushed automatically. Temporary historical checkout also requires a clean working tree. While detached, commit, push, pull, discard, and restore are unavailable; use **Return to current** to switch back to a branch. Preview serves only common web asset types and rejects hidden paths and paths outside the configured repository.

## Development

`server.py` handles HTTP and request checks; `repository.py` contains project configuration, portable preview URLs, and Git operations. `catalogue_backend.py` calls the selected checkout's generator through `catalogue_compat.py`. `index.html` is the interface, and `projects.json` supplies default project metadata. `project_onboarding.py` handles projects-directory resolution, read-only discovery, URL validation and clone jobs; `project-onboarding.js` supplies the Add Project dialog flow. `screenshots.py` manages capture jobs and saved sessions; `capture.mjs` and `scroll_plan.mjs` drive the browser. Run the Python integration and JavaScript scroll-plan tests with:

```bash
python3 -m unittest discover -s tests -v
node tests/test_scroll_plan.mjs
```

On Windows, use `python` instead of `python3`. Core tests use disposable Git repositories and fixed catalogue fixtures. Current detail/multiple-image integration tests require the sibling Linko checkout and skip when it is unavailable. `test_cross_platform.py` covers Windows-style paths, URL encoding, shell-free Git execution with explicit working directories, configurable checkout selection, startup errors, Windows browser discovery, and catalogue locking. The native lock test exercises Windows locking when run on Windows, and Linux locking on Linux. Symlink-specific tests require Windows Developer Mode or equivalent permission; only those checks skip if that permission is unavailable.

Phase 3 browser verification: run `node tests/test_product_images_browser.mjs` with Chrome and the sibling Linko checkout available. It creates a disposable catalogue and local server, then checks desktop drag/drop and 360px touch controls, selection/upload, new single-image products, save/reload/order/cover, removal without asset deletion, catalogue output and saved previews, gallery switching, mixed aspect ratios, stable layout and unavailable images. Run `node tests/test_detail_editor.mjs` for editor-state checks. `PANEL_TEST_PYTHON` can select the Python executable and `PANEL_IMAGE_SOURCE` can select an isolated current Linko source checkout. Physical Android/iOS and native Windows were not tested in Phase 3. The known detail-workflow fixture issue was fixed by including `sitemap.py` and using deterministic, fully translated test content; all 69 panel Python tests now pass.

The compatibility work was verified automatically on Linux with the Python and JavaScript suites, including HTTP handler integration tests. Windows paths and the Windows adapter are also exercised with portable representations/mocks on Linux. This verification environment denies listening sockets, so live server startup could not be tested here. Native Windows execution, Windows browser capture, and GitHub authentication/push from your PC require the manual Windows check above; Linux verification does not establish that those Windows runtime checks have run.

Licensed under the [MIT License](LICENSE).
