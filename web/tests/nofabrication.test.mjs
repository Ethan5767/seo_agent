import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RAW = readFileSync(path.join(webDir, "app", "ReaiDashboard.tsx"), "utf8");

/**
 * Comments stripped before matching. The file documents the constants it used
 * to print - that history is the point of those comments, and a guard that
 * cannot tell "the literal is in the code" from "the literal is named in a note
 * explaining its removal" would push people to delete the explanation. The
 * guard is about what renders, so it reads only what renders.
 */
const DASH = RAW
  .replace(/\/\*[\s\S]*?\*\//g, " ")   // block comments, JSX {/* */} included
  .replace(/^\s*\/\/.*$/gm, " ");       // whole-line // comments

/**
 * The Overview screen rendered invented figures on an empty account.
 *
 * `resolveProjectData` had already been cleaned - `authorityScore = 0`,
 * `refDelta = ""`, each with a comment saying why - and the JSX around those
 * honest values printed constants over the top of them. Headless render of
 * /dashboard with no client selected showed "+14.2%", "$2,439/mo est. value",
 * "Top 35%", "Grade B+" at 0% health, "609 pages checked", "85%", "~342 brand
 * mentions", and a "0 Ranked Keywords" headline directly above "7 AT RANK #1".
 *
 * These are string checks on purpose: the defect was literals in JSX, so a
 * literal is what has to stay out.
 */
const BANNED = [
  ["+14.2%", "a constant growth badge, shown to every client in success-green"],
  ["$2,439/mo", "a constant traffic valuation; nothing in the scan prices traffic"],
  ["Top 35%", "a constant authority percentile"],
  ["Grade B+", "a frozen letter grade - the badge colour moved with the score, the letter did not"],
  ["609 pages checked", "a constant page count that outlived every crawl cap"],
  ["609 URLs checked", "the same constant, on the technical card"],
  ["~342 brand mentions", "a constant mention count"],
  ['title="OpenAI (96%)"', "a per-engine score invented in a bar tooltip"],
  ['title="Gemini (92%)"', "a per-engine score invented in a bar tooltip"],
  ['title="Perplexity (98%)"', "a per-engine score invented in a bar tooltip"],
  ['title="Claude (88%)"', "a per-engine score invented in a bar tooltip"],
  ["All Tools (156)", "a hardcoded catalog count; the catalog reports its own"],
  ["7 AT RANK #1", "a constant, rendered beside a headline reading '0 Ranked Keywords'"],
  ["Visibility (74%)", "a tab label carrying its own fixture's endpoint"],
];

/** Chart series that had no source: a traffic ramp, a keyword climb, a visibility curve. */
const BANNED_SERIES = [
  [/\{ m: "Oct", v: 2\.8 \}/, "the six-month traffic fixture"],
  [/\[84, 92, 105, 114, 122/, "the keyword-climb fixture"],
  [/\[48, 54, 59, 64, 70, 74\]/, "the visibility-curve fixture"],
];

test("no metric has a floor that fires when nothing was measured", () => {
  // `Math.max(120, ...)` handed every unscanned client 120 organic visits a
  // month. Zero measured keywords must model zero traffic.
  assert.ok(!/Math\.max\(120,/.test(DASH), "the 120-visit floor is back");
  for (const [needle, why] of [
    ['pagesPerVisit: "3.4"', "a constant pages-per-visit"],
    ['avgDuration: "3m 48s"', "a constant session duration"],
    ['bounceRate: "41.2%"', "a constant bounce rate"],
  ]) {
    // Session metrics: neither the scan nor Search Console observes a session.
    assert.ok(!DASH.includes(needle), `${why} is back`);
  }
});

test("the health score is computed once, in the scanner, and never re-derived", () => {
  /*
   * One scan had three health numbers: the scanner's penalty model, a pass rate
   * recomputed in ReaiDashboard, and a third in AuditHeroBar with different
   * weights and a floor of 20. They disagreed, and the falsy-`||` fallback meant
   * a genuine score of 0 was replaced by 20. Any arithmetic over error/warn
   * counts in the web tier is a fourth formula waiting to happen.
   */
  for (const file of ["app/ReaiDashboard.tsx", "components/dashboard/AuditHeroBar.tsx"]) {
    const raw = readFileSync(path.join(webDir, file), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/^\s*\/\/.*$/gm, " ");
    assert.ok(
      !/100\s*-\s*\(?\s*\w*[eE]rror\w*\s*\*/.test(raw),
      `${file} computes a health score from error counts; the scanner owns that`
    );
    assert.ok(
      !/Math\.max\(\s*\d+\s*,\s*100\s*-/.test(raw),
      `${file} carries a clamped penalty score; that model saturates and is gone`
    );
  }
});

test("an unmeasured health score renders as unmeasured, never as zero", () => {
  // Comments stripped: the file explains the `||` bug it used to have, and a
  // guard that cannot tell code from the note explaining the fix would push
  // people to delete the explanation.
  const raw = readFileSync(path.join(webDir, "app/ReaiDashboard.tsx"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^\s*\/\/.*$/gm, " ");
  // `?? null`, never `|| 0`: a real score of 0 is falsy, and a scan that graded
  // nothing has no health to report.
  assert.ok(
    !/report\?\.score\s*\|\|/.test(raw),
    "report.score is being coerced with ||, which discards a genuine 0"
  );
  assert.ok(
    /dynamicHealth[\s\S]{0,200}report\?\.score \?\?/.test(raw),
    "dynamicHealth must read the scanner's score with ??"
  );
});

test("the traffic chart plots measurements or nothing", () => {
  for (const [re, why] of BANNED_SERIES) {
    assert.ok(!re.test(DASH), `${why} is back - the chart must render real trend data or no series`);
  }
});

test("the Overview screen states no figure it did not measure", () => {
  for (const [needle, why] of BANNED) {
    assert.ok(!DASH.includes(needle), `'${needle}' is back in ReaiDashboard.tsx - ${why}`);
  }
});

test("no client's real competitors are handed to another client", () => {
  // A `.kh` domain inherited four named Cambodian hospitals - real businesses,
  // shown to whoever was signed in as THEIR rivals - and every other domain got
  // competitors invented from its own name, which may belong to someone.
  for (const needle of [
    "royalphnompenhhospital.com",
    "rafflesmedical.com.kh",
    "intercarehospital.com",
    "-leader.com",
    "industry-network.com",
  ]) {
    assert.ok(
      !DASH.includes(`"${needle}"`) && !DASH.includes(`\`\${dClean.split(".")[0]}${needle}\``),
      `'${needle}' is back as a competitor fallback`
    );
  }
});

test("a configured keyword is never given a rank, volume or intent", () => {
  // client.keywords are TARGETS. This filled the rankings table from them with
  // position 3/7/14 and volume 600/520/440 when no scan had run.
  assert.ok(
    !/position:\s*i === 0 \? 3 : i === 1 \? 7 : 14/.test(DASH),
    "the invented rank ladder is back"
  );
  assert.ok(
    !/volume:\s*`\$\{\(600 - i \* 80\)/.test(DASH),
    "the invented volume ladder is back"
  );
});

test("no metric is conditioned on a substring of the client's domain", () => {
  // B-043's shape: the product decided a healthcare client had ~342 brand
  // mentions because its URL contained "hospital".
  assert.ok(
    !/currentDomain\.includes\("hospital"\)\s*\?/.test(DASH),
    "a metric is being chosen from the domain name again"
  );
});

// ── metric fallbacks (B-073) ─────────────────────────────────────────────────

test("no metric falls back to an invented number", () => {
  // Three live cases found by a user who was not even signed in:
  //   overallScore || 80                        -> "80/100 · Good Site Health"
  //   posTop10 = ...length || 5                 -> a 5-bucket chart under "0 Ranked Keywords"
  //   insights?.breakdown?.calls?.count || 142  -> the accessor was DEAD, so 142 always rendered
  //
  // Divide-by-zero guards on chart scales (`|| 1`, `|| 100`) are fine; a metric
  // a client reads as a measurement is not.
  const files = [
    "app/ReaiDashboard.tsx",
    "components/dashboard/AuditHeroBar.tsx",
    "components/dashboard/LocalBusinessManager.tsx",
    "components/dashboard/MeasureScreen.tsx",
    "components/dashboard/Overview.tsx",
  ];
  const METRIC = /\b(score|count|calls|clicks|impressions|visits|keywords|bookings|reviews|rating|traffic|domains|backlinks)\w*\s*(?:\?\.\w+)*\s*\|\|\s*(\d+)/gi;

  const found = [];
  for (const f of files) {
    let src;
    try { src = readFileSync(new URL(`../${f}`, import.meta.url), "utf8"); } catch { continue; }
    const code = src.replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    for (const m of code.matchAll(METRIC)) {
      if (Number(m[2]) === 0 || Number(m[2]) === 1) continue;   // 0 and 1 are guards, not claims
      found.push(`${f}: ${m[0].trim()}`);
    }
  }
  assert.deepEqual(found, [],
    `a metric falls back to a made-up number:\n  ${found.join("\n  ")}`);
});

test("the position distribution is counted, never modelled from a percentage", () => {
  const src = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const block = src.slice(src.indexOf("5. Position distribution"), src.indexOf("posTotalSample ="));
  assert.ok(!/\*\s*0\.\d+/.test(block),
    "buckets must be counted from real positions, not derived as a share of the total");
  assert.ok(/hasRankings/.test(src), "there must be an explicit no-rankings state");
});
