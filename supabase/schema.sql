-- ============================================================
-- Ranní moudra — Supabase / Postgres schema (v2, více uživatelů)
-- Run this once in Supabase Studio -> SQL Editor.
-- Pro EXISTUJÍCÍ (jednouživatelskou) databázi nespouštěj tohle celé,
-- ale migraci: supabase/migrations/002-multi-user.sql
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

-- ---------- SUBSCRIBERS ----------
-- Odběratelé (uživatelé). Každý má vlastní ntfy téma a vlastní knihovnu
-- (které knihy dostává — viz subscriber_books).
create table if not exists public.subscribers (
    id          bigint generated always as identity primary key,
    slug        text        not null unique,        -- 'marek', 'zuzka'
    name        text        not null,
    ntfy_topic  text        not null,               -- vlastní ntfy téma
    active      boolean     not null default true,
    created_at  timestamptz not null default now()
);

-- ---------- SUBSCRIBER_BOOKS (vlastní knihovna) ----------
-- Kdo má kterou knihu ve své knihovně. Knihy i myšlenky se ukládají jen
-- jednou a sdílí se; tahle tabulka řídí, kdo co dostává. Plní sync_books.py.
create table if not exists public.subscriber_books (
    subscriber_id bigint not null references public.subscribers(id) on delete cascade,
    book_id       bigint not null references public.books(id)       on delete cascade,
    added_at      timestamptz not null default now(),
    primary key (subscriber_id, book_id)
);

create index if not exists idx_subscriber_books_sub  on public.subscriber_books(subscriber_id);
create index if not exists idx_subscriber_books_book on public.subscriber_books(book_id);

-- ---------- ACTIVITY ----------
-- One row per send. rating/rated_at stay NULL for now.
create table if not exists public.activity (
    id            bigint generated always as identity primary key,
    subscriber_id bigint not null references public.subscribers(id) on delete cascade,
    insight_id    bigint not null references public.insights(id) on delete cascade,
    sent_at       timestamptz not null default now(),
    channel       text   not null default 'push' check (channel in ('push', 'manual')),
    rating        int    check (rating between 1 and 5),
    rated_at      timestamptz
);

create index if not exists idx_activity_insight    on public.activity(insight_id);
create index if not exists idx_activity_sent_at    on public.activity(sent_at desc);
create index if not exists idx_activity_subscriber on public.activity(subscriber_id, sent_at desc);
create index if not exists idx_insights_book       on public.insights(book_id);

-- ============================================================
-- Row Level Security
-- anon key (used in the public web page) may ONLY read.
-- The send/sync/generate scripts use the service_role key, which
-- bypasses RLS entirely, so they can still write.
-- ============================================================
alter table public.books           enable row level security;
alter table public.insights        enable row level security;
alter table public.activity        enable row level security;
alter table public.subscribers     enable row level security;
alter table public.subscriber_books enable row level security;

-- Drop-and-recreate so this file is safe to re-run.
drop policy if exists "anon read books"            on public.books;
drop policy if exists "anon read insights"         on public.insights;
drop policy if exists "anon read activity"         on public.activity;
drop policy if exists "anon read subscribers"      on public.subscribers;
drop policy if exists "anon read subscriber_books" on public.subscriber_books;

create policy "anon read books"            on public.books            for select to anon using (true);
create policy "anon read insights"         on public.insights         for select to anon using (true);
create policy "anon read activity"         on public.activity         for select to anon using (true);
create policy "anon read subscribers"      on public.subscribers      for select to anon using (true);
create policy "anon read subscriber_books" on public.subscriber_books for select to anon using (true);
-- No insert/update/delete policies for anon => writes are blocked for the web page.

-- Web (anon) smí ze subscribers číst jen bezpečné sloupce — NIKDY ntfy_topic.
revoke select on public.subscribers from anon;
grant  select (id, slug, name) on public.subscribers to anon;

-- ============================================================
-- Convenience view: POSLEDNÍ odeslaná myšlenka pro každého odběratele.
-- Web ji čte přes ?user=<slug>. Vystavuje slug, NE ntfy_topic.
-- ============================================================
create or replace view public.v_last_sent as
select distinct on (a.subscriber_id)
    a.subscriber_id,
    s.slug          as subscriber_slug,
    i.id            as insight_id,
    i.theme,
    i.body,
    i.verified,
    b.id            as book_id,
    b.title         as book_title,
    b.author        as book_author,
    a.sent_at
from public.activity a
join public.subscribers s on s.id = a.subscriber_id
join public.insights    i on i.id = a.insight_id
join public.books       b on b.id = i.book_id
order by a.subscriber_id, a.sent_at desc;

grant select on public.v_last_sent to anon;

-- ============================================================
-- Convenience view: NEPOSLANÉ myšlenky ZVLÁŠŤ pro každého odběratele.
-- Jen z knih v JEHO knihovně (subscriber_books), aktivní kniha i odběratel,
-- a co mu ještě neodešlo. send.py čte pohled filtrovaný přes subscriber_id.
-- NOTE: čte jen service_role (RLS bypassed); anon NEmá grant.
-- ============================================================
create or replace view public.v_unsent_insights as
select
    s.id       as subscriber_id,
    s.slug     as subscriber_slug,
    i.id       as insight_id,
    i.book_id,
    b.title    as book_title,
    b.author   as book_author,
    b.category as category,
    i.theme,
    i.body
from public.subscriber_books sb
join public.subscribers s on s.id = sb.subscriber_id
join public.books       b on b.id = sb.book_id
join public.insights    i on i.book_id = b.id
where s.active
  and b.active
  and not exists (
      select 1 from public.activity a
      where a.insight_id = i.id
        and a.subscriber_id = s.id
  );
