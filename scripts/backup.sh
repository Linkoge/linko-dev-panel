#!/bin/sh
set -eu
. "$(dirname -- "$0")/deploy-common.sh"

mkdir -p "$DEPLOY_STATE_DIR"

# The backup command runs before a merge is restarted. Prefer the revision
# recorded after the last successful deploy; on first setup use the first
# parent of the current commit as the version being replaced.
if [ -f "$DEPLOY_STATE_DIR/deployed-revision" ]; then
    revision=$(cat "$DEPLOY_STATE_DIR/deployed-revision")
else
    revision=$(git -C "$DEPLOY_ROOT" rev-parse --verify 'HEAD^' 2>/dev/null || git -C "$DEPLOY_ROOT" rev-parse --verify HEAD)
fi
git -C "$DEPLOY_ROOT" cat-file -e "$revision^{commit}"
printf '%s\n' "$revision" > "$DEPLOY_STATE_DIR/rollback-revision.tmp"
mv "$DEPLOY_STATE_DIR/rollback-revision.tmp" "$DEPLOY_STATE_DIR/rollback-revision"
printf 'Saved rollback revision %s\n' "$revision"
