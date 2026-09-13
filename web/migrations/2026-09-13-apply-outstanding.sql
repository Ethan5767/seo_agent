-- ═══════════════════════════════════════════════════════════════════════════
-- OUTSTANDING MIGRATIONS — run this once, in the Supabase SQL editor.
--
-- Measured against the live database on 2026-09-13, not assumed. Every table
-- and every column in `web/supabase-schema.sql` was compared against the live
-- PostgREST schema, and the result was narrower than expected:
--
--     clients             ok        scan_metrics        ok
--     scans               ok        keywords            ok
--     scan_tools          ok        competitors         ok
--     findings            ok        backlink_snapshots  ok
--     traffic_snapshots   ok        project_overview    ok (view)
--     remediations        TABLE MISSING
--
-- So there are exactly TWO things outstanding, not "a lot":
--
--   1. `public.remediations` does not exist.
--   2. `traffic_snapshots` has a policy that grants every row to everybody.
--
-- This file is idempotent. Running it twice is safe.
-- ═══════════════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────────────
-- 1. remediations — the table that records what the agent actually changed
--
-- `web/lib/db.ts:remediationHistory` reads it and swallows error codes 42P01
-- and PGRST205 ("relation does not exist") on purpose, so the UI degrades to an
-- empty history rather than throwing. That is why nothing ever complained: the
-- Change History screen has been reporting "no remediations" for every client,
-- and "the table is not there" and "this client has had no fixes applied" look
-- identical from the outside. The same class of quiet absence as B-089.
-- ───────────────────────────────────────────────────────────────────────────
create table if not exists public.remediations (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid not null references public.clients (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  url         text not null default '',
  cycle       text not null default '',                -- YYYY-MM
  applied     int  not null default 0,                 -- items with status "fixed"
  cost_usd    numeric(10,4) not null default 0,
  diffstat    text not null default '',                -- git diff --stat snapshot
  items       jsonb not null default '[]'::jsonb,      -- per-item {code,url,status,note,files}
  created_at  timestamptz not null default now()
);

create index if not exists remediations_client_idx
  on public.remediations (client_id, created_at desc);
create index if not exists remediations_user_idx
  on public.remediations (user_id, created_at desc);

alter table public.remediations enable row level security;
drop policy if exists remediations_owner on public.remediations;
create policy remediations_owner on public.remediations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ───────────────────────────────────────────────────────────────────────────
-- 2. B-091 — traffic_snapshots is readable by anyone holding the anon key
--
-- The policy is `for all using (true) with check (true)` on a table with a
-- user_id column. RLS is ENABLED and the policy is NAMED "owner", so both
-- signals a reviewer scans for are green; `using (true)` enforces nothing.
--
-- The anon key is PUBLIC by design - it ships in the browser bundle, because
-- RLS is what protects the data. Measured 2026-09-13 with that key, from
-- outside: every other table returned `content-range: */0`, and this one
-- returned **0-2/170** - all 170 rows, carrying site_url, clicks, impressions,
-- CTR, average position, country and device splits, and the full `top_queries`
-- array: the real search terms real people used to reach a customer's site.
--
-- ⚠️  THE NEXT STATEMENT DELETES ROWS.
--
--     All 170 rows have user_id NULL. They predate the route stamping it, so
--     they belong to nobody, and under the corrected policy no user could ever
--     see them again - while anyone with the anon key still could, until they
--     are gone.
--
--     This table is a CACHE. Every row is re-derived from Search Console on the
--     next page load. Deleting them costs a refresh, not data.
--
--     Check the count first if you want to see it for yourself:
--         select count(*) from public.traffic_snapshots where user_id is null;
-- ───────────────────────────────────────────────────────────────────────────
delete from public.traffic_snapshots where user_id is null;

-- A nullable user_id is how rows became unattributable in the first place.
alter table public.traffic_snapshots
  alter column user_id set not null;

drop policy if exists traffic_snapshots_owner on public.traffic_snapshots;
create policy traffic_snapshots_owner on public.traffic_snapshots
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ───────────────────────────────────────────────────────────────────────────
-- 3. Prove it. Both queries must return ZERO rows.
-- ───────────────────────────────────────────────────────────────────────────

-- (a) Any table with a user_id column whose policy does not reference user_id.
select c.relname as table_name,
       p.polname as policy,
       pg_get_expr(p.polqual, p.polrelid) as using_clause
from pg_policy p
join pg_class c on c.oid = p.polrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = c.relname
                and column_name = 'user_id')
  and pg_get_expr(p.polqual, p.polrelid) not like '%user_id%';

-- (b) Any table with a user_id column and RLS switched off.
select c.relname as table_name
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and not c.relrowsecurity
  and exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = c.relname
                and column_name = 'user_id');
