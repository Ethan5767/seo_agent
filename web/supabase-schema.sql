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
  n_ok        int not null default 0,
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

-- indexes for the common lookups (a client's scans, newest first)
create index if not exists scans_client_created_idx
  on public.scans (client_id, created_at desc);
create index if not exists clients_user_idx on public.clients (user_id);
create index if not exists scan_tools_scan_idx on public.scan_tools (scan_id);
create index if not exists findings_scan_idx on public.findings (scan_id);
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
alter table public.clients    enable row level security;
alter table public.scans      enable row level security;
alter table public.scan_tools enable row level security;
alter table public.findings   enable row level security;

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
