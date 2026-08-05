#!/usr/bin/env python3
"""
baseline.py — pre-existing-debt baseline + ratchet for the gate suite.

WHY THIS EXISTS
---------------
Every gate in this suite is proven correct, and on a real hand-built client the
suite is still unusable as a *blocking* PR check, because the client's LEGACY
content fails it en masse. On the Acme pilot: 60/61 pages lack a content
capsule, 31/61 duplicate a sibling, 37/63 images blow their byte budget. There
were only ever two settings — block every PR forever, or run advisory and
enforce nothing. Both enforce nothing.

A mature gate distinguishes PRE-EXISTING DEBT from a NEW REGRESSION. That is the
entire job of this module. Record today's findings once; from then on the gate
blocks only findings that are NOT in that record. The debt stays visible and
countable, but it stops holding the merge hostage, and it can never grow.

    baseline  = the set of findings that existed when we started enforcing
    ratchet   = the baseline may only SHRINK, never grow

THE SAFETY BOUNDARY — READ BEFORE WIDENING `BASELINEABLE`
---------------------------------------------------------
Baselining is a decision to KEEP SHIPPING a known-bad thing. That is acceptable
only when the finding is *content debt* — undesirable, costly in ranking terms,
fixable on a schedule, and harmful to nobody today. It is NOT acceptable when
the finding is a live liability or a correctness/integrity failure, because for
those the passage of time makes the finding worse, not more tolerable.

NEVER baselineable (`NEVER_BASELINEABLE`, hard-coded, attempting it is an ERROR):

  forbidden_sweep   LEGAL EXPOSURE. The forbidden-phrase ledger encodes claims
                    the client may not legally make (warranty/price/insurance
                    language). A banned phrase that has been live for a year is
                    not "legacy debt" — it is a live liability that has been
                    accruing risk the whole time. Baselining it would mean the
                    pipeline formally signs off on shipping it. Never.
  audit_ssr         CORRECTNESS. SSR-unsafe `window`/`document` in the render
                    path is a runtime crash / blank page under static export,
                    not a quality opinion. A "pre-existing" crash is still a
                    crash on every request.
  fingerprint_check INTEGRITY / PROVENANCE. Invisible-Unicode and generator
                    fingerprints are AI-authorship tells and tamper signals.
                    Their entire value is that the answer is always zero; a
                    tolerated non-zero baseline destroys the signal.
  parity_check      STRUCTURAL TRUTH. sitemap == routes == llms.txt. Parity is
                    a bidirectional invariant, not a count of defects — a
                    "pre-existing" mismatch means the site's own map is lying,
                    and every downstream gate reasons off that map.
  orphan_check      STRUCTURAL TRUTH + this is the original Acme bug, the
                    highest-value gate in the suite. An orphaned URL is
                    unreachable and uncrawlable today; age does not soften it.

Baselineable (`BASELINEABLE`) — all carry genuine legacy CONTENT debt that a
human must work down page by page, and none of which is unsafe to ship for
another week:

  capsule_check       missing interrogative-H2 / answer-first capsule (§20)
  noncommodity_check  missing proprietary variable / sibling duplication (§21)
  image_budget_check  oversized image bytes
  lcp_hygiene_check   dimensionless <img> / lazy-loaded declared hero
  pages_are_data_check bespoke-heavy static route (architecture drift)
  check_headings      heading casing
  llms_sales_purge    CTA copy in llms.txt
  audit_built         the 30-point per-page audit (titles, metas, alt text, ...)

The rule for anyone tempted to add to `BASELINEABLE`: if a reviewer would be
uncomfortable writing "we have decided to keep shipping this" next to the
finding, it does not belong here. Widening this list is a decision to be made
by a human in a PR, with the reasoning written down — never as a convenience
during a red build.

STABLE FINGERPRINTS
-------------------
A finding must be recognisable across builds even as the emitter reflows the
HTML and every line number moves. A fingerprint is therefore computed over:

    gate | code | location | normalized context

and DELIBERATELY excludes line numbers, byte offsets, file sizes, word counts,
overlap ratios and any other measured quantity — those churn on every content
edit and would make the baseline flaky (a finding would "become new" merely by
getting slightly worse). `location` is a page ROUTE or a repo-relative FILE
path, never an absolute path. `context` is the stable identity of the thing
complained about (the offending heading text, the image tier, the blocked
phrase), whitespace-normalized.

Where several identical findings occur in one file (e.g. three dimensionless
<img> tags with the same src), an occurrence ORDINAL disambiguates them. The
ordinal is assigned in document order, so fixing one of the three retires the
highest ordinal and leaves the rest matching — the ratchet still shrinks.

USAGE
-----
    # record (writes into the CLIENT repo — baselines are client state)
    wf-gate-baseline --project /path/to/client --out docs/gate-baseline.json

    # ratchet check in CI: fails on new findings, reports fixable entries
    wf-gate-baseline --project /path/to/client --baseline docs/gate-baseline.json --check

    # refresh after fixing debt (removals are free; ADDING requires --accept-new)
    wf-gate-baseline --project /path/to/client --out docs/gate-baseline.json --refresh

Individual gates take `--baseline PATH` and then report:
    "N pre-existing (ignored), M new (blocking)" — exiting non-zero only on M.

Exit codes:
    0  ok (record written / check clean)
    1  new findings present (--check), or a gate refused
    2  usage error
    3  attempt to baseline a NEVER_BASELINEABLE gate (loud refusal)
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SCHEMA = "meridian-gate-baseline/1"

# ── the safety boundary (see module docstring for the reasoning) ──────────────
# Hard-coded on purpose. Attempting to baseline any of these is a LOUD ERROR,
# never a silent skip, so a misconfigured CI job cannot quietly disarm the gates
# that exist to stop legal and structural failures.
NEVER_BASELINEABLE = {
    "forbidden_sweep": "legal exposure — a pre-existing banned phrase is still a live liability",
    "audit_ssr": "correctness — a pre-existing SSR crash still crashes on every request",
    "fingerprint_check": "integrity — the invisible-Unicode signal is only worth anything at zero",
    "parity_check": "structural truth — sitemap/routes/llms parity is an invariant, not a defect count",
    "orphan_check": "structural truth — an orphaned URL is unreachable today regardless of age",
    "rules_selftest": "meta-integrity — a broken ruleset checker is a disarmed legal gate; it can never carry accepted debt",
}

BASELINEABLE = {
    "capsule_check",
    "noncommodity_check",
    "image_budget_check",
    "lcp_hygiene_check",
    "pages_are_data_check",
    "check_headings",
    "llms_sales_purge",
    "audit_built",
}


class BaselineError(RuntimeError):
    """Raised on a refusal — notably an attempt to baseline an excluded gate."""


def assert_baselineable(gate: str) -> None:
    """Guard every entry point. Excluded gates fail LOUD, never silently skip."""
    if gate in NEVER_BASELINEABLE:
        raise BaselineError(
            f"REFUSED: gate '{gate}' is NEVER baselineable — {NEVER_BASELINEABLE[gate]}. "
            f"Baselining it would mean the pipeline formally signs off on shipping the "
            f"finding. Fix the finding instead. (see pipeline/lib/baseline.py docstring)"
        )
    if gate not in BASELINEABLE:
        raise BaselineError(
            f"REFUSED: gate '{gate}' is not in the baselineable allow-list "
            f"{sorted(BASELINEABLE)}. Adding to that list is a documented human "
            f"decision, not a convenience during a red build."
        )


# ── findings ─────────────────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def normalize_context(value: str) -> str:
    """Collapse whitespace and trim. Case is PRESERVED — for check_headings the
    casing IS the finding, so lowercasing here would collapse distinct findings."""
    return _WS_RE.sub(" ", str(value or "")).strip()


def fingerprint(gate: str, code: str, location: str, context: str = "", ordinal: int = 0) -> str:
    """Stable 16-hex identity for a finding.

    Deliberately excludes line numbers and any measured quantity (bytes, words,
    overlap ratios): those churn on every content edit and would let a finding
    silently become "new" merely by getting worse."""
    parts = [gate, code, location, normalize_context(context), str(ordinal)]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


class Finding:
    """One gate finding, in the shape the baseline records and compares.

    gate      module name, e.g. 'capsule_check'
    code      the rule that fired, e.g. 'capsule.interrogative_h2'
    location  page route or repo-relative file — never an absolute path
    context   stable identity of the offending thing (heading text, image tier,
              blocked phrase). Excludes measured quantities.
    detail    human-only extra shown in gate output; NEVER fingerprinted, so it
              is free to carry volatile numbers (sizes, line numbers, counts).
    ordinal   disambiguates repeated identical findings in one file.
    """

    __slots__ = ("gate", "code", "location", "context", "detail", "ordinal")

    def __init__(self, gate: str, code: str, location: str, context: str = "",
                 detail: str = "", ordinal: int = 0):
        self.gate = gate
        self.code = code
        self.location = location
        self.context = normalize_context(context)
        self.detail = detail
        self.ordinal = ordinal

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.gate, self.code, self.location, self.context, self.ordinal)

    def where(self) -> str:
        """Human-readable location line for gate output and the baseline file."""
        base = f"{self.location}"
        if self.context:
            base += f" [{self.context}]"
        if self.ordinal:
            base += f" #{self.ordinal + 1}"
        return base

    def to_entry(self, recorded: str) -> dict:
        return {
            "gate": self.gate,
            "code": self.code,
            "fingerprint": self.fingerprint,
            "location": self.where(),
            "recorded": recorded,
        }

    def to_json(self) -> dict:
        return {"gate": self.gate, "code": self.code, "location": self.location,
                "context": self.context, "detail": self.detail, "ordinal": self.ordinal}

    @classmethod
    def from_json(cls, d: dict) -> "Finding":
        return cls(d["gate"], d["code"], d.get("location", ""), d.get("context", ""),
                   d.get("detail", ""), int(d.get("ordinal", 0)))

    def sort_key(self):
        return (self.gate, self.location, self.code, self.context, self.ordinal)


def assign_ordinals(findings: list) -> list:
    """Assign document-order occurrence ordinals to findings that are otherwise
    identical. Call once, on the gate's findings, before fingerprinting."""
    seen: dict = {}
    for f in findings:
        key = (f.gate, f.code, f.location, f.context)
        f.ordinal = seen.get(key, 0)
        seen[key] = f.ordinal + 1
    return findings


def sort_findings(findings: list) -> list:
    """Deterministic order — the baseline file must be byte-identical across runs."""
    return sorted(findings, key=lambda f: f.sort_key())


# ── the baseline file ────────────────────────────────────────────────────────

class Baseline:
    """A recorded set of pre-existing findings, keyed by fingerprint."""

    def __init__(self, entries: list | None = None, meta: dict | None = None):
        self.entries = {e["fingerprint"]: e for e in (entries or [])}
        self.meta = meta or {}

    @classmethod
    def load(cls, path) -> "Baseline":
        p = Path(path)
        if not p.is_file():
            raise BaselineError(f"baseline file not found: {p}")
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            raise BaselineError(f"baseline file is not valid JSON: {p} ({e})")
        if data.get("schema") != SCHEMA:
            raise BaselineError(
                f"baseline schema mismatch in {p}: expected {SCHEMA!r}, got {data.get('schema')!r}")
        for e in data.get("entries", []):
            g = e.get("gate")
            if g in NEVER_BASELINEABLE:
                raise BaselineError(
                    f"REFUSED: baseline {p} contains an entry for NEVER-baselineable gate "
                    f"'{g}' — {NEVER_BASELINEABLE[g]}. Someone has tried to disarm a "
                    f"safety gate through the baseline file. Remove the entry.")
        meta = {k: v for k, v in data.items() if k != "entries"}
        return cls(data.get("entries", []), meta)

    def has(self, fp: str) -> bool:
        return fp in self.entries

    def for_gate(self, gate: str) -> dict:
        return {fp: e for fp, e in self.entries.items() if e.get("gate") == gate}

    def gates(self) -> list:
        return sorted({e.get("gate", "?") for e in self.entries.values()})

    def counts(self) -> dict:
        out: dict = {}
        for e in self.entries.values():
            out[e.get("gate", "?")] = out.get(e.get("gate", "?"), 0) + 1
        return out

    def write(self, path, project_slug: str, recorded: str | None = None) -> None:
        recorded = recorded or date.today().isoformat()
        entries = sorted(self.entries.values(),
                         key=lambda e: (e["gate"], e["location"], e["code"], e["fingerprint"]))
        doc = {
            "schema": SCHEMA,
            "project": project_slug,
            "recorded": recorded,
            "note": ("Pre-existing gate findings accepted as legacy debt. This file may only "
                     "SHRINK — adding entries requires wf-gate-baseline --accept-new. "
                     "Gates in NEVER_BASELINEABLE (forbidden_sweep, audit_ssr, "
                     "fingerprint_check, parity_check, orphan_check, rules_selftest) "
                     "can never appear here."),
            "gates": sorted({e["gate"] for e in entries}),
            "counts": {g: sum(1 for e in entries if e["gate"] == g)
                       for g in sorted({e["gate"] for e in entries})},
            "total": len(entries),
            "entries": entries,
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n")


# ── comparison used by the gates ─────────────────────────────────────────────

class Verdict:
    """Result of filtering a gate's findings against a baseline."""

    def __init__(self, gate: str, preexisting: list, new: list, baseline_path: str | None):
        self.gate = gate
        self.preexisting = preexisting
        self.new = new
        self.baseline_path = baseline_path

    @property
    def blocking(self) -> list:
        return self.new

    def summary(self) -> str:
        return (f"{self.gate}: {len(self.preexisting)} pre-existing (ignored), "
                f"{len(self.new)} new (blocking)")

    def report(self, stream=sys.stdout) -> None:
        print(f"  baseline: {self.baseline_path}", file=stream)
        print(f"  {self.summary()}", file=stream)


def partition(gate: str, findings: list, baseline: Baseline) -> Verdict:
    assert_baselineable(gate)
    pre, new = [], []
    for f in findings:
        (pre if baseline.has(f.fingerprint) else new).append(f)
    return Verdict(gate, pre, new, None)


def apply_baseline(gate: str, findings: list, baseline_path: str | None) -> Verdict:
    """Filter a gate's findings. With no baseline path every finding is 'new'
    (i.e. the gate behaves exactly as it did before this module existed)."""
    findings = sort_findings(assign_ordinals(list(findings)))
    if not baseline_path:
        return Verdict(gate, [], findings, None)
    assert_baselineable(gate)
    bl = Baseline.load(baseline_path)
    v = partition(gate, findings, bl)
    v.baseline_path = str(baseline_path)
    return v


def add_baseline_args(ap: argparse.ArgumentParser) -> None:
    """Wire the two standard flags onto a baselineable gate's parser."""
    ap.add_argument("--baseline", default=None,
                    help="gate-baseline.json: findings recorded there are reported "
                         "PRE-EXISTING and do not fail the run; anything else is NEW and does.")
    ap.add_argument("--emit-findings", default=None,
                    help=argparse.SUPPRESS)  # internal: wf-gate-baseline collects through this


def emit(path: str, findings: list) -> int:
    """Write the gate's findings as JSON for wf-gate-baseline to collect, so the
    recorder and the gate can never drift apart. Returns the gate's exit code."""
    findings = sort_findings(assign_ordinals(list(findings)))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps([f.to_json() for f in findings], indent=2) + "\n")
    return 0


def resolve(gate: str, findings: list, args) -> tuple:
    """Standard gate tail. Returns (verdict, early_exit_code).

    When --emit-findings was passed, early_exit_code is 0 and the gate must
    return it immediately without printing its normal report. A BaselineError
    (excluded gate, tampered/mismatched baseline file) is turned into a clean
    loud refusal with early_exit_code 3 — never a traceback — so a tampered
    baseline can never masquerade as a passing gate."""
    if getattr(args, "emit_findings", None):
        return None, emit(args.emit_findings, findings)
    try:
        return apply_baseline(gate, findings, getattr(args, "baseline", None)), None
    except BaselineError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return None, 3


# ── the recorder / ratchet CLI ───────────────────────────────────────────────

def _build_dir(project: Path) -> Path:
    from pipeline.lib.common import load_config, client_profile
    cfg = load_config(str(project))
    prof = client_profile(cfg, str(project))
    return project / prof.get("resolved_build_dir", "out").lstrip("./")


def _sitemap_urls(build: Path) -> list:
    sm = build / "sitemap.xml"
    if not sm.is_file():
        return []
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm.read_text(errors="replace"))


def gate_argv(gate: str, project: Path) -> list:
    """How wf-gate-baseline invokes each gate to collect its findings. The gate
    itself does the detection — this module never re-implements it."""
    build = _build_dir(project)
    mod = f"pipeline.gates.{gate}"
    if gate in ("capsule_check", "noncommodity_check", "pages_are_data_check"):
        return [sys.executable, "-m", mod, str(project)]
    if gate in ("image_budget_check", "lcp_hygiene_check"):
        return [sys.executable, "-m", mod, "--project", str(project)]
    if gate == "check_headings":
        return [sys.executable, "-m", mod, "--out", str(build), "--project", str(project)]
    if gate == "llms_sales_purge":
        return [sys.executable, "-m", mod, "--out", str(build), "--project", str(project)]
    if gate == "audit_built":
        return [sys.executable, "-m", mod, str(project), str(build)] + _sitemap_urls(build)
    raise BaselineError(f"no invocation registered for gate '{gate}'")


def collect(project: Path, gates: list, tmpdir: Path, verbose: bool = False) -> tuple:
    """Run each gate in --emit-findings mode and merge. Returns (findings, errors)."""
    findings, errors = [], []
    for gate in gates:
        assert_baselineable(gate)
        out = tmpdir / f"{gate}.json"
        argv = gate_argv(gate, project) + ["--emit-findings", str(out)]
        r = subprocess.run(argv, capture_output=True, text=True)
        if not out.is_file():
            errors.append(f"{gate}: produced no findings file (exit {r.returncode}). "
                          f"{(r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else ''}")
            continue
        got = [Finding.from_json(d) for d in json.loads(out.read_text())]
        if verbose:
            print(f"  {gate}: {len(got)} finding(s)")
        findings += got
    return sort_findings(assign_ordinals(findings)), errors


def _counts(findings: list) -> dict:
    out: dict = {}
    for f in findings:
        out[f.gate] = out.get(f.gate, 0) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-gate-baseline",
        description="Record and ratchet the pre-existing-debt baseline for the baselineable gates.")
    ap.add_argument("--project", required=True, help="CLIENT project dir (holds docs/client-config.yml)")
    ap.add_argument("--out", default=None,
                    help="write the baseline here (default docs/gate-baseline.json inside --project)")
    ap.add_argument("--baseline", default=None,
                    help="existing baseline to compare against (default: --out path)")
    ap.add_argument("--check", action="store_true",
                    help="ratchet check: fail on findings absent from the baseline; "
                         "REPORT (do not fail) baseline entries that have been fixed.")
    ap.add_argument("--refresh", action="store_true",
                    help="rewrite the baseline, dropping entries that are now fixed. "
                         "Refuses to ADD entries unless --accept-new is also given.")
    ap.add_argument("--accept-new", action="store_true",
                    help="explicitly accept findings not already in the baseline. Required to "
                         "grow the baseline — stops a regression being laundered in by re-running "
                         "the recorder.")
    ap.add_argument("--gates", default=None,
                    help="comma-separated subset of gates (default: all baselineable)")
    ap.add_argument("--tmpdir", default=None, help="where to stage per-gate findings (default: a temp dir)")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"[ERROR] project dir not found: {project}", file=sys.stderr)
        return 2

    if args.gates:
        gates = [g.strip() for g in args.gates.split(",") if g.strip()]
        for g in gates:
            try:
                assert_baselineable(g)
            except BaselineError as e:
                print(f"[ERROR] {e}", file=sys.stderr)
                return 3
    else:
        gates = sorted(BASELINEABLE)

    out_path = Path(args.out) if args.out else (project / "docs" / "gate-baseline.json")
    if not out_path.is_absolute():
        out_path = project / out_path
    bl_path = Path(args.baseline) if args.baseline else out_path
    if not bl_path.is_absolute():
        bl_path = project / bl_path

    import tempfile
    tmp_ctx = None
    if args.tmpdir:
        tmpdir = Path(args.tmpdir)
        tmpdir.mkdir(parents=True, exist_ok=True)
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="wf-gate-baseline-")
        tmpdir = Path(tmp_ctx.name)

    try:
        print(f"wf-gate-baseline: collecting findings for {len(gates)} gate(s) under {project}")
        findings, errors = collect(project, gates, tmpdir, verbose=True)
        for e in errors:
            print(f"[WARN] {e}", file=sys.stderr)

        current = {f.fingerprint: f for f in findings}
        counts = _counts(findings)

        # ── check mode: the ratchet ──────────────────────────────────────────
        if args.check:
            try:
                bl = Baseline.load(bl_path)
            except BaselineError as e:
                print(f"[ERROR] {e}", file=sys.stderr)
                return 2
            recorded = bl.entries
            new = [f for fp, f in current.items() if fp not in recorded]
            fixed = [e for fp, e in recorded.items() if fp not in current]
            still = len(recorded) - len(fixed)

            print(f"\nratchet check against {bl_path}")
            print(f"  baseline entries: {len(recorded)}  |  current findings: {len(current)}")
            print(f"  {still} pre-existing (ignored), {len(new)} new (blocking)")

            if fixed:
                print(f"\n  [SHRINK AVAILABLE] {len(fixed)} baseline entry(ies) no longer reproduce — "
                      f"the debt has been paid down:")
                for e in sorted(fixed, key=lambda x: (x["gate"], x["location"]))[:40]:
                    print(f"    FIXED  {e['gate']}  {e['code']}  {e['location']}")
                if len(fixed) > 40:
                    print(f"    ... and {len(fixed) - 40} more")
                print(f"  Refresh so the count can only go down:")
                print(f"    wf-gate-baseline --project {project} --out {bl_path} --refresh")

            if new:
                print(f"\n[FAIL] {len(new)} NEW finding(s) not present in the baseline:")
                for f in sort_findings(new):
                    print(f"    NEW    {f.gate}  {f.code}  {f.where()}"
                          + (f"  — {f.detail}" if f.detail else ""))
                print("\n  These are regressions, not legacy debt. Fix them. If one is genuinely "
                      "acceptable, add it deliberately with --refresh --accept-new.")
                return 1

            print("\n[OK] no new findings — the ratchet holds.")
            return 0

        # ── record / refresh mode ────────────────────────────────────────────
        existed = bl_path.is_file()
        prior = Baseline.load(bl_path) if existed else None

        if existed and not args.refresh and not args.accept_new:
            print(f"\n[ERROR] {bl_path} already exists. Recording over an existing baseline is "
                  f"how a regression gets laundered into the accepted set.\n"
                  f"  To pay down debt (drop fixed entries, never add):   --refresh\n"
                  f"  To deliberately accept new findings as debt:        --refresh --accept-new\n"
                  f"  To just verify the ratchet:                          --check",
                  file=sys.stderr)
            return 2

        added = []
        if prior is not None:
            added = [f for fp, f in current.items() if not prior.has(fp)]
            if added and not args.accept_new:
                print(f"\n[FAIL] refusing to grow the baseline: {len(added)} finding(s) are NOT in "
                      f"{bl_path}. The baseline may only SHRINK.", file=sys.stderr)
                for f in sort_findings(added)[:40]:
                    print(f"    NEW  {f.gate}  {f.code}  {f.where()}", file=sys.stderr)
                if len(added) > 40:
                    print(f"    ... and {len(added) - 40} more", file=sys.stderr)
                print("\n  Fix them, or accept them explicitly with --accept-new.", file=sys.stderr)
                return 1

        new_bl = Baseline()
        recorded = date.today().isoformat()
        for f in findings:
            # keep the ORIGINAL recorded date for entries carried over, so the
            # age of the debt stays visible across refreshes.
            prev = prior.entries.get(f.fingerprint) if prior else None
            entry = f.to_entry(prev.get("recorded", recorded) if prev else recorded)
            new_bl.entries[f.fingerprint] = entry

        slug = project.name
        try:
            from pipeline.lib.common import load_config
            slug = load_config(str(project)).get("client") or slug
        except Exception:
            pass
        new_bl.write(out_path, slug, recorded)

        print(f"\nbaseline written -> {out_path}")
        print(f"  total entries: {len(new_bl.entries)}")
        for g in sorted(counts):
            print(f"    {g:<22} {counts[g]}")
        if prior is not None:
            dropped = len([fp for fp in prior.entries if fp not in current])
            print(f"  dropped (fixed): {dropped}   added (accepted): {len(added)}")
        else:
            print(f"  NOTE: this is the INITIAL baseline — every current finding is now accepted "
                  f"as legacy debt. From here it may only shrink.")
        print(f"  Commit this file to the CLIENT repo (it is client state, per Model A).")
        return 0

    except BaselineError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 3
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


if __name__ == "__main__":
    sys.exit(main())
