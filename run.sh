#!/bin/bash
# Run any engine command inside the container, with the operator's credentials.
#
#   ./run.sh wf-onboard acme/roofing-site acmeroofing.com --clients-dir /clients
#   ./run.sh wf-site-health --project /clients/roofing-site
#   ./run.sh bash                     # poke around
#
# ponytail: GH_TOKEN, not the -v ~/.config/gh mount the Dockerfile documents.
# On macOS the gh token lives in the login keyring, so that mount carries
# config but no credential and every gh call in the container 401s.
#
# GH_TOKEN authenticates gh but NOT plain git, so wf-site-remediate's push
# would fail after a clean run. GIT_CONFIG_* below hands git the same token.
#
# `./run.sh wf-dashboard` publishes the port to the host loopback only. The
# --host 0.0.0.0 is the CONTAINER's interface, not your machine's.
set -euo pipefail

CLIENTS="${CLIENTS_DIR:-$HOME/clients}"
CLAUDE_HOME="$HOME/.claude-docker"
mkdir -p "$CLIENTS" "$CLAUDE_HOME"

# remediate.py only shells out to `claude`; it never reads ANTHROPIC_API_KEY.
# So EITHER auth works — a key in the env, or a subscription login persisted in
# $CLAUDE_HOME. One-time, if you have no key:   ./run.sh claude /login
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ ! -s "$CLAUDE_HOME/.credentials.json" ]; then
  echo "WARN: no ANTHROPIC_API_KEY and no saved login — wf-site-remediate has no writer." >&2
  echo "      Fix with:  ./run.sh claude /login       (everything else runs fine without it)" >&2
fi

[ -t 0 ] && TTY=-it || TTY=-i   # ponytail: -t dies outside a terminal (CI, pipes)

# Only the dashboard needs a port; publishing on every run would collide with it.
PUB=()
if [ "${1:-}" = "wf-dashboard" ]; then
  PUB=(-p 127.0.0.1:8765:8765)
  set -- "$@" --host 0.0.0.0 --clients-dir /clients
  mkdir -p "$HOME/.cache/seo_agent"   # run logs outlive --rm
  PUB+=(-v "$HOME/.cache/seo_agent:/root/.cache/seo_agent")
fi

exec docker run --rm $TTY ${PUB[@]+"${PUB[@]}"} \
  ${ANTHROPIC_API_KEY:+-e ANTHROPIC_API_KEY} \
  -v "$CLAUDE_HOME:/root/.claude" \
  -e GH_TOKEN="$(gh auth token)" \
  -e GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-$(git config user.name || echo Ethan5767)}" \
  -e GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-$(git config user.email || echo nhatest040@gmail.com)}" \
  -e GIT_COMMITTER_NAME="${GIT_AUTHOR_NAME:-$(git config user.name || echo Ethan5767)}" \
  -e GIT_COMMITTER_EMAIL="${GIT_AUTHOR_EMAIL:-$(git config user.email || echo nhatest040@gmail.com)}" \
  -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0="credential.https://github.com.helper" \
  -e GIT_CONFIG_VALUE_0='!gh auth git-credential' \
  -v "$CLIENTS:/clients" \
  seo-agent "$@"
