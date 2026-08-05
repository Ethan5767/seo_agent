#!/bin/bash
# seo-content-pipeline — environment bootstrap (idempotent, local-only).
# Rebuilds the runnable pipeline from a fresh machine + the GitHub remotes.
set -euo pipefail

ENGINE="${1:-$(cd "$(dirname "$0")" && pwd)}"
VENV="$HOME/.wf-pipeline-venv"
HERE="$ENGINE"

echo "── checks ──"
command -v python3 >/dev/null || { echo "FATAL: python3 missing"; exit 1; }
command -v pandoc  >/dev/null || { echo "FATAL: pandoc missing (brew install pandoc)"; exit 1; }
command -v git     >/dev/null || { echo "FATAL: git missing"; exit 1; }
command -v gh      >/dev/null && gh auth status >/dev/null 2>&1 && echo "gh: authed" || echo "WARN: gh missing/unauthed — PR creation will need it"

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
for c in wf-distill wf-classify wf-emit-ts wf-preflight-docx wf-cycle-status; do
  command -v "$c" >/dev/null || { echo "FATAL: $c not on PATH after install"; exit 1; }
done
echo "engine commands: OK"

echo "── distiller skill ──"
SKILL_SRC="$HERE/distiller"
SKILL_DST="$HOME/.claude/skills/seo-distiller"
if [ -d "$SKILL_SRC" ]; then
  mkdir -p "$SKILL_DST"
  cp -R "$SKILL_SRC/." "$SKILL_DST/"
  echo "distiller skill installed/synced from module"
else
  echo "WARN: distiller/ not found in repo — install the distiller manually"
fi

echo ""
echo "READY. Activate with:  source $VENV/bin/activate"
echo "Then follow docs/HOW-IT-WORKS.md stage by stage."
