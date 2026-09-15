"use client";

import React, { useMemo, useState } from "react";
import { StatStrip } from "@/components/dashboard/Panel";
import type { ReportRow } from "@/lib/priorities";
import { tallyRows, isSearchView, type ReportView } from "@/lib/reportViews";

/**
 * The table every report view renders through.
 *
 * The app had no sortable, filterable or paginated table anywhere - zero of
 * each across the whole codebase - which is most of why a screen full of real
 * findings still read as a slide rather than a tool. One component, adopted by
 * every view, fixes that once.
 *
 * It renders a real <table> with scoped headers, because this is tabular data
 * and a grid of divs is unreadable to a screen reader.
 */

const PAGE_SIZE = 25;

type SortDir = "asc" | "desc";

const SEVERITY_ORDER: Record<string, number> = { error: 0, warn: 1, info: 2, ok: 3 };

/**
 * How many pages a finding affects, from the row's own `pages` list.
 *
 * `merge_by_code` has attached the affected URLs to every multi-page row since
 * the free crawl shipped, and `onpage_audit` attaches them per DataForSEO flag.
 * Nothing rendered them. Every competitor puts this count on the row - it is
 * the difference between "canonical mismatch" and "canonical mismatch on 340
 * pages", and it is what makes a list of findings sortable by consequence
 * rather than by severity label alone.
 */
function affected(row: ReportRow): number {
  const pages = (row as { pages?: unknown }).pages;
  return Array.isArray(pages) ? pages.length : 0;
}

const SEVERITY_TONE: Record<string, { fg: string; bg: string; border: string; label: string }> = {
  error: { fg: "var(--bad)", bg: "var(--bad-tint)", border: "var(--bad-border)", label: "Error" },
  warn: { fg: "var(--warn)", bg: "var(--warn-tint)", border: "var(--warn-border)", label: "Warning" },
  info: { fg: "var(--info)", bg: "var(--info-tint)", border: "var(--info-border)", label: "Info" },
  ok: { fg: "var(--ok)", bg: "var(--ok-tint)", border: "var(--ok-border)", label: "Pass" },
};

/**
 * The count strip above every report view.
 *
 * It renders whether or not there are rows: an unscanned screen shows zeroes
 * rather than nothing, so the screen reads as measured-at-zero instead of
 * broken. The figures are counts of the rows themselves, never estimates.
 */
export function ReportStats({ rows, search }: { rows: ReportRow[]; search?: boolean }) {
  const tally = tallyRows(rows);

  // A search tool returns data, not verdicts, so it gets a single count instead
  // of the pass/fail buckets that only make sense for an audit.
  const cells: Array<{ label: string; value: number; tone?: string }> = search
    ? [{ label: "Results", value: tally.total }]
    : [
        { label: "Rows", value: tally.total },
        { label: "Errors", value: tally.error, tone: "var(--bad)" },
        { label: "Warnings", value: tally.warn, tone: "var(--warn)" },
        { label: "Passing", value: tally.ok, tone: "var(--ok)" },
      ];

  return (
    <div style={{ marginBottom: "var(--space-4)" }}>
      <StatStrip label="Row counts" stats={cells.map((c) => ({ label: c.label, value: c.value.toLocaleString(), tone: c.tone }))} />
    </div>
  );
}

export interface ReportTableProps {
  view: ReportView;
  rows: ReportRow[];
  /** Shown on the empty state so a blank screen has a way out. */
  onRunAudit?: () => void;
  /**
   * When the scan DID run and found nothing of this kind. Replaces "No data
   * here yet / Run a scan", which was false after a completed scan.
   */
  checkedEmpty?: { title: string; hint: string; action?: { label: string; onClick: () => void } };
}

export function ReportTable({ view, rows, onRunAudit, checkedEmpty }: ReportTableProps) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string>("severity");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(0);

  // A search tool returns data, so it drops the audit "Status / Pass" column and
  // reads as a plain data table — the way the category presents a lookup.
  const search = isSearchView(view);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) =>
      [r.what, r.detail, r.why, r.fix].some((v) => (v || "").toLowerCase().includes(q)),
    );
  }, [rows, query]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      let cmp: number;
      if (sortKey === "severity") {
        cmp = (SEVERITY_ORDER[a.severity || "info"] ?? 9) - (SEVERITY_ORDER[b.severity || "info"] ?? 9);
      } else if (sortKey === "affected") {
        // Sorting by consequence rather than by severity label: a warning on
        // 340 pages usually outranks an error on one.
        cmp = affected(a) - affected(b);
      } else {
        const av = String(a[sortKey as keyof ReportRow] ?? "");
        const bv = String(b[sortKey as keyof ReportRow] ?? "");
        // Figures sort as figures; "12" must not come before "9".
        const an = Number(av.replace(/[^0-9.-]/g, ""));
        const bn = Number(bv.replace(/[^0-9.-]/g, ""));
        cmp =
          av !== "" && bv !== "" && Number.isFinite(an) && Number.isFinite(bn) && /\d/.test(av) && /\d/.test(bv)
            ? an - bn
            : av.localeCompare(bv);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = sorted.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  // Shown only when some row actually carries pages: a single-page scan would
  // otherwise get a column of em dashes, which is worse than no column.
  const anyAffected = useMemo(() => rows.some((r) => affected(r) > 0), [rows]);

  function toggleSort(key: string) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(0);
  }

  if (rows.length === 0) {
    // An empty screen is where a product feels broken, so this says three
    // things plainly: that nothing is wrong, what this screen will hold, and
    // the one action that fills it. The ghost rows show the shape the data
    // will take, so the screen reads as waiting rather than blank.
    return (
      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          background: "var(--surface)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "var(--space-5) var(--space-4)",
            textAlign: "center",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
            {checkedEmpty ? checkedEmpty.title : "No data here yet"}
          </div>
          <p
            style={{
              fontSize: 13,
              color: "var(--ink-muted)",
              margin: "var(--space-2) auto 0",
              maxWidth: "54ch",
              lineHeight: 1.55,
            }}
          >
            {view.blurb}
          </p>
          <p
            style={{
              fontSize: 13,
              color: "var(--ink-muted)",
              margin: "var(--space-2) auto 0",
              maxWidth: "54ch",
            }}
          >
            {checkedEmpty ? checkedEmpty.hint : view.emptyHint}
          </p>
          {checkedEmpty?.action && (
            <button
              type="button"
              onClick={checkedEmpty.action.onClick}
              style={{
                marginTop: "var(--space-3)", background: "var(--accent)", color: "var(--color-white)", border: 0,
                borderRadius: 6, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
              }}
            >
              {checkedEmpty.action.label}
            </button>
          )}
          {onRunAudit && !checkedEmpty && (
            <button
              type="button"
              onClick={onRunAudit}
              style={{
                marginTop: "var(--space-4)",
                padding: "var(--space-2) var(--space-4)",
                minHeight: 34,
                borderRadius: "var(--radius-sm)",
                border: 0,
                background: "var(--accent)",
                color: "var(--color-white)",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Run an audit
            </button>
          )}
        </div>

        {/* The shape the table will take, so the screen reads as waiting. */}
        <div aria-hidden="true" style={{ padding: "var(--space-3)", opacity: 0.5 }}>
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              style={{
                display: "flex",
                gap: "var(--space-3)",
                padding: "var(--space-2) var(--space-1)",
                borderBottom: i < 2 ? "1px solid var(--border)" : 0,
              }}
            >
              <div style={{ width: "5rem", height: 10, borderRadius: 3, background: "var(--surface-3)" }} />
              <div style={{ flex: "2 1 0", height: 10, borderRadius: 3, background: "var(--surface-3)" }} />
              <div style={{ flex: "1 1 0", height: 10, borderRadius: 3, background: "var(--surface-3)" }} />
              <div style={{ flex: "1 1 0", height: 10, borderRadius: 3, background: "var(--surface-3)" }} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: "var(--space-3)",
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: "var(--space-3)",
        }}
      >
        <label htmlFor={`filter-${view.id}`} style={{ position: "absolute", left: -9999 }}>
          Filter {view.label}
        </label>
        <input
          id={`filter-${view.id}`}
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          placeholder={`Filter ${rows.length} rows`}
          style={{
            flex: "1 1 16rem",
            minWidth: 0,
            padding: "0 var(--space-3)",
            minHeight: 36,
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border-strong)",
            background: "var(--surface)",
            color: "var(--ink-body)",
            fontSize: "var(--text-sm)",
          }}
        />
        <span style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
          {filtered.length === rows.length
            ? `${rows.length} rows`
            : `${filtered.length} of ${rows.length} rows`}
        </span>
      </div>

      <div className="report-table">
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-sm)", minWidth: "40rem" }}>
          <caption style={{ position: "absolute", left: -9999 }}>{view.blurb}</caption>
          <thead>
            <tr>
              {!search && (
                <th
                  scope="col"
                  style={{ ...headStyle, width: "6.5rem" }}
                  aria-sort={sortKey === "severity" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <SortButton
                    label="Status"
                    active={sortKey === "severity"}
                    dir={sortDir}
                    onClick={() => toggleSort("severity")}
                  />
                </th>
              )}
              {anyAffected && (
                <th
                  scope="col"
                  style={{ ...headStyle, width: "6rem", textAlign: "right" }}
                  aria-sort={sortKey === "affected" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <SortButton
                    label="Pages"
                    active={sortKey === "affected"}
                    dir={sortDir}
                    onClick={() => toggleSort("affected")}
                  />
                </th>
              )}
              {view.columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  style={{
                    ...headStyle,
                    width: col.width,
                    textAlign: col.numeric ? "right" : "left",
                  }}
                  aria-sort={sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <SortButton
                    label={col.label}
                    active={sortKey === col.key}
                    dir={sortDir}
                    align={col.numeric ? "right" : "left"}
                    onClick={() => toggleSort(col.key)}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => {
              const tone = SEVERITY_TONE[row.severity || "info"] ?? SEVERITY_TONE.info;
              return (
                <tr key={`${row.code}-${row.what}-${i}`} className="report-table__row">
                  {!search && (
                    <td style={cellStyle}>
                      <span
                        style={{
                          display: "inline-block",
                          fontSize: "var(--text-xs)",
                          fontWeight: 600,
                          padding: "2px 10px",
                          borderRadius: "var(--radius-full)",
                          color: tone.fg,
                          background: tone.bg,
                          border: `1px solid ${tone.border}`,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {tone.label}
                      </span>
                    </td>
                  )}
                  {anyAffected && (
                    <td style={{ ...cellStyle, textAlign: "right", fontVariantNumeric: "tabular-nums",
                                 color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
                      {affected(row) > 0 ? (
                        <span title={((row as { pages?: string[] }).pages || []).slice(0, 10).join("\n")}>
                          {affected(row).toLocaleString()}
                        </span>
                      ) : "\u2014"}
                    </td>
                  )}
                  {view.columns.map((col) => (
                    <td
                      key={col.key}
                      style={{
                        ...cellStyle,
                        textAlign: col.numeric ? "right" : "left",
                        fontVariantNumeric: col.numeric ? "tabular-nums" : undefined,
                        color: col.key === "what" ? "var(--ink)" : "var(--ink-muted)",
                        fontWeight: col.key === "what" ? 500 : 400,
                      }}
                    >
                      {String(row[col.key as keyof ReportRow] ?? "") || "—"}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div
          style={{
            display: "flex",
            gap: "var(--space-2)",
            alignItems: "center",
            justifyContent: "flex-end",
            marginTop: "var(--space-3)",
          }}
        >
          <span style={{ fontSize: 12, color: "var(--ink-muted)", marginRight: "auto" }}>
            Page {safePage + 1} of {pageCount}
          </span>
          <PageButton label="Previous" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} />
          <PageButton
            label="Next"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage(safePage + 1)}
          />
        </div>
      )}
    </div>
  );
}

const headStyle: React.CSSProperties = {
  textAlign: "left",
  padding: 0,
  background: "var(--surface-2)",
  borderBottom: "1px solid var(--border)",
  position: "sticky",
  top: 0,
};

const cellStyle: React.CSSProperties = {
  padding: "var(--space-3) var(--space-4)",
  borderBottom: "1px solid var(--border)",
  verticalAlign: "top",
  lineHeight: 1.45,
};

function SortButton({
  label,
  active,
  dir,
  align = "left",
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  align?: "left" | "right";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: "100%",
        display: "flex",
        justifyContent: align === "right" ? "flex-end" : "flex-start",
        alignItems: "center",
        gap: 4,
        padding: "var(--space-3) var(--space-4)",
        border: 0,
        background: "transparent",
        cursor: "pointer",
        font: "inherit",
        fontSize: "var(--text-xs)",
        fontWeight: 600,
        color: active ? "var(--ink)" : "var(--ink-muted)",
      }}
    >
      {label}
      <span aria-hidden="true" style={{ opacity: active ? 1 : 0.35 }}>
        {active && dir === "desc" ? "▾" : "▴"}
      </span>
    </button>
  );
}

function PageButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "var(--space-2) var(--space-3)",
        minHeight: 34,
        borderRadius: "var(--radius-sm)",
        border: "1px solid var(--border-strong)",
        background: "var(--surface)",
        color: disabled ? "var(--ink-muted)" : "var(--ink-body)",
        fontSize: 13,
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {label}
    </button>
  );
}
