/**
 * The live activity of a running scan, folded from the scanner's event stream.
 *
 * Events (NDJSON from wf-scan-web, via /api/scan):
 *   { tool, state: "running" }                       a tool started
 *   { tool, state: "progress", status, detail }      something real happened inside it
 *   { tool, state: "done", rows, status, cost }      it finished
 *
 * `detail` carries only facts the scanner has: a DataForSEO request started or
 * answered (ms, cost), a crawl's pages_crawled / pages_in_queue from the free
 * summary poll, a page the free crawl is fetching. Nothing here estimates a
 * percentage the scanner did not report.
 *
 * Pure, so the panel's behaviour is tested without a browser.
 */

export type ActivityLine = {
  at: number;
  text: string;
  step?: string;
  phase?: string;
  ms?: number;
  cost?: number;
};

export type ToolActivity = {
  name: string;
  state: "running" | "done";
  startedAt: number;
  finishedAt?: number;
  rows: any[];
  status: string;
  cost: number;
  lines: ActivityLine[];
  /** From DataForSEO's on_page/summary poll. */
  crawl?: { crawled: number; queue: number; max: number };
  /** From our own multi-page crawl. */
  page?: { n: number; total: number; url: string };
};

/** Keep the panel readable on a 25-page crawl with dozens of requests. */
export const MAX_LINES = 40;

export function applyScanEvent(tools: ToolActivity[], ev: any, now: number): ToolActivity[] {
  if (!ev || typeof ev.tool !== "string" || ev.state === "phase") return tools;
  const i = tools.findIndex((t) => t.name === ev.tool);
  const prev: ToolActivity =
    i >= 0
      ? tools[i]
      : { name: ev.tool, state: "running", startedAt: now, rows: [], status: "", cost: 0, lines: [] };
  let next: ToolActivity = prev;

  if (ev.state === "running") {
    next = { ...prev, state: "running", startedAt: i >= 0 ? prev.startedAt : now };
  } else if (ev.state === "progress") {
    const d = (ev.detail && typeof ev.detail === "object" ? ev.detail : {}) as Record<string, any>;
    const line: ActivityLine = {
      at: now,
      text: String(ev.status || ""),
      step: d.step,
      phase: d.phase,
      ms: typeof d.ms === "number" ? d.ms : undefined,
      cost: typeof d.cost === "number" ? d.cost : undefined,
    };
    next = { ...prev, lines: [...prev.lines, line].slice(-MAX_LINES) };
    if (typeof d.pages_crawled === "number") {
      next.crawl = {
        crawled: d.pages_crawled,
        queue: typeof d.pages_in_queue === "number" ? d.pages_in_queue : 0,
        max: typeof d.max_crawl_pages === "number" ? d.max_crawl_pages : d.pages_crawled,
      };
    }
    if (d.step === "page" && typeof d.n === "number") {
      next.page = { n: d.n, total: typeof d.total === "number" ? d.total : d.n, url: String(d.url || "") };
    }
    // The free crawl is not a catalog tool, so it never sends "done"; the
    // scanner marks its end with a "finished" progress event instead.
    if (d.phase === "finished") {
      next = { ...next, state: "done", finishedAt: now, status: line.text };
    }
  } else if (ev.state === "done") {
    next = {
      ...prev,
      state: "done",
      finishedAt: now,
      rows: Array.isArray(ev.rows) ? ev.rows : [],
      status: String(ev.status || ""),
      cost: typeof ev.cost === "number" ? ev.cost : 0,
    };
  } else {
    return tools;
  }

  const out = tools.slice();
  if (i >= 0) out[i] = next;
  else out.push(next);
  return out;
}

/** What a finished tool found, for the one-line summary. */
export function outcomeOf(t: ToolActivity): { kind: "ok" | "issues" | "not-run" | "running"; label: string } {
  if (t.state === "running") return { kind: "running", label: "Running" };
  const notRun = t.rows.find((r) => typeof r?.code === "string" && r.code.startsWith("unavailable."));
  if (notRun) return { kind: "not-run", label: `Did not run: ${notRun.why || t.status}` };
  const graded = t.rows.filter((r) => ["ok", "warn", "error"].includes(r?.severity));
  const issues = graded.filter((r) => r.severity !== "ok").length;
  if (!t.rows.length) return { kind: "ok", label: t.status || "No rows" };
  return issues
    ? { kind: "issues", label: `${graded.length} checks · ${issues} issue${issues === 1 ? "" : "s"}` }
    : { kind: "ok", label: graded.length ? `${graded.length} checks · all passed` : `${t.rows.length} rows` };
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
