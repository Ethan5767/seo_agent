/**
 * Monitor Data Fetching Layer.
 *
 * Calls `/api/gsc/query` and `/api/ga4/query` via `authedFetch`, applying global filters,
 * date ranges, and comparison intervals. Returns structured datasets ready for widgets.
 */

import { authedFetch } from "@/lib/authedFetch";
import { widgetDateRange, type MonitorGlobalFilters, type MonitorWidget } from "./types";

export interface GscDataPoint {
  key: string;
  keys: string[];
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GscQueryResult {
  ok: boolean;
  rows: GscDataPoint[];
  comparisonRows?: GscDataPoint[];
  totals: {
    clicks: number;
    impressions: number;
    ctr: number;
    position: number;
  };
  comparisonTotals?: {
    clicks: number;
    impressions: number;
    ctr: number;
    position: number;
  };
  error?: string;
  source: "gsc";
}

export interface Ga4DataPoint {
  key: string;
  keys: string[];
  metrics: Record<string, number>;
}

export interface Ga4QueryResult {
  ok: boolean;
  rows: Ga4DataPoint[];
  comparisonRows?: Ga4DataPoint[];
  totals: Record<string, number>;
  comparisonTotals?: Record<string, number>;
  error?: string;
  source: "ga4";
}

/** Fetch GSC data for a specific widget and filters */
export async function fetchWidgetGscData(
  siteUrl: string,
  widget: MonitorWidget,
  filters: MonitorGlobalFilters,
): Promise<GscQueryResult> {
  if (!siteUrl) {
    return {
      ok: false,
      rows: [],
      totals: { clicks: 0, impressions: 0, ctr: 0, position: 0 },
      error: "No Search Console property selected.",
      source: "gsc",
    };
  }

  const dimension = widget.dimension || (widget.chartType === "line" ? "date" : "query");
  const dimensions = widget.chartType === "stat" ? [] : [dimension];

  const range = widgetDateRange(widget, filters);
  const { startDate, endDate, compareStartDate, compareEndDate } = range;

  // Build dimensionFilterGroups
  const gscFilters: Array<{ dimension: string; operator: string; expression: string }> = [];

  if (filters.deviceFilter !== "all") {
    gscFilters.push({
      dimension: "device",
      operator: "equals",
      expression: filters.deviceFilter.toUpperCase(),
    });
  }

  if (filters.countryFilter && filters.countryFilter !== "all") {
    gscFilters.push({
      dimension: "country",
      operator: "equals",
      expression: filters.countryFilter.toLowerCase(),
    });
  }

  if (filters.pageFilter && filters.pageFilter.trim()) {
    gscFilters.push({
      dimension: "page",
      operator: "contains",
      expression: filters.pageFilter.trim(),
    });
  }

  if (filters.searchAppearanceFilter && filters.searchAppearanceFilter !== "all") {
    gscFilters.push({
      dimension: "searchAppearance",
      operator: "equals",
      expression: filters.searchAppearanceFilter,
    });
  }

  const payload: Record<string, any> = {
    siteUrl,
    startDate,
    endDate,
    dimensions,
    rowLimit: widget.chartType === "table" ? 100 : 50,
  };

  if (compareStartDate && compareEndDate) {
    payload.compareStartDate = compareStartDate;
    payload.compareEndDate = compareEndDate;
  }

  if (gscFilters.length > 0) {
    payload.dimensionFilterGroups = [{ groupType: "and", filters: gscFilters }];
  }

  try {
    const res = await authedFetch("/api/gsc/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let errMsg = `Search Console returned status ${res.status}`;
      try {
        const j = await res.json();
        if (j?.error) errMsg = j.error;
      } catch {
        // Not JSON
      }
      return {
        ok: false,
        rows: [],
        totals: { clicks: 0, impressions: 0, ctr: 0, position: 0 },
        error: errMsg,
        source: "gsc",
      };
    }

    const data = await res.json();
    const rawRows = Array.isArray(data?.rows) ? data.rows : [];
    const compRows = Array.isArray(data?.comparisonRows) ? data.comparisonRows : [];

    const mapRows = (rows: any[]): GscDataPoint[] =>
      rows.map((r) => {
        const keys = Array.isArray(r.keys) ? r.keys : [];
        return {
          key: keys[0] || "",
          keys,
          clicks: r.clicks || 0,
          impressions: r.impressions || 0,
          ctr: Number(((r.ctr || 0) * 100).toFixed(2)),
          position: Number((r.position || 0).toFixed(1)),
        };
      });

    const mapped = mapRows(rawRows);
    const mappedComp = compRows.length > 0 ? mapRows(compRows) : undefined;

    const calcTotals = (pts: GscDataPoint[]) => {
      let clicks = 0;
      let impressions = 0;
      let weightedPos = 0;
      for (const p of pts) {
        clicks += p.clicks;
        impressions += p.impressions;
        weightedPos += p.position * p.impressions;
      }
      const ctr = impressions > 0 ? Number(((clicks / impressions) * 100).toFixed(2)) : 0;
      const position = impressions > 0 ? Number((weightedPos / impressions).toFixed(1)) : 0;
      return { clicks, impressions, ctr, position };
    };

    return {
      ok: true,
      rows: mapped,
      comparisonRows: mappedComp,
      totals: calcTotals(mapped),
      comparisonTotals: mappedComp ? calcTotals(mappedComp) : undefined,
      source: "gsc",
    };
  } catch (err: any) {
    return {
      ok: false,
      rows: [],
      totals: { clicks: 0, impressions: 0, ctr: 0, position: 0 },
      error: err?.message || "Failed to reach Search Console API",
      source: "gsc",
    };
  }
}

/** Fetch GA4 data for a specific widget and filters */
export async function fetchWidgetGa4Data(
  propertyId: string,
  widget: MonitorWidget,
  filters: MonitorGlobalFilters,
): Promise<Ga4QueryResult> {
  if (!propertyId) {
    return {
      ok: false,
      rows: [],
      totals: {},
      error: "No Google Analytics 4 property selected.",
      source: "ga4",
    };
  }

  const dimension = widget.dimension || (widget.chartType === "line" ? "date" : "sessionDefaultChannelGroup");
  const dimensions = widget.chartType === "stat" ? [] : [dimension];

  const primaryMetric = widget.metric || "sessions";
  const metrics = [primaryMetric];
  if (widget.secondaryMetric && widget.secondaryMetric !== primaryMetric) {
    metrics.push(widget.secondaryMetric);
  }

  const range = widgetDateRange(widget, filters);
  const { startDate, endDate, compareStartDate, compareEndDate } = range;

  // Build GA4 dimensionFilter
  const filterExpressions: any[] = [];

  if (filters.deviceFilter !== "all") {
    filterExpressions.push({
      filter: {
        fieldName: "deviceCategory",
        stringFilter: { value: filters.deviceFilter.toLowerCase(), matchType: "EXACT" },
      },
    });
  }

  if (filters.countryFilter && filters.countryFilter !== "all") {
    filterExpressions.push({
      filter: {
        fieldName: "country",
        stringFilter: { value: filters.countryFilter, matchType: "CONTAINS" },
      },
    });
  }

  if (filters.pageFilter && filters.pageFilter.trim()) {
    filterExpressions.push({
      filter: {
        fieldName: "pagePath",
        stringFilter: { value: filters.pageFilter.trim(), matchType: "CONTAINS" },
      },
    });
  }

  if (filters.channelFilter && filters.channelFilter !== "all") {
    filterExpressions.push({
      filter: {
        fieldName: "sessionDefaultChannelGroup",
        stringFilter: { value: filters.channelFilter, matchType: "EXACT" },
      },
    });
  }

  let dimensionFilter: any = undefined;
  if (filterExpressions.length === 1) {
    dimensionFilter = filterExpressions[0];
  } else if (filterExpressions.length > 1) {
    dimensionFilter = {
      andGroup: {
        expressions: filterExpressions,
      },
    };
  }

  const payload: Record<string, any> = {
    property: propertyId,
    startDate,
    endDate,
    metrics,
    dimensions,
    dimensionFilter,
    limit: widget.chartType === "table" ? 100 : 50,
  };

  if (compareStartDate && compareEndDate) {
    payload.compareStartDate = compareStartDate;
    payload.compareEndDate = compareEndDate;
  }

  try {
    const res = await authedFetch("/api/ga4/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let errMsg = `GA4 returned status ${res.status}`;
      try {
        const j = await res.json();
        if (j?.error) errMsg = j.error;
      } catch {
        // Not JSON
      }
      return {
        ok: false,
        rows: [],
        totals: {},
        error: errMsg,
        source: "ga4",
      };
    }

    const data = await res.json();
    const rawRows = Array.isArray(data?.rows) ? data.rows : [];
    const metricHeaders: string[] = Array.isArray(data?.metricHeaders)
      ? data.metricHeaders.map((h: any) => h.name)
      : metrics;

    const mappedRows: Ga4DataPoint[] = [];
    const mappedCompRows: Ga4DataPoint[] = [];
    const totals: Record<string, number> = {};
    const compTotals: Record<string, number> = {};

    for (const r of rawRows) {
      const dimVals = Array.isArray(r.dimensionValues) ? r.dimensionValues.map((v: any) => v.value) : [];
      const metVals = Array.isArray(r.metricValues) ? r.metricValues.map((v: any) => parseFloat(v.value) || 0) : [];

      const rowMetrics: Record<string, number> = {};
      metricHeaders.forEach((name, idx) => {
        rowMetrics[name] = metVals[idx] ?? 0;
      });

      const isComp = r.dateRange === "date_range_1";

      const point: Ga4DataPoint = {
        key: dimVals[0] || "",
        keys: dimVals,
        metrics: rowMetrics,
      };

      if (isComp) {
        mappedCompRows.push(point);
        metricHeaders.forEach((name) => {
          compTotals[name] = (compTotals[name] || 0) + (rowMetrics[name] || 0);
        });
      } else {
        mappedRows.push(point);
        metricHeaders.forEach((name) => {
          totals[name] = (totals[name] || 0) + (rowMetrics[name] || 0);
        });
      }
    }

    return {
      ok: true,
      rows: mappedRows,
      comparisonRows: mappedCompRows.length > 0 ? mappedCompRows : undefined,
      totals,
      comparisonTotals: mappedCompRows.length > 0 ? compTotals : undefined,
      source: "ga4",
    };
  } catch (err: any) {
    return {
      ok: false,
      rows: [],
      totals: {},
      error: err?.message || "Failed to reach Google Analytics 4 API",
      source: "ga4",
    };
  }
}
