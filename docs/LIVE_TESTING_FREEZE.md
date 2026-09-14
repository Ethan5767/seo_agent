# Live API Testing Freeze & Integration Directive

> **LIFTED 2026-09-14 by the operator** ("switch to use dataforseo as default"), who
> re-supplied the credentials the same day. This page is kept as the dated record of
> the 2026-09-09 freeze, not current policy. It was also inaccurate while active: the
> code latch it describes (`DATAFORSEO_PAUSE_SPEND` with a "paused by user" message,
> plus a guard in `providers.py`) is not what shipped; d64662d shipped an `x`/`y`
> credential latch and a pytest-only gate instead (B-106). Current rule: see the
> DataForSEO block in `.env.example`.


**Directive Effective Date:** September 9, 2026  
**Status:** ACTIVE / MANDATORY

---

## 1. Directive Summary
By explicit user directive, **all live paid API testing is strictly paused and frozen**.
Under no circumstances should any automated tests, manual CLI runs, or backend crawlers initiate live billable requests to external paid providers (DataForSEO, Bright Data, etc.).

All work must focus **exclusively on frontend and system integration** using existing cached scans, SQLite databases, and local mock/fixture data.

---

## 2. Balance Protection & Safety Latch
- **Account Balance:** `$24.31 USD` (preserved and protected).
- **Safety Latch:** An environment guard `DATAFORSEO_PAUSE_SPEND=1` has been installed in:
  - `.env` (`DATAFORSEO_PAUSE_SPEND=1`)
  - `pipeline/scanner/dataforseo.py` (`call()` method)
  - `pipeline/audit/providers.py` (`dataforseo_findings()` method)
- When active, any attempted network call to DataForSEO returns:
  `skipped: live API testing paused by user to prevent spend`
  with `$0.0000` cost.

---

## 3. Integration Guidelines (Offline / Local Mode)
1. **Use Existing Cached Data:**
   - Real crawl results and audits for `oriendainternationalhospital.com.kh` are already stored in `wf-scan-web.db`.
   - Use these stored records for UI verification, chart rendering, and keyword table displays.
2. **Feature Integration Priority:**
   - Connect and polish all 14 sub-tools and routes in `web/app/` (`/local-seo`, `/traffic-analytics`, `/keyword-gap`, etc.).
   - Ensure consistent compact styling, responsive typography, and functional navigation buttons.
   - Zero synthetic/fake competitor keywords — display verified stored SERP datasets.
3. **Re-enabling Live Testing:**
   - Live testing may ONLY be resumed if the user explicitly instructs: `"resume live testing"`.
   - When resumed, test single isolated endpoints instead of full automated multi-crawl suites.
