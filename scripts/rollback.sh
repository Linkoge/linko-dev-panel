#!/bin/sh
set -eu
. "$(dirname -- "$0")/deploy-common.sh"

revision_file=$DEPLOY_STATE_DIR/rollback-revision
if [ ! -s "$revision_file" ]; then
    echo "No rollback revision is available at $revision_file" >&2
    exit 1
fi
revision=$(cat "$revision_file")
git -C "$DEPLOY_ROOT" cat-file -e "$revision^{commit}"
git -C "$DEPLOY_ROOT" reset --hard "$revision"
deploy_systemctl restart "$DEPLOY_UNIT"
printf '%s\n' "$revision" > "$DEPLOY_STATE_DIR/deployed-revision.tmp"
mv "$DEPLOY_STATE_DIR/deployed-revision.tmp" "$DEPLOY_STATE_DIR/deployed-revision"
