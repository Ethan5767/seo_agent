-- ═══════════════════════════════════════════════════════════════════════════
-- REAI — run this once in the Supabase SQL editor. Paste the whole thing.
--
-- Safe to run repeatedly: every statement is `if not exists` / `or replace` /
-- `drop policy if exists` + recreate. It contains no DROP TABLE, no TRUNCATE
-- and no DROP COLUMN.
--
-- ONE deletion, and it is deliberate — see the note on it below.
--
-- Afterwards, from web/:  npm run db:check    ->  must print "In sync."
-- ═══════════════════════════════════════════════════════════════════════════

-- ── B-091, step 1 of 2 ─────────────────────────────────────────────────────
-- traffic_snapshots holds 170 rows with user_id NULL. They predate the route
-- stamping it, so they belong to nobody: no corrected policy can ever match
-- them, while anyone holding the PUBLIC anon key can still read them. The table
-- is a CACHE — every row is re-derived from Search Console on the next load, so
-- this costs a refresh, not data. It must run BEFORE the schema below, because
-- `alter column user_id set not null` fails while a NULL remains.
--
--   select count(*) from public.traffic_snapshots where user_id is null;  -- 170
delete from public.traffic_snapshots where user_id is null;

-- SEO/AEO Pipeline — Supabase schema
-- Paste into Supabase → SQL Editor → Run. Safe to re-run (idempotent-ish).
-- Auth is handled by Supabase Auth (auth.users). Every row is owned by a user
-- and protected by Row Level Security so users only see their own clients/scans.

-- ── clients (the Onboard profile) ────────────────────────────────────────────
create table if not exists public.clients (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users (id) on delete cascade,
  business     text not null default '',
  domain       text not null,                       -- e.g. example.com
  website      text not null default '',            -- https://example.com
  model        text not null default 'B' check (model in ('A', 'B')),
  repo         text not null default '',             -- Model B repo path/URL
  tier         int  not null default 1 check (tier between 1 and 3),
  keywords     text[] not null default '{}',
  competitors  text[] not null default '{}',
  goal         text not null default '',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- ── scans (one Measure run against a client) ─────────────────────────────────
create table if not exists public.scans (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid not null references public.clients (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  url         text not null,
  model       text not null default 'B',
  crawl       boolean not null default false,        -- legacy (pre tool-selection)
  deep        boolean not null default false,        -- legacy (pre tool-selection)
  tools       jsonb not null default '[]'::jsonb,     -- selected tool keys this run
  score       int,                                   -- 0-100 headline
  counts      jsonb not null default '{}'::jsonb,     -- {error,warn,info,ok}
  cost        numeric(10,4) not null default 0,       -- total $ this run
  report      jsonb not null default '{}'::jsonb,     -- the full grouped audit
  log         jsonb not null default '[]'::jsonb,     -- "what we did" lines
  created_at  timestamptz not null default now()
);

-- ── scan_tools (one row per tool per scan — cost + finding counts) ───────────
create table if not exists public.scan_tools (
  id          uuid primary key default gen_random_uuid(),
  scan_id     uuid not null references public.scans (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  tool        text not null,                          -- tool label, e.g. "On-page SEO"
  status      text not null default '',               -- the tool's status line
  cost        numeric(10,4) not null default 0,        -- $ this tool cost
  n_error     int not null default 0,
  n_warn      int not null default 0,
  n_info      int not null default 0,
  n_ok        int not null default 0,
  result      jsonb not null default '[]'::jsonb,      -- this tool's full rows (complete result)
  created_at  timestamptz not null default now()
);

-- ── findings (one row per individual issue — the queryable history) ──────────
create table if not exists public.findings (
  id          uuid primary key default gen_random_uuid(),
  scan_id     uuid not null references public.scans (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  tool        text not null default '',               -- which tool found it
  code        text not null default '',               -- stable id, e.g. "dfs.op.no_title"
  what        text not null default '',
  severity    text not null default '',               -- error | warn | info | ok
  why         text not null default '',
  fix         text not null default '',
  detail      text not null default '',
  created_at  timestamptz not null default now()
);

-- ── remediations (one Model-B apply run — what Claude Code fixed) ────────────
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

-- indexes for the common lookups (a client's scans, newest first)
create index if not exists scans_client_created_idx
  on public.scans (client_id, created_at desc);
create index if not exists clients_user_idx on public.clients (user_id);
create index if not exists scan_tools_scan_idx on public.scan_tools (scan_id);
create index if not exists findings_scan_idx on public.findings (scan_id);
create index if not exists remediations_client_created_idx
  on public.remediations (client_id, created_at desc);
-- trend/ratchet: the same finding code for a user over time
create index if not exists findings_user_code_idx on public.findings (user_id, code, created_at desc);

-- keep clients.updated_at fresh
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists clients_touch on public.clients;
create trigger clients_touch before update on public.clients
  for each row execute function public.touch_updated_at();

-- ── Row Level Security ───────────────────────────────────────────────────────
alter table public.clients      enable row level security;
alter table public.scans        enable row level security;
alter table public.scan_tools   enable row level security;
alter table public.findings     enable row level security;
alter table public.remediations enable row level security;

-- every table: owner-only (users see only their own rows)
drop policy if exists clients_owner on public.clients;
create policy clients_owner on public.clients
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists scans_owner on public.scans;
create policy scans_owner on public.scans
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists scan_tools_owner on public.scan_tools;
create policy scan_tools_owner on public.scan_tools
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists findings_owner on public.findings;
create policy findings_owner on public.findings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists remediations_owner on public.remediations;
create policy remediations_owner on public.remediations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- v2 STRENGTHENING (additive + idempotent — safe to run over an existing DB)
-- Adds data-integrity constraints, a flat metrics table for cheap trend charts,
-- and dedicated entity tables so rankings/competitors/backlinks stop living only
-- inside scans.report jsonb. Re-runnable: columns use IF NOT EXISTS, constraints
-- are added NOT VALID inside DO/exception guards so existing rows aren't rejected.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── integrity: new columns on existing tables ────────────────────────────────
alter table public.scans    add column if not exists status      text not null default 'done';
alter table public.scans    add column if not exists crawl_pages int  not null default 1;
alter table public.scans    add column if not exists duration_ms int;
alter table public.findings add column if not exists category    text not null default '';
alter table public.findings add column if not exists finding_fp  text not null default '';  -- stable id: code|url (ratchet + remediation link)

-- ── integrity: CHECK constraints (NOT VALID → applies to new rows, never
--    rejects legacy rows; guarded so a re-run is a no-op) ─────────────────────
do $$ begin
  alter table public.findings add constraint findings_severity_chk
    check (severity in ('error','warn','info','ok','')) not valid;
exception when duplicate_object then null; end $$;
do $$ begin
  alter table public.scans add constraint scans_status_chk
    check (status in ('running','done','error')) not valid;
exception when duplicate_object then null; end $$;
do $$ begin
  alter table public.scans add constraint scans_score_range_chk
    check (score is null or score between 0 and 100) not valid;
exception when duplicate_object then null; end $$;

-- ── scan_metrics: one flat row per scan — the headline numbers a dashboard/
--    trend chart needs, without digging through report jsonb every read. ──────
create table if not exists public.scan_metrics (
  id               uuid primary key default gen_random_uuid(),
  scan_id          uuid not null references public.scans (id) on delete cascade,
  client_id        uuid not null references public.clients (id) on delete cascade,
  user_id          uuid not null references auth.users (id) on delete cascade,
  score            int,                                    -- 0-100 site health
  n_error          int not null default 0,
  n_warn           int not null default 0,
  n_info           int not null default 0,
  n_ok             int not null default 0,
  checks_total     int not null default 0,
  cost             numeric(10,4) not null default 0,
  ai_visibility    int,                                    -- AEO answer-ready %
  organic_keywords int,                                    -- from DataForSEO (null until run)
  organic_traffic  int,
  backlinks        int,
  ref_domains      int,
  created_at       timestamptz not null default now(),
  unique (scan_id)
);

-- ── keywords: ranked keywords per scan — powers the position-tracking widget ─
create table if not exists public.keywords (
  id            uuid primary key default gen_random_uuid(),
  scan_id       uuid references public.scans (id) on delete cascade,
  client_id     uuid not null references public.clients (id) on delete cascade,
  user_id       uuid not null references auth.users (id) on delete cascade,
  keyword       text not null,
  position      int,
  volume        int,
  intent        text not null default '',
  url           text not null default '',
  serp_features text[] not null default '{}',
  created_at    timestamptz not null default now()
);

-- ── competitors: tracked per scan (snapshot of who ranks alongside) ──────────
create table if not exists public.competitors (
  id         uuid primary key default gen_random_uuid(),
  scan_id    uuid references public.scans (id) on delete cascade,
  client_id  uuid not null references public.clients (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  domain     text not null,
  created_at timestamptz not null default now()
);

-- ── backlink snapshots: per-scan link profile totals for a trend ─────────────
create table if not exists public.backlink_snapshots (
  id          uuid primary key default gen_random_uuid(),
  scan_id     uuid references public.scans (id) on delete cascade,
  client_id   uuid not null references public.clients (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  backlinks   int,
  ref_domains int,
  toxic       int,
  created_at  timestamptz not null default now()
);

-- ── indexes for the dashboard's hot paths ────────────────────────────────────
create index if not exists scan_metrics_client_created_idx on public.scan_metrics (client_id, created_at desc);
create index if not exists keywords_client_created_idx     on public.keywords (client_id, created_at desc);
create index if not exists keywords_scan_idx               on public.keywords (scan_id);
create index if not exists competitors_client_idx          on public.competitors (client_id);
create index if not exists backlink_snap_client_idx        on public.backlink_snapshots (client_id, created_at desc);
create index if not exists findings_scan_sev_idx           on public.findings (scan_id, severity);
create index if not exists findings_user_fp_idx            on public.findings (user_id, finding_fp);

-- ── project_overview: latest metrics per client in one read (the Folders
--    dashboard). security_invoker so the caller's RLS still applies. ──────────
create or replace view public.project_overview
  with (security_invoker = true) as
select
  c.id as client_id, c.user_id, c.business, c.domain, c.website, c.model, c.tier,
  m.scan_id, m.score, m.n_error, m.n_warn, m.n_info, m.n_ok, m.checks_total,
  m.cost, m.ai_visibility, m.organic_keywords, m.organic_traffic, m.backlinks,
  m.ref_domains, m.created_at as last_scanned
from public.clients c
left join lateral (
  select * from public.scan_metrics sm
  where sm.client_id = c.id
  order by sm.created_at desc
  limit 1
) m on true;

-- ── RLS on the new tables (owner-only, same as the rest) ─────────────────────
alter table public.scan_metrics       enable row level security;
alter table public.keywords           enable row level security;
alter table public.competitors        enable row level security;
alter table public.backlink_snapshots enable row level security;

drop policy if exists scan_metrics_owner on public.scan_metrics;
create policy scan_metrics_owner on public.scan_metrics
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists keywords_owner on public.keywords;
create policy keywords_owner on public.keywords
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists competitors_owner on public.competitors;
create policy competitors_owner on public.competitors
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists backlink_snapshots_owner on public.backlink_snapshots;
create policy backlink_snapshots_owner on public.backlink_snapshots
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ── traffic_snapshots (Google Search Console & Traffic telemetry cache) ───────
create table if not exists public.traffic_snapshots (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references auth.users (id) on delete cascade,
  domain       text not null,
  site_url     text not null,
  clicks       int not null default 0,
  impressions  int not null default 0,
  ctr          numeric(5,2) not null default 0,
  avg_position numeric(5,2) not null default 0,
  top_queries  jsonb not null default '[]'::jsonb,
  countries    jsonb not null default '[]'::jsonb,
  devices      jsonb not null default '{}'::jsonb,
  date_trend   jsonb not null default '[]'::jsonb,
  created_at   timestamptz not null default now()
);

create index if not exists traffic_snapshots_domain_idx
  on public.traffic_snapshots (domain, created_at desc);
create index if not exists traffic_snapshots_site_url_idx
  on public.traffic_snapshots (site_url, created_at desc);

-- B-091. This table had RLS ENABLED and a policy named `traffic_snapshots_owner`
-- that read `for all using (true) with check (true)` - every row, to everybody,
-- for select, insert, update and delete. RLS being on made it look protected and
-- the name made it look owner-scoped; it was neither.
--
-- The anon key is PUBLIC - it ships in the browser bundle by design, because RLS
-- is what protects the data. With this policy it protected nothing: an anonymous
-- read returned 170 of 170 rows, carrying every user's site_url, clicks,
-- impressions, CTR, average position, per-country and per-device splits, and the
-- full `top_queries` array - the actual search terms their customers used.
--
-- Every other table in this file gets `auth.uid() = user_id`. This one is now
-- the same. Nothing in the application needed the difference: the route already
-- writes `user_id` and already filters on it.
alter table public.traffic_snapshots enable row level security;
alter table public.traffic_snapshots
  alter column user_id set not null;
drop policy if exists traffic_snapshots_owner on public.traffic_snapshots;
create policy traffic_snapshots_owner on public.traffic_snapshots
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ═══════════════════════════════════════════════════════════════════════════
-- PROOF. Both queries must return ZERO rows.
-- ═══════════════════════════════════════════════════════════════════════════

-- (a) any per-user table whose policy does not reference user_id
select c.relname as table_name, p.polname as policy,
       pg_get_expr(p.polqual, p.polrelid) as using_clause
from pg_policy p
join pg_class c on c.oid = p.polrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = c.relname
                and column_name = 'user_id')
  and pg_get_expr(p.polqual, p.polrelid) not like '%user_id%';

-- (b) any per-user table with RLS switched off
select c.relname as table_name
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
  and exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = c.relname
                and column_name = 'user_id');
