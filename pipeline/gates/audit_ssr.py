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

GLOBAL = re.compile(r"\b(window|document)\.[A-Za-z_$]")
TYPEOF = re.compile(r"typeof\s+(window|document|globalThis|navigator|self|localStorage|sessionStorage)\b")
CONTROL = re.compile(r"\b(if|for|while|switch|catch|else)\b\s*\([^)]*\)\s*$")
FUNC_SIG = re.compile(r"\bfunction\b\s*\*?\s*[\w$]*\s*\([^)]*\)\s*$")
NAMED_CALL = re.compile(r"[\w$]\s*\([^)]*\)\s*$")
GUARD_IF = re.compile(r"\bif\s*\(.*typeof\s+(window|document|globalThis|navigator|self|localStorage|sessionStorage).*\)\s*$")
EARLY_RETURN_GUARD = re.compile(r"typeof\s+(window|document)\s*===?\s*['\"]undefined['\"]")


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


def _is_func_open(pre: str) -> bool:
    """Does the masked text before a `{` open a FUNCTION body (vs an object/block/control)?"""
    s = pre.rstrip()
    if s.endswith('=>'):
        return True
    if FUNC_SIG.search(s):
        return True
    if s.endswith(')') and not CONTROL.search(s) and NAMED_CALL.search(s):
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

    for idx, mline in enumerate(masked_lines):
        rline = raw_lines[idx] if idx < len(raw_lines) else ""
        same_line_guard = bool(TYPEOF.search(mline))
        access_cols = {m.start(1) for m in GLOBAL.finditer(mline)}

        # early-return guard (`if (typeof window === 'undefined') return`) guards the rest of the fn
        if same_line_guard and EARLY_RETURN_GUARD.search(mline) and ('return' in mline or 'throw' in mline):
            guard_frames.append(func_frames[-1] if func_frames else 0)

        for col, ch in enumerate(mline):
            if col in access_cols:
                guarded = same_line_guard or bool(guard_frames)
                if not guarded and len(func_frames) < 2:
                    hit = GLOBAL.search(rline)
                    issues.append((idx + 1, hit.group(0) if hit else "window/document",
                                   rline.strip()[:120]))
            if ch == '{':
                pre = mline[:col]
                if _is_func_open(pre):
                    func_frames.append(brace_depth)
                if same_line_guard and GUARD_IF.search(pre):
                    guard_frames.append(brace_depth)
                brace_depth += 1
            elif ch == '}':
                brace_depth = max(0, brace_depth - 1)
                while func_frames and func_frames[-1] >= brace_depth:
                    func_frames.pop()
                while guard_frames and guard_frames[-1] >= brace_depth:
                    guard_frames.pop()
    return issues


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

    candidates = [project / "src"]
    if cfg.get("repo", {}).get("pages_dir", ""):
        for p in project.glob("**/src"):
            if p.is_dir() and p not in candidates and "node_modules" not in str(p) and ".next" not in str(p):
                candidates.append(p)
    src = next((c for c in candidates if c.exists()), None)
    if not src:
        print(f"[SKIP] No src/ directory in {project}"); sys.exit(0)

    all_issues = {}
    for ext in ("tsx", "ts", "jsx", "js"):
        for f in src.rglob(f"*.{ext}"):
            if "node_modules" in str(f) or ".next" in str(f):
                continue
            issues = scan_file(f)
            if issues:
                all_issues[str(f.relative_to(project))] = issues

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
