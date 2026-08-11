#!/usr/bin/env python3
"""Scan source files for SSR-unsafe patterns: bare document/window accessed during
SERVER render (module top-level or component render body) without a typeof guard.
Prevents silent SSR shell builds (the BLH Florida / Northstar blank-shell disasters).

A window/document access is SSR-DANGEROUS only if it runs during server render:
  - at module top-level (function depth 0), or
  - directly in a component render body (function depth 1)
It is SSR-SAFE (not flagged) when:
  - it sits inside a string/template/comment (e.g. a Next <Script> gtag/GTM body), OR
  - it is typeof-guarded (`typeof window !== 'undefined'`) in the same line or the
    enclosing block / function, OR
  - it is nested >=2 functions deep — i.e. inside an event handler, useEffect /
    useCallback callback, addEventListener / setTimeout / .then callback, etc. — which
    do not execute during server render.

This is a heuristic (not a full TS parser): it masks strings/comments and tracks
brace-scoped function depth + typeof guards. Limitation: window/document referenced
inside a ${} template interpolation that is itself rendered at SSR is masked (rare);
the dangerous module-level / render-body patterns are not in template literals.

Usage: python3 audit-ssr.py [PROJECT_DIR]
"""
import sys, re
from datetime import date
from pathlib import Path
from pipeline.lib.common import load_config, audit_log_dir

CANNOT_JUDGE_EXIT = 4      # same meaning the forbidden sweep gives it: no input to judge

SOURCE_EXTS = ("tsx", "ts", "jsx", "js", "mjs", "cjs")

# A DENYLIST, not an allowlist, and that is the whole design decision.
#
# This gate used to look for a folder called `src/` and exit 0 when it found
# none. `create-next-app` asks whether you want `src/` and the DEFAULT ANSWER IS
# NO, so every client who took the default had a never-baselineable correctness
# gate silently passing over their entire codebase (B-027).
#
# The tempting fix is to derive the roots from the framework — app/ for Next
# app-router, pages/ for pages-router, src/ for Vite. Don't. `framework_family`
# returns None for anything that is not next/vite/wordpress, so an allowlist
# scans NOTHING for the next client on a framework this repo has not met, which
# is the same bug wearing a different hat. A denylist degrades safely: an
# unknown framework gets over-scanned, never under-scanned.
NON_SOURCE_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", ".svelte-kit", ".turbo", ".vercel",
    "out", "dist", "build", "coverage", "public", "static", "vendor",
    "docs", ".venv", "venv", "__pycache__",
}

GLOBAL = re.compile(r"\b(window|document)\.[A-Za-z_$]")
TYPEOF = re.compile(r"typeof\s+(window|document|globalThis|navigator|self|localStorage|sessionStorage)\b")
CONTROL = re.compile(r"\b(if|for|while|switch|catch|else)\b\s*\([^)]*\)\s*$")
FUNC_SIG = re.compile(r"\bfunction\b\s*\*?\s*[\w$]*\s*\([^)]*\)\s*$")
NAMED_CALL = re.compile(r"[\w$]\s*\([^)]*\)\s*$")
GUARD_IF = re.compile(r"\bif\s*\(.*typeof\s+(window|document|globalThis|navigator|self|localStorage|sessionStorage).*\)\s*$")
# NOTE: this one is matched against the RAW line, never the masked one — `_mask`
# blanks string contents, so `typeof window === "undefined"` masks to
# `typeof window ===` and the quoted literal this pattern requires is gone. It
# never matched anything until B-036. It stays honest because the caller also
# requires the MASKED line to carry a `typeof`, which a commented-out or
# stringified guard cannot.
EARLY_RETURN_GUARD = re.compile(r"typeof\s+(window|document)\s*===?\s*['\"]undefined['\"]")
# Opens a paren group that belongs to a function signature: `function`, with or
# without a name, `async`, `export` or `export default` in front. Used to carry
# signature state across lines — see `_is_func_open`.
FUNC_SIG_OPEN = re.compile(r"\bfunction\b\s*\*?\s*[\w$]*\s*$")


def _mask(text: str) -> str:
    """Replace string/template/comment contents with spaces (length + newline preserving)
    so braces and `window.`/`document.` inside them are not parsed as code."""
    out = []
    i, n = 0, len(text)
    state = None  # None | "'" | '"' | '`' | 'line' | 'block'
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if state is None:
            if c == '/' and nxt == '/':
                state = 'line'; out.append('  '); i += 2; continue
            if c == '/' and nxt == '*':
                state = 'block'; out.append('  '); i += 2; continue
            if c in ('"', "'", '`'):
                state = c; out.append(' '); i += 1; continue
            out.append(c); i += 1; continue
        if state == 'line':
            if c == '\n':
                state = None; out.append('\n'); i += 1; continue
            out.append(' '); i += 1; continue
        if state == 'block':
            if c == '*' and nxt == '/':
                state = None; out.append('  '); i += 2; continue
            out.append('\n' if c == '\n' else ' '); i += 1; continue
        # inside a string literal (', ", `)
        if c == '\\':
            out.append('  '); i += 2; continue
        if c == state:
            state = None; out.append(' '); i += 1; continue
        out.append('\n' if c == '\n' else ' '); i += 1; continue
    return ''.join(out)


def _is_func_open(pre: str, sig_close: bool = False) -> bool:
    """Does the masked text before a `{` open a FUNCTION body (vs an object/block/control)?

    `sig_close` is set by the caller when the `)` immediately behind this `{`
    closed a paren group that a `function` keyword opened — which is the only way
    to see a signature spread over several lines (B-036):

        export default function AddressPanels({    <- `{` here is DESTRUCTURING
          addresses,
        }: Props) {                                <- `{` here opens the body

    Neither line can be recognised on its own: the first has no closing paren, the
    second has no `function`. Every React component written with named props looks
    like this, and without it the component's own frame was never counted, so
    every event handler inside it read as a render body.
    """
    s = pre.rstrip()
    if s.endswith('=>'):
        return True
    if FUNC_SIG.search(s):
        return True
    if s.endswith(')') and not CONTROL.search(s) and (sig_close or NAMED_CALL.search(s)):
        return True
    return False


def scan_file(path: Path) -> list:
    """Returns list of (line_num, pattern, snippet) for SSR-dangerous usages."""
    issues = []
    try:
        raw = path.read_text()
    except Exception:
        return issues

    masked_lines = _mask(raw).splitlines()
    raw_lines = raw.splitlines()

    brace_depth = 0
    func_frames = []   # brace_depth at which each function body opened
    guard_frames = []  # brace_depth at which a typeof-guard scope opened
    paren_ctx = []     # per open paren: did a `function` keyword open this group?
    sig_close = False  # the last `)` closed a function signature's paren group

    for idx, mline in enumerate(masked_lines):
        rline = raw_lines[idx] if idx < len(raw_lines) else ""
        same_line_guard = bool(TYPEOF.search(mline))
        access_cols = {m.start(1) for m in GLOBAL.finditer(mline)}

        # Early-return guard (`if (typeof window === 'undefined') return`) guards
        # the rest of the fn. The quoted-literal half is read from the RAW line
        # because masking blanks it (B-036); `same_line_guard` on the MASKED line
        # is what still proves the guard is code rather than a comment.
        if same_line_guard and EARLY_RETURN_GUARD.search(rline) and ('return' in mline or 'throw' in mline):
            guard_frames.append(func_frames[-1] if func_frames else 0)

        for col, ch in enumerate(mline):
            if col in access_cols:
                guarded = same_line_guard or bool(guard_frames)
                if not guarded and len(func_frames) < 2:
                    hit = GLOBAL.search(rline)
                    issues.append((idx + 1, hit.group(0) if hit else "window/document",
                                   rline.strip()[:120]))
            if ch == '(':
                paren_ctx.append(bool(FUNC_SIG_OPEN.search(mline[:col])))
            elif ch == ')':
                sig_close = paren_ctx.pop() if paren_ctx else False
            elif ch == '{':
                pre = mline[:col]
                if _is_func_open(pre, sig_close):
                    func_frames.append(brace_depth)
                if same_line_guard and GUARD_IF.search(pre):
                    guard_frames.append(brace_depth)
                brace_depth += 1
                sig_close = False
            elif ch == '}':
                brace_depth = max(0, brace_depth - 1)
                while func_frames and func_frames[-1] >= brace_depth:
                    func_frames.pop()
                while guard_frames and guard_frames[-1] >= brace_depth:
                    guard_frames.pop()
            elif ch == ';':
                sig_close = False
    return issues


def source_files(project: Path, cfg: dict | None = None):
    """Every JS/TS source file in the repo, in sorted order, skipping the
    directories that are never source.

    The client's CONFIGURED build dir is excluded too, on top of the static list:
    a repo that emits to `.output/` or `_site/` would otherwise have its own
    generated bundles scanned and reported as SSR violations in files nobody
    wrote. Minified bundles are skipped for the same reason.
    """
    skip = set(NON_SOURCE_DIRS)
    repo_cfg = (cfg or {}).get("repo", {}) or {}
    # `build_dir` is the older spelling; common.py:127 normalizes both, so read both.
    build_dir = repo_cfg.get("build_output_dir") or repo_cfg.get("build_dir") or ""
    if isinstance(build_dir, str) and build_dir.strip():
        # NOT `.strip("./")` — that eats the leading dot of `.output` and would
        # exclude a directory named `output` while scanning the real one.
        bd = build_dir.strip()
        bd = bd[2:] if bd.startswith("./") else bd
        first = bd.strip("/").split("/")[0]
        if first:
            skip.add(first)

    out = []
    for f in sorted(project.rglob("*")):
        if f.suffix.lstrip(".") not in SOURCE_EXTS or not f.is_file():
            continue
        rel = f.relative_to(project)
        if skip & set(rel.parts[:-1]) or f.name.endswith((".min.js", ".min.mjs")):
            continue
        out.append(f)
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: audit-ssr.py [PROJECT_DIR]", file=sys.stderr); sys.exit(1)
    project = Path(sys.argv[1])
    # The SSR scan needs no client config; tolerate a missing config so this gate can
    # run as a blocking CI check before docs/client-config.yml exists.
    cfg = {}
    if (project / "docs" / "client-config.yml").exists():
        try:
            cfg = load_config(str(project))
        except SystemExit:
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    if cfg.get("repo", {}).get("framework") == "wordpress":
        print("[SKIP] WordPress client — SSR check not applicable."); sys.exit(0)

    all_issues = {}
    scanned = 0
    for f in source_files(project, cfg):
        scanned += 1
        issues = scan_file(f)
        if issues:
            all_issues[str(f.relative_to(project))] = issues

    if scanned == 0:
        # NOT a pass. Until 2026-08-10 this exited 0 with "[SKIP] No src/ directory",
        # so a never-baselineable correctness gate reported success over zero files
        # on every repo that took `create-next-app`'s default layout (B-027).
        print(f"[REFUSED] no source files found under {project} — this gate cannot "
              f"judge a tree it cannot see, and reporting that as a pass is how an "
              f"SSR crash ships. Looked for *.{{{','.join(SOURCE_EXTS)}}} outside "
              f"{', '.join(sorted(NON_SOURCE_DIRS))}. If this repo genuinely holds no "
              f"JS/TS, say so in docs/client-config.yml `repo.framework`.",
              file=sys.stderr)
        sys.exit(CANNOT_JUDGE_EXIT)

    log = audit_log_dir(str(project), date.today().isoformat())
    out = [f"# SSR Safety Audit — {date.today().isoformat()}", ""]
    if not all_issues:
        out.append("PASS — no SSR-dangerous document/window usage (module-level or render-body, unguarded).")
    else:
        out.append(f"FAIL — {sum(len(v) for v in all_issues.values())} SSR violations (run at server render, unguarded):")
        out.append("")
        for f, items in all_issues.items():
            out.append(f"## {f}")
            for line_no, pattern, snippet in items:
                out.append(f"  L{line_no}  {pattern}  -> {snippet}")
            out.append("")
    (log / "audit-ssr.md").write_text("\n".join(out))

    if all_issues:
        print(f"[FAIL] {len(all_issues)} files have SSR-dangerous patterns. See {log}/audit-ssr.md")
        sys.exit(9)
    print(f"[OK] No SSR violations found. See {log}/audit-ssr.md")


if __name__ == "__main__":
    main()
