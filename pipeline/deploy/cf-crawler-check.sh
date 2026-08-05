#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# cf-crawler-check.sh — LIVE, post-deploy AI-crawler access gate (edge side).
#
# Why this gate exists (T05): a single Cloudflare "Block AI Crawlers" toggle,
# or a Bot-Fight / WAF managed rule, silently returns a challenge/403 to the
# citation bots that feed AI Overviews, ChatGPT, Perplexity and Claude. Every
# build metric stays green while the entire AEO pillar is zeroed at the edge.
# CF rules live at the edge — INVISIBLE in ./out — so this MUST run on the live
# URL, never on the static build. The static companion (robots-aicrawler-check.py)
# catches a robots.txt Disallow pre-deploy; this catches the edge block.
#
# What it does: for every CITATION user-agent, curls each route on the live URL
# and asserts a real 200 with page content and NO Cloudflare challenge
# ('Just a moment', 'cf-challenge', 'cdn-cgi/challenge', 'Checking your browser',
# 'Attention Required'). A 403 or a challenge body on a citation UA is RED.
# TRAINING bots (GPTBot/ClaudeBot/Google-Extended/CCBot) are fetched for
# visibility only — their status is reported INFO and NEVER turns the gate RED
# (blocking training crawlers is a legitimate privacy choice).
#
# Arg order mirrors verify-live.sh so it wires in next to it in the deploy job.
#
# Usage:
#   cf-crawler-check.sh <BASE_URL> <CONTENT_STRING> <ROUTE> [ROUTE ...]
#     BASE_URL        e.g. https://acmeroofing.example.com   (trailing slash optional)
#     CONTENT_STRING  string expected in every route's HTML for each citation
#                     UA; "" to skip the content assertion and check 200+no-challenge
#     ROUTE...        one or more paths (default: /)
#
# UA lists are env-overridable (mitigates vendor bot-renames):
#   CITATION_UAS  space/comma-separated citation bot tokens (RED if blocked)
#   TRAINING_UAS  space/comma-separated training bot tokens (INFO only)
#   CRAWLER_CONFIG  optional path to a client-config.yml — if the env lists are
#                   unset and python3+PyYAML are present, citation_uas /
#                   training_uas (top-level or under ai_crawlers:) are read from it.
# Precedence: env override > config file > hardcoded defaults below.
#
# Exit codes:
#   0  every citation UA got 200 + content + no challenge on every route
#   1  RED — any citation UA got 403 / a challenge / a non-200 / missing content
# ---------------------------------------------------------------------------
set -uo pipefail

BASE_URL="${1:?BASE_URL required (e.g. https://acmeroofing.example.com)}"
CONTENT_STRING="${2-}"
shift 2 2>/dev/null || shift $# || true

# Default to root if no routes supplied.
if [ "$#" -eq 0 ]; then
  set -- "/"
fi

BASE_URL="${BASE_URL%/}"

# ── Hardcoded sane defaults ────────────────────────────────────────────────
# Citation bots: the crawlers whose fetch feeds an AI answer WITH a live link
# back to the site. Blocking any of these zeroes AEO — RED.
DEFAULT_CITATION_UAS="OAI-SearchBot ChatGPT-User PerplexityBot Bingbot Googlebot Claude-SearchBot"
# Training bots: bulk corpus scrapers. Blocking them is a valid privacy choice,
# so they are reported INFO-only and never gate.
DEFAULT_TRAINING_UAS="GPTBot ClaudeBot Google-Extended CCBot"

# ── Resolve UA lists: env override > config file > defaults ─────────────────
_normalize_list() { printf '%s' "$1" | tr ',' ' ' | tr -s '[:space:]' ' ' | sed 's/^ //; s/ $//'; }

_from_config() {
  # $1 = yaml key (citation_uas | training_uas). Emits a space-separated list or
  # nothing. Never fails the script — degrades to empty on any error.
  local key="$1"
  [ -n "${CRAWLER_CONFIG:-}" ] || return 0
  [ -f "${CRAWLER_CONFIG:-}" ] || return 0
  command -v python3 >/dev/null 2>&1 || return 0
  python3 - "$CRAWLER_CONFIG" "$key" <<'PY' 2>/dev/null || true
import sys
try:
    import yaml
except Exception:
    sys.exit(0)
try:
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f) or {}
except Exception:
    sys.exit(0)
key = sys.argv[2]
val = None
if isinstance(cfg.get("ai_crawlers"), dict) and cfg["ai_crawlers"].get(key):
    val = cfg["ai_crawlers"][key]
elif cfg.get(key):
    val = cfg[key]
if not val:
    sys.exit(0)
if isinstance(val, str):
    import re
    val = [t for t in re.split(r"[,\s]+", val) if t]
print(" ".join(str(t) for t in val))
PY
}

CITATION_UAS="$(_normalize_list "${CITATION_UAS:-}")"
[ -n "$CITATION_UAS" ] || CITATION_UAS="$(_normalize_list "$(_from_config citation_uas)")"
[ -n "$CITATION_UAS" ] || CITATION_UAS="$DEFAULT_CITATION_UAS"

TRAINING_UAS="$(_normalize_list "${TRAINING_UAS:-}")"
[ -n "$TRAINING_UAS" ] || TRAINING_UAS="$(_normalize_list "$(_from_config training_uas)")"
[ -n "$TRAINING_UAS" ] || TRAINING_UAS="$DEFAULT_TRAINING_UAS"

# ── Map a bot token to a realistic full User-Agent header ───────────────────
# A realistic UA string improves fidelity vs a WAF that keys on the classic
# "compatible; <Bot>/x.x; +url" shape. Unknown tokens fall back to the token.
ua_string() {
  case "$1" in
    OAI-SearchBot)   echo "Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)" ;;
    ChatGPT-User)    echo "Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)" ;;
    GPTBot)          echo "Mozilla/5.0 (compatible; GPTBot/1.1; +https://openai.com/gptbot)" ;;
    PerplexityBot)   echo "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://www.perplexity.ai/perplexitybot)" ;;
    Perplexity-User) echo "Mozilla/5.0 (compatible; Perplexity-User/1.0; +https://www.perplexity.ai/perplexity-user)" ;;
    Bingbot)         echo "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)" ;;
    Googlebot)       echo "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" ;;
    Google-Extended) echo "Google-Extended" ;;
    Claude-SearchBot) echo "Mozilla/5.0 (compatible; Claude-SearchBot/1.0; +https://www.anthropic.com/claude-searchbot)" ;;
    Claude-User)     echo "Mozilla/5.0 (compatible; Claude-User/1.0; +https://www.anthropic.com/claude-user)" ;;
    ClaudeBot)       echo "Mozilla/5.0 (compatible; ClaudeBot/1.0; +https://www.anthropic.com/claudebot)" ;;
    CCBot)           echo "CCBot/2.0 (https://commoncrawl.org/faq/)" ;;
    Bytespider)      echo "Mozilla/5.0 (compatible; Bytespider; ops@example.com)" ;;
    *)               echo "$1" ;;
  esac
}

# Match ONLY genuine Cloudflare interstitial / WAF-block markers. Deliberately
# NOT a bare 'cdn-cgi/challenge': CF injects a benign
# 'cdn-cgi/challenge-platform/scripts/jsd/main.js' JS-detection BEACON into every
# NORMAL 200 page, so a substring match there false-positives on healthy content
# (verified against live acmeroofing.example.com — a real 200 page carries the beacon but none
# of the markers below). Real challenge pages carry the '_cf_chl_opt' options var
# / the "Just a moment" title; real WAF blocks carry "Attention Required" /
# 'cf-error-details' / the "Enable JavaScript and cookies to continue" line.
CHALLENGE_RE='Just a moment|_cf_chl_opt|cf-challenge-running|challenge-error-text|Attention Required|cf-error-details|Enable JavaScript and cookies to continue|Checking your browser before'
RETRIES=2
RETRY_DELAY=4

echo "== cf-crawler-check (LIVE edge) =="
echo "base: ${BASE_URL}"
echo "routes: $*"
echo "content assertion: ${CONTENT_STRING:-<none (200 + no-challenge only)>}"
echo "citation UAs (gating): ${CITATION_UAS}"
echo "training UAs (INFO):   ${TRAINING_UAS}"
echo

# fetch <ua-string> <url>  -> sets globals CODE and BODY_FILE (caller rm's it)
fetch() {
  local ua="$1" url="$2"
  BODY_FILE="$(mktemp)"
  CODE="$(curl -sS -L -o "$BODY_FILE" -w '%{http_code}' \
            --max-time 30 \
            -A "$ua" \
            -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \
            "$url" 2>/dev/null || echo "000")"
}

RED=0
CIT_TESTED=0

for TOKEN in $CITATION_UAS; do
  UA="$(ua_string "$TOKEN")"
  for ROUTE in "$@"; do
    case "$ROUTE" in /*) P="$ROUTE" ;; *) P="/$ROUTE" ;; esac
    URL="${BASE_URL}${P}"
    CIT_TESTED=$((CIT_TESTED + 1))
    ok=0; reason=""
    for attempt in $(seq 1 "$RETRIES"); do
      fetch "$UA" "$URL"
      if [ "$CODE" = "403" ]; then
        reason="HTTP 403 (edge block)"; rm -f "$BODY_FILE"; sleep "$RETRY_DELAY"; continue
      fi
      if grep -qEi -- "$CHALLENGE_RE" "$BODY_FILE" 2>/dev/null; then
        reason="Cloudflare challenge in body"; rm -f "$BODY_FILE"; sleep "$RETRY_DELAY"; continue
      fi
      if [ "$CODE" != "200" ]; then
        reason="HTTP ${CODE} (want 200)"; rm -f "$BODY_FILE"; sleep "$RETRY_DELAY"; continue
      fi
      if [ -n "$CONTENT_STRING" ] && ! grep -qF -- "$CONTENT_STRING" "$BODY_FILE" 2>/dev/null; then
        reason="200 but content string missing"; rm -f "$BODY_FILE"; sleep "$RETRY_DELAY"; continue
      fi
      BYTES="$(wc -c < "$BODY_FILE" | tr -d ' ')"; rm -f "$BODY_FILE"
      echo "  PASS [${TOKEN}] ${URL} -> 200, ${BYTES} bytes$([ -n "$CONTENT_STRING" ] && echo ', content ok')"
      ok=1; break
    done
    if [ "$ok" -ne 1 ]; then
      echo "  RED  [${TOKEN}] ${URL} -> ${reason:-unreachable}"
      RED=$((RED + 1))
    fi
  done
done

echo
echo "-- training bots (INFO only, never gate) --"
for TOKEN in $TRAINING_UAS; do
  UA="$(ua_string "$TOKEN")"
  ROUTE="/"; URL="${BASE_URL}${ROUTE}"
  fetch "$UA" "$URL"
  if grep -qEi -- "$CHALLENGE_RE" "$BODY_FILE" 2>/dev/null; then
    echo "  INFO [${TOKEN}] ${URL} -> HTTP ${CODE}, challenge/blocked (expected/allowed)"
  else
    echo "  INFO [${TOKEN}] ${URL} -> HTTP ${CODE}"
  fi
  rm -f "$BODY_FILE"
done

echo
echo "cf-crawler-check: tested ${CIT_TESTED} citation UA×route pair(s), ${RED} RED"
if [ "$RED" -ne 0 ]; then
  echo "FAIL: ${RED} citation-crawler access failure(s) at the EDGE."
  echo "      Fix at Cloudflare: dashboard -> Security -> Bots -> disable 'Block AI Crawlers';"
  echo "      check WAF/managed rules and Bot Fight Mode for the citation UAs above."
  echo "      (If robots-aicrawler-check.py is GREEN, the block is edge-side, not robots.txt.)"
  exit 1
fi
echo "PASS: all citation crawlers reach the live site (200 + content, no challenge)."
exit 0
