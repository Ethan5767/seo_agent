/**
 * The three AEO tiles, and whether they are entitled to a verdict at all.
 *
 * B-094. Every tile on the AI Search Visibility screen was written as a binary:
 *
 *     {crawlerBlocked ? "Blocked" : "Allowed ✓"}
 *     {schemaBiz && schemaBiz.severity !== "ok" ? "Needs Fix" : "Valid Schema ✓"}
 *     {answerStruct && answerStruct.severity !== "ok" ? "Needs Headers" : "Detected ✓"}
 *
 * Each of those values comes from `aeoRows.find(...)`, which returns `undefined`
 * when the check did not run. So `undefined` fell through to the happy branch and
 * a signed-in operator who had never scanned anything was told their AI crawler
 * access was **Allowed ✓**, their schema **Valid ✓**, and their answer structure
 * **Detected ✓** - three green ticks over zero measurements.
 *
 * The matrix below them was worse: a hardcoded five-row fallback rendered
 * whenever there were no real rows, including the line "Verified in robots.txt"
 * for a robots.txt nobody had fetched.
 *
 * This is the rule the whole engine is built on, broken in the UI:
 * **a check that scanned nothing must never report a pass.** `forbidden_sweep`
 * and `audit_ssr` exit 4 for "cannot judge" rather than green-over-empty
 * (B-018, B-027); the same distinction has to survive to the screen, or the
 * engine's honesty stops at the API boundary.
 *
 * Three states, never two:
 *
 *     null       no row carries this verdict - nothing measured it
 *     "ok"       measured, and fine
 *     "problem"  measured, and needs work
 */

export type AeoVerdict = null | "ok" | "problem";

export type AeoRow = {
  code?: string;
  what?: string;
  why?: string;
  fix?: string;
  severity?: string;
  [k: string]: unknown;
};

export type AeoTile = {
  id: "crawlers" | "schema" | "answers";
  label: string;
  verdict: AeoVerdict;
  /** The headline. Never a tick when `verdict` is null. */
  value: string;
  /** One line under it: what it means, or what would produce a verdict. */
  note: string;
};

/** `warn`, `error` and anything unrecognised count as a problem; only `ok` passes. */
function judge(rows: AeoRow[]): AeoVerdict {
  if (rows.length === 0) return null;
  return rows.every((r) => r.severity === "ok") ? "ok" : "problem";
}

function match(rows: AeoRow[], needles: string[], codes: string[]): AeoRow[] {
  return rows.filter((r) => {
    const what = (r.what || "").toLowerCase();
    const code = (r.code || "").toLowerCase();
    return needles.some((n) => what.includes(n)) || codes.some((c) => code.includes(c));
  });
}

export function deriveAeoTiles(aeoRows: AeoRow[] | null | undefined): AeoTile[] {
  const rows = Array.isArray(aeoRows) ? aeoRows.filter((r) => r && typeof r === "object") : [];

  const crawler = judge(match(rows, ["crawler", "gptbot", "claudebot", "perplexity"], ["crawler", "robots"]));
  const schema = judge(match(rows, ["localbusiness", "json-ld", "schema"], ["schema_business", "schema"]));
  const answers = judge(match(rows, ["answer", "faq", "q&a"], ["answer", "faq"]));

  return [
    {
      id: "crawlers",
      label: "AI Crawler Access",
      verdict: crawler,
      value: crawler === null ? "Not measured" : crawler === "ok" ? "Allowed" : "Blocked",
      note:
        crawler === null
          ? "Run a scan to read robots.txt and see which AI crawlers are allowed."
          : crawler === "ok"
            ? "The citation crawlers are not disallowed in robots.txt."
            : "robots.txt disallows at least one AI citation crawler.",
    },
    {
      id: "schema",
      label: "LocalBusiness JSON-LD",
      verdict: schema,
      value: schema === null ? "Not measured" : schema === "ok" ? "Valid schema" : "Needs fix",
      note:
        schema === null
          ? "Run a scan to check the page for business structured data."
          : schema === "ok"
            ? "Business structured data is present and parses."
            : "Business structured data is missing or incomplete.",
    },
    {
      id: "answers",
      label: "Answer Structure",
      verdict: answers,
      value: answers === null ? "Not measured" : answers === "ok" ? "Detected" : "Needs headings",
      note:
        answers === null
          ? "Run a scan to check for question headings and answer-first copy."
          : answers === "ok"
            ? "Question headings with answer-first copy were found."
            : "No question headings the answer engines can lift from.",
    },
  ];
}

/** The colour for a verdict. `null` is grey - never the pass green. */
export function aeoVerdictColor(v: AeoVerdict): string {
  return v === null ? "#64748b" : v === "ok" ? "#047857" : "#d97706";
}

/**
 * Rows for the signals matrix, or null.
 *
 * Null is the whole point: the caller must render an empty state rather than a
 * table. The previous code substituted five invented rows here, three of them
 * marked PASS.
 */
export function aeoMatrixRows(aeoRows: AeoRow[] | null | undefined): AeoRow[] | null {
  const rows = Array.isArray(aeoRows) ? aeoRows.filter((r) => r && typeof r === "object") : [];
  return rows.length > 0 ? rows : null;
}
