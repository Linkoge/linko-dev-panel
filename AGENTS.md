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
