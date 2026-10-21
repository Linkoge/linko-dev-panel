#!/bin/sh
set -eu
. "$(dirname -- "$0")/deploy-common.sh"

deploy_systemctl restart "$DEPLOY_UNIT"
mkdir -p "$DEPLOY_STATE_DIR"
git -C "$DEPLOY_ROOT" rev-parse --verify HEAD > "$DEPLOY_STATE_DIR/deployed-revision.tmp"
mv "$DEPLOY_STATE_DIR/deployed-revision.tmp" "$DEPLOY_STATE_DIR/deployed-revision"
