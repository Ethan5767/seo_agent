-- Remove synthetic traffic defaults. Apply in Supabase SQL editor.
-- Existing rows are preserved; NULL now means the caller did not measure it.
alter table public.traffic_snapshots
  alter column clicks drop default,
  alter column impressions drop default,
  alter column ctr drop default,
  alter column avg_position drop default,
  alter column clicks drop not null,
  alter column impressions drop not null,
  alter column ctr drop not null,
  alter column avg_position drop not null;

comment on column public.traffic_snapshots.clicks is 'Measured Search Console clicks; NULL means not measured.';
comment on column public.traffic_snapshots.impressions is 'Measured Search Console impressions; NULL means not measured.';
comment on column public.traffic_snapshots.ctr is 'Measured Search Console CTR; NULL means not measured.';
comment on column public.traffic_snapshots.avg_position is 'Measured Search Console average position; NULL means not measured.';
