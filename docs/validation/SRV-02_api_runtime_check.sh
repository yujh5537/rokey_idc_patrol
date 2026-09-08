#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/api/v1}"
ROBOT_ID="${ROBOT_ID:-robot5}"
MAX_SECONDS="${MAX_SECONDS:-1.0}"

check_endpoint() {
  local label="$1"
  local url="$2"
  local result
  local http_code
  local elapsed

  result="$(curl -sS -o /tmp/srv02_api_response.json -w '%{http_code} %{time_total}' "$url")"
  http_code="${result%% *}"
  elapsed="${result##* }"

  printf '%-18s HTTP %s  %ss  %s\n' "$label" "$http_code" "$elapsed" "$url"

  if [[ "$http_code" -lt 200 || "$http_code" -ge 300 ]]; then
    echo "FAIL: $label returned HTTP $http_code" >&2
    return 1
  fi

  if ! awk -v elapsed="$elapsed" -v max="$MAX_SECONDS" 'BEGIN { exit !(elapsed < max) }'; then
    echo "FAIL: $label response time ${elapsed}s is not below ${MAX_SECONDS}s" >&2
    return 1
  fi
}

check_endpoint "robots API" "$BASE_URL/robots"
check_endpoint "robot detail API" "$BASE_URL/robots/$ROBOT_ID"
check_endpoint "events API" "$BASE_URL/events"

echo "PASS: all SRV-02 REST endpoints returned 2xx in under ${MAX_SECONDS}s"
