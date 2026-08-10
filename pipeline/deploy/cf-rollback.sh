#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# cf-rollback.sh — Cloudflare Pages production rollback engine.
#
# WHY THIS EXISTS
# Before this script, deploy.reusable.yml could DETECT a bad production deploy
# (verify-live / crawler-check turn the run red) but could not RECOVER from
# one: the only documented remedy was a comment telling a human to run
# `wrangler pages deployment rollback` by hand. Between the failing gate and the
# human noticing, the bad build keeps serving. This script closes that window.
#
# THE SACRED RULE IS PRESERVED
# This script does NOT build and does NOT create a deployment. It can only
# PROMOTE A DEPLOYMENT THAT ALREADY EXISTS in the project's history — i.e. code
# that already went through a human PR merge to main at some earlier point. It
# is invoked exclusively from inside the post-merge deploy job. It therefore
# creates NO second path to production: it can only move production BACKWARDS to
# a state production was already in.
#
# PER-CLIENT ACCOUNTS
# Every value it needs (account id, API token, project name) is read from the
# environment. Nothing is hardcoded and no shared/global account is assumed —
# each client repo supplies its OWN Cloudflare account id + token, which is the
# fleet's actual topology.
#
# ---------------------------------------------------------------------------
# USAGE
#   cf-rollback.sh capture
#       Print the deployment id currently SERVING production, to stdout, alone.
#       Prints the literal string NONE (exit 0) when the project has no prior
#       production deployment — i.e. the first-ever deploy. That is an expected
#       state, not an error: there is simply nothing to roll back to.
#
#   cf-rollback.sh rollback <DEPLOYMENT_ID>
#       Roll production back to DEPLOYMENT_ID. Exit 0 on success, non-zero on
#       failure (a non-zero here is a P0 — production is left on the bad build).
#
#   cf-rollback.sh current
#       Alias of capture, for a post-rollback confirmation read.
#
# ENVIRONMENT (all referenced BY NAME only — never write a value into a file)
#   CLOUDFLARE_API_TOKEN   required — this CLIENT'S token (Pages: Edit)
#   CLOUDFLARE_ACCOUNT_ID  required — this CLIENT'S account id
#   CLOUDFLARE_PAGES_PROJECT required — this client's Pages project name
#   CF_API_BASE            optional — API root. Default the real CF API.
#   WF_CF_API_CMD          optional — path to a command that replaces the HTTP
#                          call entirely, invoked as `<cmd> <METHOD> <PATH>` and
#                          expected to print the raw JSON response body. This is
#                          the TEST SEAM: the simulation harness points it at a
#                          stub so the rollback path can be exercised end to end
#                          without touching a real Cloudflare account.
#
# EXIT CODES
#   0  success (capture printed an id or NONE; rollback completed)
#   1  bad usage / missing required environment
#   2  API call failed or returned success:false
#   3  rollback completed the API call but production did not land on the
#      requested deployment id (rollback did not take — treat as P0)
# ---------------------------------------------------------------------------
set -uo pipefail

CF_API_BASE="${CF_API_BASE:-https://api.cloudflare.com/client/v4}"

die() { echo "cf-rollback: $*" >&2; exit 1; }

MODE="${1:-}"
case "$MODE" in
  capture|current|rollback) ;;
  *) die "usage: cf-rollback.sh {capture|current|rollback <DEPLOYMENT_ID>}" ;;
esac

: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID is required}"
: "${CLOUDFLARE_PAGES_PROJECT:?CLOUDFLARE_PAGES_PROJECT is required}"
if [ -z "${WF_CF_API_CMD:-}" ]; then
  : "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required}"
fi

PROJECT_PATH="/accounts/${CLOUDFLARE_ACCOUNT_ID}/pages/projects/${CLOUDFLARE_PAGES_PROJECT}"

# --- API transport ---------------------------------------------------------
# Emits the raw response body on stdout. Never echoes the token.
_api() {
  local method="$1" path="$2"
  if [ -n "${WF_CF_API_CMD:-}" ]; then
    "$WF_CF_API_CMD" "$method" "$path"
    return $?
  fi
  curl -sS -X "$method" \
    --max-time 45 \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json" \
    "${CF_API_BASE}${path}"
}

# --- JSON helpers ----------------------------------------------------------
# python3 is guaranteed present on the runner (setup-python runs before this).
_json_ok() {
  # stdin = response body. exit 0 if {"success": true}
  python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if d.get("success") is True else 1)
'
}

_json_errors() {
  python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unparseable response body"); sys.exit(0)
errs = d.get("errors") or []
if not errs:
    print("no error detail returned")
else:
    print("; ".join(str(e.get("message", e)) for e in errs))
' 2>/dev/null || echo "unparseable response body"
}

# --- capture ---------------------------------------------------------------
# The deployment currently SERVING production is the project's
# canonical_deployment. Fall back to the newest production-environment
# deployment in the deployments list if the project object omits it.
capture_current() {
  local body id
  body="$(_api GET "${PROJECT_PATH}")" || return 2
  printf '%s' "$body" | _json_ok || {
    echo "cf-rollback: project read failed: $(printf '%s' "$body" | _json_errors)" >&2
    return 2
  }
  id="$(printf '%s' "$body" | python3 -c '
import json,sys
d = json.load(sys.stdin).get("result") or {}
for key in ("canonical_deployment", "latest_deployment"):
    dep = d.get(key)
    if isinstance(dep, dict) and dep.get("id") and dep.get("environment", "production") == "production":
        print(dep["id"]); break
' 2>/dev/null)"

  if [ -z "$id" ]; then
    body="$(_api GET "${PROJECT_PATH}/deployments?env=production&per_page=25")" || return 2
    printf '%s' "$body" | _json_ok || {
      echo "cf-rollback: deployment list failed: $(printf '%s' "$body" | _json_errors)" >&2
      return 2
    }
    id="$(printf '%s' "$body" | python3 -c '
import json,sys
res = json.load(sys.stdin).get("result") or []
for dep in res:
    if not isinstance(dep, dict):
        continue
    if dep.get("environment") != "production":
        continue
    if dep.get("is_skipped"):
        continue
    stage = dep.get("latest_stage") or {}
    # Only a deployment that finished successfully is a valid rollback target.
    if stage.get("status") not in (None, "success"):
        continue
    if dep.get("id"):
        print(dep["id"]); break
' 2>/dev/null)"
  fi

  if [ -z "$id" ]; then
    # FIRST-EVER DEPLOY. Not an error — the project genuinely has no previous
    # production deployment, so there is no rollback target. The caller must
    # branch on NONE rather than crash.
    echo "NONE"
    return 0
  fi
  echo "$id"
  return 0
}

# --- rollback --------------------------------------------------------------
do_rollback() {
  local target="$1" body landed
  [ -n "$target" ] || die "rollback requires a DEPLOYMENT_ID"
  if [ "$target" = "NONE" ]; then
    echo "cf-rollback: refusing to roll back to NONE (there is no previous deployment)." >&2
    return 1
  fi

  echo "cf-rollback: rolling production back to ${target}"
  body="$(_api POST "${PROJECT_PATH}/deployments/${target}/rollback")" || {
    echo "cf-rollback: rollback API call could not be made." >&2
    return 2
  }
  if ! printf '%s' "$body" | _json_ok; then
    echo "cf-rollback: rollback REJECTED by Cloudflare: $(printf '%s' "$body" | _json_errors)" >&2
    return 2
  fi

  # Confirm production actually moved. A 'success' response that leaves the bad
  # deployment serving is exactly the silent failure this rail must not have.
  landed="$(capture_current)" || {
    echo "cf-rollback: rollback reported success but the confirmation read failed." >&2
    return 3
  }
  if [ "$landed" != "$target" ]; then
    echo "cf-rollback: rollback reported success but production is serving '${landed}', not '${target}'." >&2
    return 3
  fi
  echo "cf-rollback: production is now serving ${target}"
  return 0
}

case "$MODE" in
  capture|current)
    capture_current
    exit $?
    ;;
  rollback)
    do_rollback "${2:-}"
    exit $?
    ;;
esac
