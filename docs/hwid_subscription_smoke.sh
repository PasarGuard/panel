#!/usr/bin/env bash
# HWID subscription smoke examples (bash + curl).
# Usage:
#   export SUB_TOKEN='your-subscription-token'
#   export BASE_URL='https://127.0.0.1:8000'   # or http://...
#   export SUB_PATH='sub'                      # must match panel SUBSCRIPTION_PATH
#   export CURL_INSECURE='-k'                # add -k for self-signed TLS
#   ./docs/hwid_subscription_smoke.sh
#
# With HWID globally disabled: expect HTTP 200 and no x-hwid-* headers on success.
# With HWID enabled + positive fallback (or per-user) limit:
#   - First curl with a new x-hwid should return 200 and x-hwid-active: true
#   - Same x-hwid again: 200 (updates last_seen / metadata)
#   - Missing x-hwid: 404 + x-hwid-not-supported: true
#   - Different x-hwid when already at limit: 404 + x-hwid-max-devices-reached / x-hwid-limit

set -euo pipefail

SUB_TOKEN="${SUB_TOKEN:-}"
BASE_URL="${BASE_URL:-https://127.0.0.1:8000}"
SUB_PATH="${SUB_PATH:-sub}"
CURL_INSECURE="${CURL_INSECURE:-}"

if [[ -z "$SUB_TOKEN" ]]; then
  echo "Set SUB_TOKEN to a valid subscription token." >&2
  exit 1
fi

SUB_URL="${BASE_URL%/}/${SUB_PATH}/${SUB_TOKEN}/links"

echo "== Base URL: ${BASE_URL}"
echo "== Subscription URL: ${SUB_URL}"
echo

run() {
  local name="$1"
  shift
  echo "--- ${name} ---"
  # -D - prints headers to stdout; -o /dev/null discards body
  curl -sS ${CURL_INSECURE} -D - -o /dev/null "$@" "${SUB_URL}" | tr -d '\r' | sed -n '1,30p'
  echo
}

# 1) Minimal client: only HWID (good for testing enforcement)
run "Device A — x-hwid only" \
  -H "X-HWID: smoke-device-a"

# 2) Same as app might send: HWID + OS + model + UA
run "Device B — full optional metadata" \
  -H "X-HWID: smoke-device-b" \
  -H "X-Device-OS: iOS" \
  -H "X-Ver-OS: 17.2" \
  -H "X-Device-Model: iPhone15,2" \
  -H "User-Agent: PasarGuard-HWID-Smoke/1.0"

# 3) Deliberately no HWID header (expect 404 + not-supported when HWID enforced)
run "No X-HWID header"

echo "Done. Inspect status line and x-hwid-* response headers above."
