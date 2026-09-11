# Plan — Client & Scan-History Dashboard (web MVP)

**Date:** 2026-09-09
**Stage:** new `history` view in `web/` (Onboard → Measure → Plan already live)
**Cost:** $0 — reads the existing 4-table Supabase DB only; no scanner, no paid API.

## Why

Every Measure run already persists a full snapshot: `scans.report` (whole audit),
`scan_tools.result` (per-tool rows), `findings` (one row each). Nothing in the UI
reads it back. The operator can't see a client's past scans, the score trend, or
reopen a report without paying to re-scan. This closes that loop with pure reads.

## Scope (offline, no paid calls)

1. **DB helpers** (`web/lib/db.ts`):
   - `listClients()` → each client + `{ scans, lastScore, lastScannedAt }` (aggregate).
   - `scanHistory(clientId)` → scans ordered newest-first: `id, created_at, url, score, counts, cost`.
   - `getScanReport(scanId)` → the stored `scans.report` snapshot (reopen, no re-scan).
   - All best-effort, RLS-scoped to the signed-in user, matching existing style.

2. **Pure helper** (`web/lib/trend.ts`) — testable offline:
   - `scoreTrend(scans)` → sparkline points + delta (last vs previous) + direction.

3. **Dashboard view** (`web/app/page.tsx`): new `stage="history"`.
   - Client list (name, domain, last score chip, scan count, last scanned).
   - Click a client → scan-history table + score sparkline + per-scan counts/cost.
   - Click a scan → reopen its stored report in the existing Measure render (free).
   - Nav toggle in header between Onboard / History.

## Non-goals

- No new writes, no schema change (tables + `scans.report` already exist).
- No paid re-scan from history — reopen shows the stored snapshot only.
- No cross-client analytics yet (single-client trend first).

## Test

- `web/lib/trend.test.ts` — pure `scoreTrend` (offline, no network, no cost).
- `tsc --noEmit` for the new DB helpers + view types.
- No live scan (cost rule) — verify DB reads later against real rows on user's say-so.
