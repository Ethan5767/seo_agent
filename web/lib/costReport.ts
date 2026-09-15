/**
 * A printable cost report, generated from scan history and handed to the
 * browser's own "Save as PDF". No PDF dependency: a clean, self-contained HTML
 * document opened in a new window, printed, and closed.
 *
 * Cost lives on the Dashboard, never on the individual tool pages, so this is
 * the one place a spend record is produced. Every figure traces to a real
 * `ScanRow.cost` — nothing is estimated or invented.
 */
import type { ScanRow } from "./db";
import { formatUsd } from "./budget";

export interface CostReportInput {
  projectName: string;
  scans: ScanRow[];
  /** ISO timestamp the report was generated. Passed in so the doc is testable. */
  generatedAt: string;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

function domainOf(url: string): string {
  return (url || "").replace(/^https?:\/\//i, "").replace(/\/.*$/, "").replace(/^www\./i, "") || url;
}

/** A vertical bar chart of per-scan spend as an inline SVG block, or "" when
 *  there is nothing to plot. Pure string building; prints without JS. */
function buildSpendChart(scans: ScanRow[]): string {
  if (scans.length === 0) return "";
  const W = 720, H = 180, pad = 28, gap = 6;
  const max = Math.max(...scans.map((s) => s.cost ?? 0), 0.0001);
  const bw = (W - pad * 2) / scans.length - gap;
  const bars = scans.map((s, i) => {
    const h = Math.max(2, ((s.cost ?? 0) / max) * (H - pad * 2));
    const x = pad + i * (bw + gap);
    const y = H - pad - h;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="#4f46e5" />`;
  }).join("");
  return `
  <figure style="margin:0 0 24px">
    <figcaption style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#475569;margin-bottom:6px">Spend per scan</figcaption>
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Spend per scan bar chart">
      <line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#cbd5e1" stroke-width="1" />
      ${bars}
    </svg>
  </figure>`;
}

/** The report as a full standalone HTML document. Pure — no window access. */
export function buildCostReportHtml({ projectName, scans, generatedAt }: CostReportInput): string {
  const priced = [...scans]
    .filter((s) => (s.cost ?? 0) > 0)
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  const total = priced.reduce((sum, s) => sum + (s.cost ?? 0), 0);
  const genDate = generatedAt.slice(0, 10);

  // A spend bar chart: the most recent scans, oldest-left, height by cost, so
  // the report opens on a picture of spend rather than a wall of figures.
  const chart = buildSpendChart(priced.slice(0, 20).reverse());

  const rows = priced.length
    ? priced.map((s) => `
        <tr>
          <td>${escapeHtml(s.created_at.slice(0, 10))}</td>
          <td>${escapeHtml(domainOf(s.url))}</td>
          <td class="num">${escapeHtml(formatUsd(s.cost ?? 0))}</td>
        </tr>`).join("")
    : `<tr><td colspan="3" class="empty">No paid scans recorded. Free checks cost $0.00 and are not listed.</td></tr>`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Cost Report — ${escapeHtml(projectName)}</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { font: 14px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         color: #0f172a; margin: 48px; }
  header { border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 24px; }
  h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }
  .meta { color: #475569; font-size: 13px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em;
       color: #475569; border-bottom: 1px solid #cbd5e1; padding: 8px 10px; }
  th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
  td { padding: 9px 10px; border-bottom: 1px solid #e2e8f0; }
  td.empty { color: #64748b; text-align: center; padding: 24px; }
  tfoot td { border-top: 2px solid #0f172a; border-bottom: 0; font-weight: 700; padding-top: 12px; }
  .count { color: #475569; font-weight: 400; }
  @media print { body { margin: 0.75in; } }
</style>
</head>
<body>
  <header>
    <h1>Cost Report — ${escapeHtml(projectName)}</h1>
    <div class="meta">Generated ${escapeHtml(genDate)} · ${priced.length} paid scan${priced.length === 1 ? "" : "s"} · ${escapeHtml(formatUsd(total))} total</div>
  </header>
  ${chart}
  <table>
    <thead>
      <tr><th>Date</th><th>Domain</th><th class="num">Cost</th></tr>
    </thead>
    <tbody>${rows}
    </tbody>
    <tfoot>
      <tr><td colspan="2">Total <span class="count">(${priced.length} scan${priced.length === 1 ? "" : "s"})</span></td><td class="num">${escapeHtml(formatUsd(total))}</td></tr>
    </tfoot>
  </table>
</body>
</html>`;
}

/**
 * Open the report in a new window and trigger the print dialog, from which the
 * operator picks "Save as PDF". Returns false if a popup blocker stopped it.
 */
export function downloadCostReport(projectName: string, scans: ScanRow[]): boolean {
  const html = buildCostReportHtml({ projectName, scans, generatedAt: new Date().toISOString() });
  const win = window.open("", "_blank", "noopener,noreferrer,width=800,height=1000");
  if (!win) return false;
  win.document.open();
  win.document.write(html);
  win.document.close();
  // Give the document a tick to lay out before the print dialog.
  win.onload = () => win.print();
  return true;
}
