#!/bin/sh

set -eu

DEPLOY_ROOT=${LINKO_DEPLOY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
DEPLOY_STATE_DIR=${LINKO_DEPLOY_STATE_DIR:-${XDG_STATE_HOME:-${HOME:?HOME must be set}/.local/state}/linko-dev-panel/deploy}
DEPLOY_UNIT=${LINKO_DEPLOY_UNIT:-linko-dev-panel.service}

deploy_systemctl() {
    "${SYSTEMCTL:-systemctl}" --user "$@"
}

