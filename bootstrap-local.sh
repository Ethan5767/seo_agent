#!/bin/bash
# seo-content-pipeline — environment bootstrap (idempotent, local-only).
# Rebuilds the runnable pipeline from a fresh machine + the GitHub remotes.
set -euo pipefail

ENGINE="${1:-$(cd "$(dirname "$0")" && pwd)}"
VENV="$HOME/.wf-pipeline-venv"

echo "── checks ──"
command -v python3 >/dev/null || { echo "FATAL: python3 missing"; exit 1; }
command -v git     >/dev/null || { echo "FATAL: git missing"; exit 1; }
command -v gh      >/dev/null && gh auth status >/dev/null 2>&1 && echo "gh: authed" || echo "WARN: gh missing/unauthed — PR creation will need it"
command -v claude  >/dev/null && echo "claude: on PATH" || echo "WARN: claude missing — wf-site-remediate has no writer"

if [ ! -d "$ENGINE/pipeline" ]; then
  echo "FATAL: engine not found at: $ENGINE"
  echo "Recover with: git clone <seo-content-pipeline remote> and re-run with the clone path as arg 1."
  exit 1
fi

echo "── engine venv ──"
# Prefer 3.12 — the engine's CI matrix tops out there, and brew's 3.14 has
# ensurepip issues. Fall back to python3.
PY="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)"
echo "using: $PY"
[ -d "$VENV" ] || "$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -e "$ENGINE"
pip install --quiet pyyaml

echo "── verify engine commands ──"
# ponytail: one command per stage of the rail, not all 40 — if these four
# resolve, the entry points installed.
for c in wf-onboard wf-site-health wf-site-plan wf-site-remediate; do
  command -v "$c" >/dev/null || { echo "FATAL: $c not on PATH after install"; exit 1; }
done
echo "engine commands: OK"

echo ""
echo "READY. Activate with:  source $VENV/bin/activate"
echo "Then follow docs/HOW-IT-WORKS.md stage by stage."
