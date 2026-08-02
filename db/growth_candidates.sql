-- Gazetteer-growth candidates: a frequency-ranked review queue of JD skills the
-- Haiku parser named that the deterministic gazetteer (src/matching/gazetteer.py)
-- does not recognize. Written fire-and-forget by src/growth.py via the RPC below.
-- Idempotent — safe to re-run. Apply against the Supabase Postgres (SQL Editor, or
-- psql/asyncpg over the session pooler). Not auto-applied by the app.
--
-- Curation query:
--   select skill, occurrences, sample_title, last_seen
--   from public.growth_candidates order by occurrences desc, last_seen desc;

create table if not exists public.growth_candidates (
    skill_key    text primary key,          -- lower(trim(skill)) — dedup key
    skill        text not null,             -- display form (first seen)
    occurrences  integer not null default 1,
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now(),
    sample_title text                        -- an example JD title where it appeared
);

comment on table public.growth_candidates is
  'Gazetteer growth queue: JD skills Haiku named that the deterministic gazetteer does not recognize. Frequency-ranked (occurrences) for human curation into src/matching/gazetteer.py. Written fire-and-forget by src/growth.py; RLS on with no policies = service-role only.';

-- Lock down: RLS on, no policies → only the service role (which bypasses RLS) can
-- touch it. Not exposed to anon/authenticated.
alter table public.growth_candidates enable row level security;

-- On-conflict-increment upsert over a batch of candidates. SECURITY INVOKER so it
-- runs with the caller's privileges (service role); de-dupes within the batch by the
-- normalized key to avoid "cannot affect row a second time".
create or replace function public.record_growth_candidates(p_candidates text[], p_title text)
returns void
language sql
security invoker
as $func$
  insert into public.growth_candidates (skill_key, skill, sample_title)
  select key, min(s), p_title
  from (
    select lower(trim(s)) as key, s
    from unnest(p_candidates) as s
    where trim(s) <> ''
  ) d
  group by key
  on conflict (skill_key) do update
     set occurrences = growth_candidates.occurrences + 1,
         last_seen = now(),
         sample_title = excluded.sample_title;
$func$;

grant insert, update, select on public.growth_candidates to service_role;
revoke execute on function public.record_growth_candidates(text[], text) from public;
grant execute on function public.record_growth_candidates(text[], text) to service_role;

-- Tell PostgREST to refresh its schema cache so the RPC is callable immediately.
notify pgrst, 'reload schema';
