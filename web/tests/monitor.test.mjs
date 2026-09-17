import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  computeDateRange,
  widgetDateRange,
  formatMetricValue,
  formatDelta,
  WIDGET_TEMPLATES,
  DEFAULT_MONITOR_WIDGETS,
} from "../lib/monitor/types.ts";

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

/* ── Date range calculation & latency offset ──────────────────────────────── */

test("computeDateRange offsets end date by 2 days for GSC latency", () => {
  const range = computeDateRange("28d", "none");
  const now = new Date();
  const twoDaysAgo = new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString().split("T")[0];

  assert.equal(range.endDate, twoDaysAgo);

  const start = new Date(range.startDate);
  const end = new Date(range.endDate);
  const diffDays = Math.round((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1;
  assert.equal(diffDays, 28);
});

test("computeDateRange calculates 7d and 90d presets accurately", () => {
  const range7 = computeDateRange("7d", "none");
  const start7 = new Date(range7.startDate);
  const end7 = new Date(range7.endDate);
  assert.equal(Math.round((end7.getTime() - start7.getTime()) / (24 * 60 * 60 * 1000)) + 1, 7);

  const range90 = computeDateRange("90d", "none");
  const start90 = new Date(range90.startDate);
  const end90 = new Date(range90.endDate);
  assert.equal(Math.round((end90.getTime() - start90.getTime()) / (24 * 60 * 60 * 1000)) + 1, 90);
});

test("computeDateRange calculates previous_period comparison interval", () => {
  const range = computeDateRange("28d", "previous_period");
  assert.ok(range.compareStartDate);
  assert.ok(range.compareEndDate);

  const primaryStart = new Date(range.startDate);
  const compEnd = new Date(range.compareEndDate);
  // Comparison period ends exactly 1 day before primary starts
  assert.equal(
    Math.round((primaryStart.getTime() - compEnd.getTime()) / (24 * 60 * 60 * 1000)),
    1,
  );
});

test("computeDateRange calculates previous_year comparison interval", () => {
  const range = computeDateRange("28d", "previous_year");
  const startYear = parseInt(range.startDate.split("-")[0], 10);
  const compStartYear = parseInt(range.compareStartDate.split("-")[0], 10);
  assert.equal(compStartYear, startYear - 1);
});

test("a widget preset overrides the global date range for both data sources", () => {
  const filters = {
    datePreset: "90d", startDate: "2025-01-01", endDate: "2025-03-31", compareMode: "none",
    deviceFilter: "all", countryFilter: "all", pageFilter: "", searchAppearanceFilter: "all", channelFilter: "all",
  };
  const range = widgetDateRange({ id: "w", title: "Seven days", source: "gsc", chartType: "line", metric: "clicks", width: "half", dateRangeOverride: { preset: "7d" } }, filters);
  const days = Math.round((new Date(range.endDate) - new Date(range.startDate)) / (24 * 60 * 60 * 1000)) + 1;
  assert.equal(days, 7);
  assert.notEqual(range.startDate, filters.startDate);
});

test("a widget exact range overrides the global date range", () => {
  const filters = {
    datePreset: "28d", startDate: "2025-01-01", endDate: "2025-01-28", compareMode: "none",
    deviceFilter: "all", countryFilter: "all", pageFilter: "", searchAppearanceFilter: "all", channelFilter: "all",
  };
  const range = widgetDateRange({ id: "w", title: "Fixed", source: "ga4", chartType: "stat", metric: "sessions", width: "third", dateRangeOverride: { startDate: "2024-05-01", endDate: "2024-05-15" } }, filters);
  assert.equal(range.startDate, "2024-05-01");
  assert.equal(range.endDate, "2024-05-15");
});

/* ── Metric formatting & rank delta inversion ─────────────────────────────── */

test("formatMetricValue formats percentages and positions correctly", () => {
  assert.equal(formatMetricValue(5.421, "ctr"), "5.4%");
  assert.equal(formatMetricValue(62.8, "engagementRate"), "62.8%");
  assert.equal(formatMetricValue(3.4, "position"), "#3.4");
  assert.equal(formatMetricValue(125, "averageSessionDuration"), "2m 05s");
  assert.equal(formatMetricValue(14500, "clicks"), "14,500");
});

test("formatDelta inverts position deltas: lower rank number is positive", () => {
  // Position moved from #12 to #7 (delta is -5, which is an improvement)
  const improved = formatDelta(7, 12, "position");
  assert.equal(improved.positive, true);
  assert.equal(improved.delta, -5);
  assert.equal(improved.label, "-5.0 ranks");

  // Position moved from #4 to #9 (delta is +5, which is worse)
  const degraded = formatDelta(9, 4, "position");
  assert.equal(degraded.positive, false);
  assert.equal(degraded.delta, 5);
  assert.equal(degraded.label, "+5.0 ranks");
});

test("formatDelta handles standard metrics normally", () => {
  // Clicks moved from 100 to 120 (+20%)
  const clickIncrease = formatDelta(120, 100, "clicks");
  assert.equal(clickIncrease.positive, true);
  assert.equal(clickIncrease.label, "+20%");

  // Clicks dropped from 100 to 80 (-20%)
  const clickDrop = formatDelta(80, 100, "clicks");
  assert.equal(clickDrop.positive, false);
  assert.equal(clickDrop.label, "-20%");
});

/* ── Widget template library & default layout ────────────────────────────── */

test("WIDGET_TEMPLATES provides at least 18 curated templates across 4 categories", () => {
  assert.ok(WIDGET_TEMPLATES.length >= 18, `Expected >= 18 templates, got ${WIDGET_TEMPLATES.length}`);

  const categories = new Set(WIDGET_TEMPLATES.map((t) => t.category));
  assert.ok(categories.has("KPI Cards"));
  assert.ok(categories.has("GSC Search"));
  assert.ok(categories.has("GA4 Traffic"));
  assert.ok(categories.has("Conversions"));

  for (const t of WIDGET_TEMPLATES) {
    assert.ok(t.id, "template must have id");
    assert.ok(t.title, "template must have title");
    assert.ok(t.source === "gsc" || t.source === "ga4", "source must be gsc or ga4");
    assert.ok(
      ["stat", "line", "bar", "donut", "funnel", "table"].includes(t.chartType),
      `invalid chartType: ${t.chartType}`,
    );
  }
});

test("DEFAULT_MONITOR_WIDGETS provides a sensible starting workspace", () => {
  assert.ok(DEFAULT_MONITOR_WIDGETS.length >= 8);
  const kpiCount = DEFAULT_MONITOR_WIDGETS.filter((w) => w.chartType === "stat").length;
  assert.ok(kpiCount >= 4, "Default layout should include at least 4 top KPI stat cards");
});

/* ── Google isolation & authedFetch validation ────────────────────────────── */

test("GA4 routes establish session ownership and never read token cookies directly", () => {
  const propsSrc = read("app/api/ga4/properties/route.ts");
  const querySrc = read("app/api/ga4/query/route.ts");

  for (const [name, src] of [["properties", propsSrc], ["query", querySrc]]) {
    assert.match(src, /googleSession\(/, `${name} must establish caller ownership via googleSession`);
    assert.ok(!src.includes("gsc_access_token"), `${name} must not read token cookies directly`);
    assert.ok(!src.includes("gsc_refresh_token"), `${name} must not read refresh cookies directly`);
  }
});

test("Monitor client fetcher uses authedFetch and no raw fetches", () => {
  const fetcherSrc = read("lib/monitor/fetcher.ts");
  assert.match(fetcherSrc, /authedFetch\(/, "fetcher.ts must use authedFetch");
  assert.ok(!/\bfetch\(/.test(fetcherSrc), "fetcher.ts must not use bare fetch()");
});

test("GA4 funnels never manufacture stages when Google reports zero or nothing", () => {
  const screen = read("components/dashboard/monitor/MonitorScreen.tsx");
  assert.ok(!/totalSessions\s*=\s*res\.totals\["sessions"\]\s*\|\|\s*100/.test(screen));
  assert.ok(!/engagedSessions.*0\.62|conv.*0\.07/.test(screen));
  assert.match(screen, /GA4-reported sessions/);
  assert.match(screen, /GA4-reported conversion events/);
});
