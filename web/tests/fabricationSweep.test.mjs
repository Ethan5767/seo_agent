import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

/**
 * The audit that produced this file found ~32 fabrications across the dashboard,
 * after seven had already been fixed by hand. The operator found every one of
 * those seven by eye, which is the wrong way to find them.
 *
 * The cleanup before this one had a SHAPE: someone emptied every fabricated
 * ARRAY and left honest comments, and never touched fabricated SCALARS, the
 * bodies of `.map()` calls, or object-literal return values. That boundary is
 * greppable, which is what this file is for.
 *
 * Comments are stripped before every check: several files now DOCUMENT the
 * fabrication they removed, and a naive grep reports a fixed bug as live.
 */
const root = new URL("../", import.meta.url);
const read = (f) => readFileSync(new URL(f, root), "utf8");
const strip = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "").replace(/^\s*\/\/.*$/gm, "");

function walk(dir) {
  const out = [];
  for (const e of readdirSync(new URL(dir + "/", root), { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === ".next") continue;
    if (e.isDirectory()) out.push(...walk(`${dir}/${e.name}`));
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(`${dir}/${e.name}`);
  }
  return out;
}
const SOURCES = [...walk("app"), ...walk("lib"), ...walk("components")];

/* ── a forecast nothing can honestly produce ─────────────────────────────── */

test("no screen forecasts a traffic lift", () => {
  // `projectedLift: +${Math.min(28, Math.max(6, sprintItems.length * 2.2))}%`
  // computed a percentage gain from the NUMBER OF TO-DO ITEMS, floored at 6% so
  // an empty plan still promised one. It shipped in the client-facing plan.
  // Forecasting organic lift needs a baseline, a control and a measured
  // outcome; this product has none of the three.
  for (const f of SOURCES) {
    const src = strip(read(f));
    assert.ok(!/projectedLift\s*:/.test(src), `${f}: a traffic forecast is back`);
    assert.ok(!/% Organic Visibility`/.test(src), `${f}: a visibility forecast is back`);
  }
});

/* ── never invent a path into a developer's brief ────────────────────────── */

test("no file path is guessed for the client's repository", () => {
  // The brief filled an unknown target with "components/SEOHead.tsx", and for
  // anything mentioning schema, "components/MedicalBusinessSchema.tsx" - one
  // pilot client's vertical, for every account. A guessed path is worse than no
  // path: it sends a developer to a file that may not exist, and reads as
  // though we looked.
  const plan = strip(read("app/api/plan/route.ts"));
  for (const invented of ["SEOHead.tsx", "MedicalBusinessSchema.tsx", "src/app/layout.tsx"]) {
    assert.ok(!plan.includes(invented), `plan route still guesses ${invented}`);
  }
  assert.match(plan, /targetFile: null/);
});

/* ── one client's copy must never reach another's screen ─────────────────── */

test("no pilot client's vertical is hardcoded anywhere", () => {
  // "Best Hospital & Medical Center in Phnom Penh", "50+ board-certified
  // international consultant physicians", "Ministry of Health Cambodia".
  // This is a confidentiality problem as much as a fabrication one.
  const offenders = [];
  for (const f of SOURCES) {
    const src = strip(read(f));
    for (const s of ["Phnom Penh", "board-certified", "Ministry of Health",
                     "MedicalOrganization", "NICU", "obstetric"]) {
      if (src.includes(s)) offenders.push(`${f} -> ${s}`);
    }
  }
  assert.deepEqual(offenders, [], "one client's copy is rendered for every client");
});

/* ── fabricated data must never be persisted ─────────────────────────────── */

test("no invented measurement is written to the database", () => {
  // Every other fabrication is a render-time lie you can delete. This one was
  // INSERTed and read back later as history.
  const snap = strip(read("app/api/traffic/snapshot/route.ts"));
  assert.ok(!/mobile:\s*68/.test(snap), "the 68/32 device default is back");
  assert.match(snap, /devices = \{\}/);
});

/* ── the generators refuse without evidence ──────────────────────────────── */

test("both model routes refuse to write from nothing", () => {
  // A model asked to work from nothing produces something that reads exactly
  // like real work. `/api/fix/advise` always refused; `/api/content/generate`
  // did not, and its two tools with no required fields had no guard at all.
  const fix = strip(read("app/api/fix/advise/route.ts"));
  const gen = strip(read("app/api/content/generate/route.ts"));
  assert.match(fix, /"error" in built/);
  assert.match(gen, /hasEvidence/);
  assert.match(gen, /Nothing measured to write from/);
  // The guard must precede the spawn, so refusing costs nothing.
  assert.ok(gen.indexOf("hasEvidence") < gen.indexOf('spawn('),
    "the refusal must come before the model is started");
});

/* ── the scan carries the page, so nothing has to invent it ──────────────── */

test("the content tools are given the page the scan fetched", () => {
  // `ContentContext.page` was declared, read by five of seven tools, and passed
  // by nobody - so "Rewrites the scanned page" rewrote nothing. B-007.
  const dash = strip(read("app/ReaiDashboard.tsx"));
  assert.match(dash, /page=\{scannedPage as any\}/, "ContentPanel gets no page");
  const panel = strip(read("components/dashboard/ContentPanel.tsx"));
  assert.match(panel, /queries, page \}/, "ContentPanel does not accept a page");
  assert.match(panel, /queries, page \}\) as any/, "the page never reaches the context");
});

test("the content panel sends the session", () => {
  // It used a plain fetch while the session lives in localStorage, so every
  // content tool returned 401 outside a dev box.
  const panel = strip(read("components/dashboard/ContentPanel.tsx"));
  assert.match(panel, /authedFetch\("\/api\/content\/generate"/);
  assert.ok(!/[^d]fetch\("\/api\/content/.test(panel));
});

test("hooks run before any early return", () => {
  // `if (!tool) return null` sat above four useMemo/useEffect calls, so an
  // unknown toolId changed the hook count between renders.
  const panel = read("components/dashboard/ContentPanel.tsx");
  const guard = panel.indexOf("if (!tool) return null;");
  assert.ok(guard > panel.lastIndexOf("useEffect("),
    "the early return must come after every hook");
});

/* ── a chart is a claim ──────────────────────────────────────────────────── */

test("no chart is drawn from a hardcoded series", () => {
  // A sparkline fed [4.1, 4.3, 4.5, 4.6, 4.7, 4.8] is an invented trend drawn
  // as a real chart. One scan is a point, not a line.
  const offenders = [];
  for (const f of SOURCES) {
    for (const line of strip(read(f)).split("\n")) {
      if (!/(MiniSparkline|MiniSegmentBar|MiniDonut|AreaChart)/.test(line)) continue;
      // a literal array of 3+ numbers passed as data
      if (/data=\{\[\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+/.test(line)) offenders.push(`${f}: ${line.trim().slice(0, 90)}`);
    }
  }
  assert.deepEqual(offenders, [], "a chart is drawn from invented data");
});
