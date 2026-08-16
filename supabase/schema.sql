-- ============================================================
-- Ranní moudra — Supabase / Postgres schema (v1)
-- Run this once in Supabase Studio -> SQL Editor.
-- Designed so v2 (ratings, weighted selection) drops in without a rebuild.
-- ============================================================

-- ---------- BOOKS ----------
create table if not exists public.books (
    id       bigint generated always as identity primary key,
    title    text        not null,
    author   text        not null,
    year     int,                                 -- rok vydání (volitelné)
    category text,                                -- téma/žánr: finance, zdraví, vztahy… (volitelné)
    active   boolean     not null default true,   -- 0 = vyřadit z automatických zpráv
    note     text,                                -- osobní poznámka (volitelné)
    added_at timestamptz not null default now(),
    unique (title, author)
);

-- ---------- INSIGHTS ----------
create table if not exists public.insights (
    id         bigint generated always as identity primary key,
    book_id    bigint not null references public.books(id) on delete cascade,
    theme      text   not null,                   -- short heading, e.g. "Kolik je dost"
    body       text   not null,                   -- 2-3 paragraphs, paraphrased (never verbatim quotes)
    verified   boolean not null default false,    -- did we web-verify the core idea (newer books)
    lang       text   not null default 'cs',
    created_at timestamptz not null default now(),
    unique (book_id, theme)                        -- stops the generator inserting duplicates
);

-- ---------- ACTIVITY ----------
-- One row per send. rating/rated_at stay NULL in v1 (filled in v2).
create table if not exists public.activity (
    id         bigint generated always as identity primary key,
    insight_id bigint not null references public.insights(id) on delete cascade,
    sent_at    timestamptz not null default now(),
    channel    text   not null default 'push' check (channel in ('push', 'manual')),
    rating     int    check (rating between 1 and 5),   -- v2
    rated_at   timestamptz                               -- v2
);

create index if not exists idx_activity_insight on public.activity(insight_id);
create index if not exists idx_activity_sent_at on public.activity(sent_at desc);
create index if not exists idx_insights_book    on public.insights(book_id);

-- ============================================================
-- Row Level Security
-- anon key (used in the public web page) may ONLY read.
-- The send/seed/generate scripts use the service_role key, which
-- bypasses RLS entirely, so they can still write.
-- ============================================================
alter table public.books    enable row level security;
alter table public.insights enable row level security;
alter table public.activity enable row level security;

-- Drop-and-recreate so this file is safe to re-run.
drop policy if exists "anon read books"    on public.books;
drop policy if exists "anon read insights" on public.insights;
drop policy if exists "anon read activity" on public.activity;

create policy "anon read books"    on public.books    for select to anon using (true);
create policy "anon read insights" on public.insights for select to anon using (true);
create policy "anon read activity" on public.activity for select to anon using (true);
-- No insert/update/delete policies for anon => writes are blocked for the web page.

-- ============================================================
-- Convenience view: the most recently sent insight (used by the
-- web page when no ?id= is provided). Joined + flattened so the
-- page needs a single simple query.
-- ============================================================
create or replace view public.v_last_sent as
select
    i.id            as insight_id,
    i.theme,
    i.body,
    i.verified,
    b.title         as book_title,
    b.author        as book_author,
    a.sent_at
from public.activity a
join public.insights i on i.id = a.insight_id
join public.books    b on b.id = i.book_id
order by a.sent_at desc
limit 1;

grant select on public.v_last_sent to anon;

-- ============================================================
-- Convenience view: insights that have NEVER been sent
-- (no matching row in activity). The send script reads this to
-- pick the next one. Kept flat so the script needs no joins.
-- NOTE: only the service_role key reads this (RLS bypassed);
-- we do NOT grant it to anon.
-- ============================================================
create or replace view public.v_unsent_insights as
select
    i.id       as insight_id,
    i.book_id,
    b.title    as book_title,
    b.author   as book_author,
    i.theme,
    i.body
from public.insights i
join public.books b on b.id = i.book_id
where b.active
  and not exists (
      select 1 from public.activity a where a.insight_id = i.id
  );
