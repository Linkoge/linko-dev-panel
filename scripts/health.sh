#!/bin/sh
set -eu
. "$(dirname -- "$0")/deploy-common.sh"

url=${LINKO_DEPLOY_HEALTH_URL:-http://127.0.0.1:8765/}
"${CURL:-curl}" --fail --silent --show-error --max-time "${LINKO_DEPLOY_CURL_TIMEOUT:-5}" "$url" >/dev/null
