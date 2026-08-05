#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# verify-live.sh — post-deploy live assertion.
#
# Lesson 4: never claim shipped until the served HTML is grepped. For each key
# route this curls the LIVE production URL and asserts:
#   1. HTTP 200
#   2. a known content string is present in the served HTML (optional but
#      strongly recommended — proves the page rendered, not just that the edge
#      returned an empty 200).
#
# Exit non-zero on ANY failure so the deploy workflow fails RED before IndexNow
# / proof. No false greens.
#
# Usage:
#   verify-live.sh <BASE_URL> <CONTENT_STRING> <ROUTE> [ROUTE ...]
#     BASE_URL        e.g. https://northstar.com   (no trailing slash)
#     CONTENT_STRING  string expected in every route's HTML; "" to skip the
#                     content check and assert 200 only
#     ROUTE...        one or more paths, e.g. /  /services/  /contact/
#
# Example:
#   verify-live.sh https://northstar.com "Northstar Roofing" / /services/ /contact/
# ---------------------------------------------------------------------------
set -uo pipefail

BASE_URL="${1:?BASE_URL required}"
CONTENT_STRING="${2-}"
shift 2 || true

# Default to root if no routes supplied.
if [ "$#" -eq 0 ]; then
  set -- "/"
fi

# Strip any trailing slash from base.
BASE_URL="${BASE_URL%/}"

RETRIES=3
RETRY_DELAY=5
FAILURES=0
TESTED=0

echo "== verify-live =="
echo "base: ${BASE_URL}"
echo "content assertion: ${CONTENT_STRING:-<none (200-only)>}"
echo

for ROUTE in "$@"; do
  # Ensure exactly one leading slash.
  case "$ROUTE" in
    /*) PATH_PART="$ROUTE" ;;
    *)  PATH_PART="/$ROUTE" ;;
  esac
  URL="${BASE_URL}${PATH_PART}"
  TESTED=$((TESTED + 1))

  ok=0
  for attempt in $(seq 1 "$RETRIES"); do
    # -L follow redirects (trailing-slash canonicalization is normal).
    # Capture body to a temp file and the final HTTP code separately.
    BODY_FILE="$(mktemp)"
    CODE="$(curl -sS -L -o "$BODY_FILE" -w '%{http_code}' \
              --max-time 30 \
              -A 'meridian-ci-verify/1.0' \
              "$URL" || echo "000")"

    if [ "$CODE" != "200" ]; then
      echo "  [try ${attempt}] ${URL} -> HTTP ${CODE} (want 200)"
      rm -f "$BODY_FILE"
      sleep "$RETRY_DELAY"
      continue
    fi

    if [ -n "$CONTENT_STRING" ]; then
      if ! grep -qF -- "$CONTENT_STRING" "$BODY_FILE"; then
        echo "  [try ${attempt}] ${URL} -> 200 but content string NOT found"
        rm -f "$BODY_FILE"
        sleep "$RETRY_DELAY"
        continue
      fi
    fi

    BYTES="$(wc -c < "$BODY_FILE" | tr -d ' ')"
    rm -f "$BODY_FILE"
    echo "  PASS ${URL} -> 200, ${BYTES} bytes$([ -n "$CONTENT_STRING" ] && echo ", content ok")"
    ok=1
    break
  done

  if [ "$ok" -ne 1 ]; then
    echo "  FAIL ${URL}"
    FAILURES=$((FAILURES + 1))
  fi
done

echo
echo "verified ${TESTED} route(s), ${FAILURES} failure(s)"

if [ "$FAILURES" -ne 0 ]; then
  echo "verify-live: FAILED"
  exit 1
fi

echo "verify-live: OK"
exit 0
