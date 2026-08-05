#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# proof-assert.sh — the "no proof = it didn't happen" meta-gate.
#
# Every blocking gate is supposed to drop a proof file under
#   docs/audit-logs/<date>/
# This script asserts that an expected list of those proof files BOTH exist and
# are non-empty. It is the final gate: if the audit trail is missing, the cycle
# did not happen, regardless of what any green checkmark claims.
#
# Usage:
#   proof-assert.sh <AUDIT_DIR> <file1> [file2 ...]
#     AUDIT_DIR   directory holding this cycle's proof files,
#                 e.g. docs/audit-logs/2026-06-30
#     fileN       proof filenames expected inside AUDIT_DIR (relative),
#                 e.g. orphan-check.txt parity-check.txt em-dash.txt
#
#   # Or pass a manifest file (one expected filename per line, # = comment):
#   proof-assert.sh <AUDIT_DIR> --manifest expected-proofs.txt
#
# Examples:
#   proof-assert.sh docs/audit-logs/2026-06-30 \
#       orphan-check.txt parity-check.txt em-dash.txt headings.txt
#
# Exit codes:
#   0  every expected proof file exists and is non-empty
#   1  any missing or empty (lists each), or bad usage
# ---------------------------------------------------------------------------
set -uo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: proof-assert.sh <AUDIT_DIR> <file1> [file2 ...]" >&2
  echo "       proof-assert.sh <AUDIT_DIR> --manifest <manifest-file>" >&2
  exit 1
fi

AUDIT_DIR="$1"
shift

EXPECTED=()
if [ "${1:-}" = "--manifest" ]; then
  MANIFEST="${2:-}"
  if [ -z "$MANIFEST" ] || [ ! -f "$MANIFEST" ]; then
    echo "ERROR: manifest file not found: ${MANIFEST:-<none>}" >&2
    exit 1
  fi
  while IFS= read -r line; do
    line="${line%%#*}"                       # strip comments
    line="$(printf '%s' "$line" | tr -d '[:space:]')"  # trim whitespace
    [ -n "$line" ] && EXPECTED+=("$line")
  done < "$MANIFEST"
else
  EXPECTED=("$@")
fi

if [ ! -d "$AUDIT_DIR" ]; then
  echo "FAIL: audit dir does not exist: $AUDIT_DIR" >&2
  echo "      (no proof dir = the cycle did not happen)" >&2
  exit 1
fi

MISSING=0
OK=0
for name in "${EXPECTED[@]}"; do
  f="$AUDIT_DIR/$name"
  if [ ! -e "$f" ]; then
    echo "  MISSING  $f"
    MISSING=$((MISSING + 1))
  elif [ ! -s "$f" ]; then
    echo "  EMPTY    $f"
    MISSING=$((MISSING + 1))
  else
    bytes=$(wc -c < "$f" | tr -d ' ')
    echo "  OK       $f (${bytes} bytes)"
    OK=$((OK + 1))
  fi
done

echo "proof-assert: $OK present, $MISSING missing/empty (of ${#EXPECTED[@]} expected) in $AUDIT_DIR"
if [ "$MISSING" -gt 0 ]; then
  echo "FAIL: $MISSING expected proof file(s) missing or empty. No proof = it didn't happen."
  exit 1
fi
echo "PASS: all ${#EXPECTED[@]} expected proof files present and non-empty."
exit 0
