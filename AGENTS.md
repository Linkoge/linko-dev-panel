# Dev Panel setup for AI agents

When asked to install, run, or restore the panel on Linux, follow the complete
[Linux installation runbook in README.md](README.md#quick-start-on-linux).
Perform the setup and verification within the requested scope; providing
commands alone does not complete an installation request.

- Inspect the existing checkout, local project configuration, installed user
  service, and listener before changing them. Preserve existing custom settings.
- Verify the projects directory used for discovery and Add Project clones.
  Preserve configured preview/catalogue metadata alongside discovered repositories;
  persist `LINKO_PROJECTS_DIR` in the service when overriding the default.
- Install Python requirements into `.venv` and run `npm ci` for terminal assets.
  The browser terminal also requires tmux. Chrome/Chromium is needed for screenshots.
- Use the repository owner's systemd user service for persistent startup and
  check user lingering. The template assumes `~/projects/linko-dev-panel`;
  adjust the installed unit for the actual checkout and dependency paths.
- For phone access, discover the current host's Tailscale IP, bind to that IP,
  and persist any hostname and executable overrides in the service configuration.
  Keep access private: the panel has no login and the terminal has shell access.
- Verify service state, listener address, project endpoints, terminal availability,
  and browser assets as described in the runbook. Return the actual browser URL
  and disclose any unavailable feature or unverified phone connectivity.

Keep the runbook and service template consistent when changing setup requirements.

## Git authentication and push verification

- Preserve each repository's working remote and authentication, including the
  panel's own checkout. A successful public HTTPS clone or `ls-remote` does not
  establish permission to push. Do not replace working SSH authentication with
  HTTPS unless a noninteractive credential helper is verified for the server user.
- Before declaring push support ready, verify the configured push URL and run
  `git push --dry-run <configured-remote> HEAD:refs/heads/<current-branch>` with
  `GIT_TERMINAL_PROMPT=0`, as the panel's user and with its service environment.
  Check the actual service's HOME, PATH and SSH agent/helper availability;
  authentication in an interactive agent shell alone is insufficient. For SSH,
  use batch mode and strict host-key checking. Never print credentials or embed
  tokens in remote URLs, documentation or service files.
- If HTTPS reports `could not read Username` / `terminal prompts disabled`,
  inspect the credential setup. Reuse the owner's existing working SSH setup
  when available, verify access to the exact repository with a push dry run,
  then update only that repository's remote to the same owner/repository over
  SSH. Preserve explicit push URLs and other remotes; verify the configured
  remote again after the change. See [the README procedure](README.md#git-authentication-checks).
- Commit and push are separate operations. Local history proves a commit exists
  locally; local ahead/behind counts may be stale. After an authorized real push,
  compare `git rev-parse HEAD` with the intended branch returned by
  `git ls-remote <verified-push-url> refs/heads/<current-branch>` at the actual
  push destination. Report pending local commits and authentication failures
  accurately. Setup and diagnosis use dry runs; publishing requires the user's
  instruction to push.
