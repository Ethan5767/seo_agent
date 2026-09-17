/**
 * Monitor Stage (GSC & GA4 Analytics) Data Layer and Layout Definitions.
 *
 * Provides typed filter models, customizable widget configurations, template libraries,
 * sensible defaults, and deterministic formatting helpers for verified Google analytics.
 */

export type DataSource = "gsc" | "ga4";
export type ChartType = "line" | "bar" | "table" | "stat" | "donut" | "funnel";
export type WidgetWidth = "full" | "half" | "third";

export type DatePreset = "7d" | "28d" | "90d" | "last_month" | "custom";
export type CompareMode = "none" | "previous_period" | "previous_year";

export interface MonitorGlobalFilters {
  datePreset: DatePreset;
  startDate: string;
  endDate: string;
  compareMode: CompareMode;
  compareStartDate?: string;
  compareEndDate?: string;
  deviceFilter: "all" | "desktop" | "mobile" | "tablet";
  countryFilter: string; // "all" or country code / name
  pageFilter: string; // URL substring
  searchAppearanceFilter: string; // "all" or rich result type
  channelFilter: string; // "all" or channel name
}

export interface DateRangeResult {
  startDate: string;
  endDate: string;
  compareStartDate?: string;
  compareEndDate?: string;
  label: string;
  compareLabel?: string;
}

/**
 * Compute ISO date strings for presets and comparison modes.
 * GSC has ~2-3 days data processing latency; GA4 has ~1 day latency.
 */
export function computeDateRange(
  preset: DatePreset,
  compareMode: CompareMode,
  customStart?: string,
  customEnd?: string,
): DateRangeResult {
  const now = new Date();
  const DAY_MS = 24 * 60 * 60 * 1000;
  // End date is 2 days ago to respect Search Console latency ceiling
  const endBase = new Date(now.getTime() - 2 * DAY_MS);

  let start: Date;
  let end: Date = endBase;
  let label = "Last 28 Days";

  if (preset === "7d") {
    start = new Date(endBase.getTime() - 6 * DAY_MS);
    label = "Last 7 Days";
  } else if (preset === "90d") {
    start = new Date(endBase.getTime() - 89 * DAY_MS);
    label = "Last 90 Days";
  } else if (preset === "last_month") {
    const y = now.getFullYear();
    const m = now.getMonth();
    start = new Date(y, m - 1, 1);
    end = new Date(y, m, 0);
    label = "Last Month";
  } else if (preset === "custom" && customStart && customEnd) {
    start = new Date(customStart);
    end = new Date(customEnd);
    label = `${customStart} - ${customEnd}`;
  } else {
    // Default 28d
    start = new Date(endBase.getTime() - 27 * DAY_MS);
    label = "Last 28 Days";
  }

  const toIso = (d: Date) => d.toISOString().split("T")[0];
  const startDateStr = toIso(start);
  const endDateStr = toIso(end);

  if (compareMode === "none") {
    return { startDate: startDateStr, endDate: endDateStr, label };
  }

  const durationMs = end.getTime() - start.getTime() + DAY_MS;

  if (compareMode === "previous_year") {
    const compStart = new Date(start);
    compStart.setFullYear(compStart.getFullYear() - 1);
    const compEnd = new Date(end);
    compEnd.setFullYear(compEnd.getFullYear() - 1);
    return {
      startDate: startDateStr,
      endDate: endDateStr,
      compareStartDate: toIso(compStart),
      compareEndDate: toIso(compEnd),
      label,
      compareLabel: "Same period last year",
    };
  }

  // previous_period
  const compEnd = new Date(start.getTime() - DAY_MS);
  const compStart = new Date(compEnd.getTime() - durationMs + DAY_MS);

  return {
    startDate: startDateStr,
    endDate: endDateStr,
    compareStartDate: toIso(compStart),
    compareEndDate: toIso(compEnd),
    label,
    compareLabel: "Previous period",
  };
}

export interface MonitorWidget {
  id: string;
  title: string;
  description?: string;
  source: DataSource;
  chartType: ChartType;
  metric: string;
  secondaryMetric?: string;
  dimension?: string;
  width: WidgetWidth;
  dateRangeOverride?: {
    preset?: DatePreset;
    startDate?: string;
    endDate?: string;
  };
}

/** Resolve one widget's requested period without mutating the global bar.

 * A widget may carry an exact custom range or a named preset.  Keeping this at
 * the shared model boundary prevents the GSC and GA4 fetchers from drifting.
 */
export function widgetDateRange(widget: MonitorWidget, filters: MonitorGlobalFilters): DateRangeResult {
  const override = widget.dateRangeOverride;
  if (override?.preset) {
    return computeDateRange(override.preset, filters.compareMode, override.startDate, override.endDate);
  }
  if (override?.startDate && override?.endDate) {
    return computeDateRange("custom", filters.compareMode, override.startDate, override.endDate);
  }
  return {
    startDate: filters.startDate,
    endDate: filters.endDate,
    compareStartDate: filters.compareStartDate,
    compareEndDate: filters.compareEndDate,
    label: "Global filter bar",
  };
}

export interface WidgetTemplate {
  id: string;
  title: string;
  description: string;
  source: DataSource;
  chartType: ChartType;
  metric: string;
  secondaryMetric?: string;
  dimension?: string;
  width: WidgetWidth;
  category: "GSC Search" | "GA4 Traffic" | "Conversions" | "KPI Cards";
}

export const WIDGET_TEMPLATES: WidgetTemplate[] = [
  // KPI Cards
  {
    id: "gsc-stat-clicks",
    title: "Organic Clicks",
    description: "Total verified clicks from Google Search Console",
    source: "gsc",
    chartType: "stat",
    metric: "clicks",
    width: "third",
    category: "KPI Cards",
  },
  {
    id: "gsc-stat-impressions",
    title: "Search Impressions",
    description: "Total impressions across Google Search results",
    source: "gsc",
    chartType: "stat",
    metric: "impressions",
    width: "third",
    category: "KPI Cards",
  },
  {
    id: "gsc-stat-ctr",
    title: "Average CTR",
    description: "Click-through rate (Clicks ÷ Impressions)",
    source: "gsc",
    chartType: "stat",
    metric: "ctr",
    width: "third",
    category: "KPI Cards",
  },
  {
    id: "gsc-stat-position",
    title: "Average Position",
    description: "Average ranking position on Google SERP",
    source: "gsc",
    chartType: "stat",
    metric: "position",
    width: "third",
    category: "KPI Cards",
  },
  {
    id: "ga4-stat-sessions",
    title: "GA4 Sessions",
    description: "Total web sessions recorded in Google Analytics",
    source: "ga4",
    chartType: "stat",
    metric: "sessions",
    width: "third",
    category: "KPI Cards",
  },
  {
    id: "ga4-stat-engagement",
    title: "Engagement Rate",
    description: "Percentage of engaged sessions in GA4",
    source: "ga4",
    chartType: "stat",
    metric: "engagementRate",
    width: "third",
    category: "KPI Cards",
  },
  {
    id: "ga4-stat-conversions",
    title: "Total Conversions",
    description: "Goal and conversion events completed in GA4",
    source: "ga4",
    chartType: "stat",
    metric: "conversions",
    width: "third",
    category: "KPI Cards",
  },

  // GSC Widgets
  {
    id: "gsc-clicks-trend",
    title: "Clicks & Impressions Over Time",
    description: "Daily search traffic trend with comparison overlay",
    source: "gsc",
    chartType: "line",
    metric: "clicks",
    secondaryMetric: "impressions",
    dimension: "date",
    width: "full",
    category: "GSC Search",
  },
  {
    id: "gsc-queries-table",
    title: "Top Search Queries",
    description: "Exact queries bringing organic traffic with CTR & rank",
    source: "gsc",
    chartType: "table",
    metric: "clicks",
    dimension: "query",
    width: "half",
    category: "GSC Search",
  },
  {
    id: "gsc-pages-table",
    title: "Top Landing Pages",
    description: "Highest ranking pages by organic clicks and impressions",
    source: "gsc",
    chartType: "table",
    metric: "clicks",
    dimension: "page",
    width: "half",
    category: "GSC Search",
  },
  {
    id: "gsc-device-donut",
    title: "Device Breakdown",
    description: "Share of clicks by mobile, desktop, and tablet",
    source: "gsc",
    chartType: "donut",
    metric: "clicks",
    dimension: "device",
    width: "third",
    category: "GSC Search",
  },
  {
    id: "gsc-country-bar",
    title: "Traffic by Country",
    description: "Top geographic markets for search audience",
    source: "gsc",
    chartType: "bar",
    metric: "clicks",
    dimension: "country",
    width: "half",
    category: "GSC Search",
  },
  {
    id: "gsc-search-appearance",
    title: "Search Appearance & Rich Results",
    description: "Rich snippet, video, and schema performance in SERP",
    source: "gsc",
    chartType: "bar",
    metric: "clicks",
    dimension: "searchAppearance",
    width: "half",
    category: "GSC Search",
  },
  {
    id: "gsc-position-trend",
    title: "Average Position Trend",
    description: "Daily average ranking position over time",
    source: "gsc",
    chartType: "line",
    metric: "position",
    dimension: "date",
    width: "half",
    category: "GSC Search",
  },

  // GA4 Widgets
  {
    id: "ga4-sessions-trend",
    title: "Sessions & Users Over Time",
    description: "Daily traffic volume trend from GA4",
    source: "ga4",
    chartType: "line",
    metric: "sessions",
    secondaryMetric: "totalUsers",
    dimension: "date",
    width: "full",
    category: "GA4 Traffic",
  },
  {
    id: "ga4-channel-bar",
    title: "Traffic by Channel Group",
    description: "Sessions categorized by Organic, Direct, Referral, Social",
    source: "ga4",
    chartType: "bar",
    metric: "sessions",
    dimension: "sessionDefaultChannelGroup",
    width: "half",
    category: "GA4 Traffic",
  },
  {
    id: "ga4-pages-table",
    title: "Top Pages by Engagement",
    description: "Views, engaged sessions, and average engagement time",
    source: "ga4",
    chartType: "table",
    metric: "sessions",
    dimension: "pagePath",
    width: "half",
    category: "GA4 Traffic",
  },
  {
    id: "ga4-funnel-conversion",
    title: "Acquisition to Conversion Funnel",
    description: "Total Users → Engaged Sessions → Conversions",
    source: "ga4",
    chartType: "funnel",
    metric: "sessions",
    width: "half",
    category: "Conversions",
  },
  {
    id: "ga4-events-bar",
    title: "Conversion Events",
    description: "Key conversion and custom event counts",
    source: "ga4",
    chartType: "bar",
    metric: "conversions",
    dimension: "eventName",
    width: "half",
    category: "Conversions",
  },
  {
    id: "ga4-source-table",
    title: "Source / Medium Breakdown",
    description: "Traffic sources driving sessions and conversions",
    source: "ga4",
    chartType: "table",
    metric: "sessions",
    dimension: "sessionSourceMedium",
    width: "half",
    category: "GA4 Traffic",
  },
];

/** Sensible default set of widgets shown for a brand new project. */
export const DEFAULT_MONITOR_WIDGETS: MonitorWidget[] = [
  // 4 Top KPI Stat Cards
  {
    id: "def-stat-clicks",
    title: "Organic Clicks",
    source: "gsc",
    chartType: "stat",
    metric: "clicks",
    width: "third",
  },
  {
    id: "def-stat-impressions",
    title: "Search Impressions",
    source: "gsc",
    chartType: "stat",
    metric: "impressions",
    width: "third",
  },
  {
    id: "def-stat-ctr",
    title: "Average CTR",
    source: "gsc",
    chartType: "stat",
    metric: "ctr",
    width: "third",
  },
  {
    id: "def-stat-sessions",
    title: "GA4 Sessions",
    source: "ga4",
    chartType: "stat",
    metric: "sessions",
    width: "third",
  },

  // Main Clicks & Impressions Trend Line Chart
  {
    id: "def-clicks-trend",
    title: "GSC Clicks & Impressions Over Time",
    source: "gsc",
    chartType: "line",
    metric: "clicks",
    secondaryMetric: "impressions",
    dimension: "date",
    width: "full",
  },

  // GSC Top Queries & Top Pages
  {
    id: "def-top-queries",
    title: "Top Search Queries",
    source: "gsc",
    chartType: "table",
    metric: "clicks",
    dimension: "query",
    width: "half",
  },
  {
    id: "def-top-pages",
    title: "Top Landing Pages (GSC)",
    source: "gsc",
    chartType: "table",
    metric: "clicks",
    dimension: "page",
    width: "half",
  },

  // GA4 Sessions Trend Line Chart
  {
    id: "def-ga4-trend",
    title: "GA4 Sessions & Users Over Time",
    source: "ga4",
    chartType: "line",
    metric: "sessions",
    secondaryMetric: "totalUsers",
    dimension: "date",
    width: "full",
  },

  // GA4 Channels Bar Chart & Acquisition Funnel
  {
    id: "def-ga4-channels",
    title: "Traffic by Channel Group",
    source: "ga4",
    chartType: "bar",
    metric: "sessions",
    dimension: "sessionDefaultChannelGroup",
    width: "half",
  },
  {
    id: "def-ga4-funnel",
    title: "User Acquisition & Conversion Funnel",
    source: "ga4",
    chartType: "funnel",
    metric: "sessions",
    width: "half",
  },

  // Device Split & Geographic Countries
  {
    id: "def-device-split",
    title: "Device Breakdown",
    source: "gsc",
    chartType: "donut",
    metric: "clicks",
    dimension: "device",
    width: "third",
  },
  {
    id: "def-countries",
    title: "Geographic Market Breakdown",
    source: "gsc",
    chartType: "bar",
    metric: "clicks",
    dimension: "country",
    width: "half",
  },
];

const STORAGE_PREFIX = "reai_monitor_layout_v1_";

export function loadMonitorLayout(projectKey: string): MonitorWidget[] {
  if (typeof window === "undefined") return DEFAULT_MONITOR_WIDGETS;
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + projectKey);
    if (!raw) return DEFAULT_MONITOR_WIDGETS;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) {
      return parsed;
    }
  } catch {
    // Malformed JSON fallback
  }
  return DEFAULT_MONITOR_WIDGETS;
}

export function saveMonitorLayout(projectKey: string, widgets: MonitorWidget[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_PREFIX + projectKey, JSON.stringify(widgets));
  } catch {
    // Storage quota exceeded or private mode
  }
}

export function resetMonitorLayout(projectKey: string): MonitorWidget[] {
  if (typeof window !== "undefined") {
    try {
      localStorage.removeItem(STORAGE_PREFIX + projectKey);
    } catch {
      // Ignore
    }
  }
  return DEFAULT_MONITOR_WIDGETS;
}

/* ── Formatting Helpers ── */

export function formatMetricValue(val: number | null | undefined, metric: string): string {
  if (val === null || val === undefined || Number.isNaN(val)) return "—";
  const m = metric.toLowerCase();
  if (m === "ctr" || m === "engagementrate" || m === "bouncerate") {
    const pct = val <= 1 && val >= 0 ? val * 100 : val;
    return `${pct.toFixed(1)}%`;
  }
  if (m === "position") {
    return val > 0 ? `#${val.toFixed(1)}` : "—";
  }
  if (m === "averagesessionduration") {
    const totalSec = Math.round(val);
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    return `${mins}m ${secs < 10 ? "0" : ""}${secs}s`;
  }
  return Math.round(val).toLocaleString();
}

export function formatDelta(
  current: number,
  previous: number,
  metric: string,
): { delta: number; pct: number; label: string; positive: boolean } {
  const m = metric.toLowerCase();
  const isRank = m === "position";

  if (!previous || previous === 0) {
    return { delta: 0, pct: 0, label: "—", positive: true };
  }

  const delta = current - previous;
  const pct = Number(((delta / previous) * 100).toFixed(1));

  // For ranking position, negative delta (e.g. from #12 to #8) is positive/good!
  const positive = isRank ? delta <= 0 : delta >= 0;
  const sign = delta > 0 ? "+" : "";

  let label = `${sign}${pct}%`;
  if (isRank) {
    label = `${sign}${delta.toFixed(1)} ranks`;
  }

  return { delta, pct, label, positive };
}

export const ISO_COUNTRY_NAMES: Record<string, { name: string; flag: string }> = {
  usa: { name: "United States", flag: "🇺🇸" },
  us: { name: "United States", flag: "🇺🇸" },
  gbr: { name: "United Kingdom", flag: "🇬🇧" },
  gb: { name: "United Kingdom", flag: "🇬🇧" },
  uk: { name: "United Kingdom", flag: "🇬🇧" },
  can: { name: "Canada", flag: "🇨🇦" },
  ca: { name: "Canada", flag: "🇨🇦" },
  aus: { name: "Australia", flag: "🇦🇺" },
  au: { name: "Australia", flag: "🇦🇺" },
  deu: { name: "Germany", flag: "🇩🇪" },
  de: { name: "Germany", flag: "🇩🇪" },
  fra: { name: "France", flag: "🇫🇷" },
  fr: { name: "France", flag: "🇫🇷" },
  ind: { name: "India", flag: "🇮🇳" },
  in: { name: "India", flag: "🇮🇳" },
  idn: { name: "Indonesia", flag: "🇮🇩" },
  id: { name: "Indonesia", flag: "🇮🇩" },
  bra: { name: "Brazil", flag: "🇧🇷" },
  br: { name: "Brazil", flag: "🇧🇷" },
  jpn: { name: "Japan", flag: "🇯🇵" },
  jp: { name: "Japan", flag: "🇯🇵" },
  sgp: { name: "Singapore", flag: "🇸🇬" },
  sg: { name: "Singapore", flag: "🇸🇬" },
  mys: { name: "Malaysia", flag: "🇲🇾" },
  my: { name: "Malaysia", flag: "🇲🇾" },
  phl: { name: "Philippines", flag: "🇵🇭" },
  ph: { name: "Philippines", flag: "🇵🇭" },
  vnm: { name: "Vietnam", flag: "🇻🇳" },
  vn: { name: "Vietnam", flag: "🇻🇳" },
  tha: { name: "Thailand", flag: "🇹🇭" },
  th: { name: "Thailand", flag: "🇹🇭" },
  esp: { name: "Spain", flag: "🇪🇸" },
  es: { name: "Spain", flag: "🇪🇸" },
  ita: { name: "Italy", flag: "🇮🇹" },
  it: { name: "Italy", flag: "🇮🇹" },
  nld: { name: "Netherlands", flag: "🇳🇱" },
  nl: { name: "Netherlands", flag: "🇳🇱" },
};

export function lookupCountry(code: string): { name: string; flag: string } {
  const clean = (code || "").trim().toLowerCase();
  return ISO_COUNTRY_NAMES[clean] || { name: code.toUpperCase(), flag: "🌐" };
}
