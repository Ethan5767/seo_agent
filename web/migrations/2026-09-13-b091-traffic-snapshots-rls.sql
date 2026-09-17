-- B-091 — traffic_snapshots was world-readable. Run this against the live database.
--
-- WHAT WAS WRONG
--   The table had Row Level Security ENABLED and a policy named
--   `traffic_snapshots_owner` whose body was:
--
--       for all using (true) with check (true)
--
--   RLS being on made it look protected. The name made it look owner-scoped. It
--   was neither: `using (true)` grants every row to every role, for select,
--   insert, update and delete.
--
--   The `anon` key is public - it ships in the browser bundle on purpose,
--   because RLS is the thing that protects the data. Measured on 2026-09-13, an
--   anonymous read returned **170 of 170 rows**, each carrying site_url, clicks,
--   impressions, CTR, average position, country and device splits, and the full
--   `top_queries` array: the real search terms that brought real people to a
--   customer's site.
--
--   Every other table in the schema uses `auth.uid() = user_id`. This one was
--   the only exception, and nothing in the application needed it - the route at
--   app/api/traffic/snapshot/route.ts already writes user_id and already filters
--   on it.
--
-- STEP 1 — the orphans.
--   All 170 existing rows have user_id NULL, so they predate the route writing
--   it and belong to nobody. They cannot be attributed, and under the corrected
--   policy they would be invisible to every user while still being readable by
--   anyone holding the anon key until they are gone.
--
--   This table is a CACHE. Every row is re-derivable from Search Console on the
--   next load, so deleting them costs a refresh, not data.
--
--   Read the count first, then delete:
--
--       select count(*) from public.traffic_snapshots where user_id is null;
--
delete from public.traffic_snapshots where user_id is null;

-- STEP 2 — make the column what the policy assumes.
--   A nullable user_id is how rows became unattributable in the first place.
alter table public.traffic_snapshots
  alter column user_id set not null;

-- STEP 3 — the actual fix.
drop policy if exists traffic_snapshots_owner on public.traffic_snapshots;
create policy traffic_snapshots_owner on public.traffic_snapshots
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- STEP 4 — prove it, from the code rather than from this file.
--   Every policy on a table that HAS a user_id column must reference it. Run
--   this after applying; it must return zero rows.
--
--       select c.relname as table_name, p.polname as policy, pg_get_expr(p.polqual, p.polrelid) as using_clause
--       from pg_policy p
--       join pg_class c on c.oid = p.polrelid
--       join pg_namespace n on n.oid = c.relnamespace
--       where n.nspname = 'public'
--         and exists (select 1 from information_schema.columns
--                     where table_schema = 'public' and table_name = c.relname
--                       and column_name = 'user_id')
--         and pg_get_expr(p.polqual, p.polrelid) not like '%user_id%';
--
--   And from outside, with the PUBLIC anon key, which must now return nothing:
--
--       curl -s "$SUPABASE_URL/rest/v1/traffic_snapshots?select=id&limit=1" \
--         -H "apikey: $ANON_KEY" -H "Authorization: Bearer $ANON_KEY" \
--         -H "Prefer: count=exact" -i | grep -i content-range
--       # expect: content-range: */0
