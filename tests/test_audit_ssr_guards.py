"""B-036 — the two things audit_ssr's docstring promises and did not do.

B-027 made this gate finally *look* at a default-layout Next repo. The first
real client it looked at, `lee-series-web`, produced **six violations in four
files, and all six were false positives**. That is the worse half of B-027's
lesson: a never-baselineable blocking gate that under-scans reports a silent
green, and one that over-reports makes a PR permanently red for no defect. Both
end with the gate being switched off.

Two independent defects, both in the "is this access actually reachable at
server render" half:

  (a) `_mask` blanks string contents before anything is scanned, so
      `typeof window === "undefined"` masks to `typeof window ===` — and
      EARLY_RETURN_GUARD requires the quoted literal. The early-return guard the
      docstring documents as supported has never once matched.

  (b) `_is_func_open` only recognises a signature whose closing `)` is on the
      same line as the `{`. `export default function Foo({ a, b }: Props) {`
      spread over several lines — the single most common way a React component
      with props is written — opened no function frame, so every event handler
      inside it read as depth 1 (a render body) instead of depth 2.

Fixtures are the real shapes, reduced. Every `must not flag` case below was an
actual finding on the client's PR #36.
"""
from __future__ import annotations

from pipeline.gates.audit_ssr import _is_func_open, scan_file


def scan(tmp_path, body: str, name="c.tsx"):
    p = tmp_path / name
    p.write_text(body)
    return scan_file(p)


# ── (a) the early-return guard ───────────────────────────────────────────────

def test_an_early_return_typeof_guard_protects_the_rest_of_the_function(tmp_path):
    """lee `components/checkout/PaywayCheckout.tsx`: three flags in a function
    whose FIRST LINE is the guard."""
    hits = scan(tmp_path, '''
export function loadPaywayScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  const existing = document.querySelector("script");
  const script = document.createElement("script");
  document.body.appendChild(script);
}
''')
    assert hits == [], f"guarded accesses flagged: {hits}"


def test_the_guard_works_with_single_quotes_and_with_document(tmp_path):
    """The masking bug was blind to the quote character, so both spellings and
    both globals have to be proven — not just the one the client happened to use."""
    for guard in ("typeof document === 'undefined'", 'typeof document === "undefined"'):
        hits = scan(tmp_path, f'''
export function f() {{
  if ({guard}) return null;
  return document.body;
}}
''')
        assert hits == [], f"{guard!r} did not guard: {hits}"


def test_a_guard_is_still_scoped_to_its_own_function(tmp_path):
    """Narrowed, not disarmed. A guard in one function must not license an
    unguarded access in the next one."""
    hits = scan(tmp_path, '''
export function guarded() {
  if (typeof window === "undefined") return;
  window.scrollTo(0, 0);
}
export function unguarded() {
  window.scrollTo(0, 0);
}
''')
    assert [h[0] for h in hits] == [7], f"expected only the unguarded line 7, got {hits}"


def test_a_commented_out_guard_does_not_count(tmp_path):
    """The fix reads the RAW line for the quoted literal. It stays honest because
    the masked line still has to prove the guard is code and not a comment."""
    hits = scan(tmp_path, '''
export function f() {
  // if (typeof window === "undefined") return;
  window.scrollTo(0, 0);
}
''')
    assert len(hits) == 1, f"a commented-out guard suppressed a real finding: {hits}"


# ── (b) multi-line function signatures ───────────────────────────────────────

def test_a_destructured_multi_line_signature_opens_a_function(tmp_path):
    assert _is_func_open("export default function AddressPanels(") is False, (
        "the line that opens the PARAM LIST is not the line that opens the body")
    # `}: Props) {` is unrecognisable in isolation — no `function`, no call. It
    # opens a body only because the caller saw the `)` close a paren group that a
    # `function` keyword opened, which is exactly what sig_close carries.
    assert _is_func_open("}: Props) ") is False
    assert _is_func_open("}: Props) ", sig_close=True) is True
    # And sig_close does not turn an object literal or a control block into one.
    assert _is_func_open("const o = ", sig_close=True) is False
    assert _is_func_open("  if (cond) ", sig_close=True) is False


def test_an_event_handler_in_a_multi_line_component_is_not_a_render_body(tmp_path):
    """lee `components/profile/AddressPanels.tsx:181`. `window.confirm` inside a
    click handler cannot run at server render; it read as depth 1 only because
    the component's own frame was never counted."""
    hits = scan(tmp_path, '''
export default function AddressPanels({
  addresses,
  onNavigate,
}: Props) {
  async function handleDelete() {
    if (!window.confirm("sure?")) return;
  }
  return <div onClick={handleDelete} />;
}
''')
    assert hits == [], f"an event handler was flagged as a render body: {hits}"


def test_a_render_body_access_is_still_caught_in_a_multi_line_component(tmp_path):
    """The point of counting the frame correctly is that depth 1 still means
    'runs at server render'. This is the disaster the gate exists for."""
    hits = scan(tmp_path, '''
export default function Shell({
  children,
}: Props) {
  const w = window.innerWidth;
  return <div>{w}{children}</div>;
}
''')
    assert [h[0] for h in hits] == [5], f"expected the render-body access at line 5, got {hits}"


def test_a_guarded_portal_after_a_multi_line_signature(tmp_path):
    """lee `components/checkout/AddressPopup.tsx:229` — both defects at once: a
    multi-line component AND an early-return guard on the line above the hit."""
    hits = scan(tmp_path, '''
export default function AddressPopup({
  open,
}: Props) {
  const modal = <div />;
  if (typeof document === "undefined") return null;
  return createPortal(modal, document.body);
}
''')
    assert hits == [], f"a guarded portal was flagged: {hits}"
