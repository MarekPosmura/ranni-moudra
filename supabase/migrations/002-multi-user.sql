-- ============================================================
-- Ranní moudra — migrace v2: více uživatelů + vlastní knihovny
-- Spusť JEDNOU v Supabase Studio -> SQL Editor NAD existující databází.
-- Je bezpečné pustit vícekrát (idempotentní).
--
-- Model: každý odběratel má VLASTNÍ knihovnu (které knihy dostává).
--   * knihy i myšlenky se ukládají JEN JEDNOU a sdílí se,
--   * tabulka `subscriber_books` říká, kdo má kterou knihu ve své knihovně,
--   * kdo co dostane při odesílání se řídí členstvím, ne globální kategorií.
--
-- ⚠️  PO spuštění vyplň v tabulce `subscribers` skutečná ntfy témata
--     (sloupec ntfy_topic) — viz placeholdery ZMEN-ME-*.
--     Membership (subscriber_books) pak naplní `python scripts/sync_books.py`
--     podle sloupce "Komu" v knihy.xlsx.
-- ============================================================

-- ---------- SUBSCRIBERS ----------
create table if not exists public.subscribers (
    id          bigint generated always as identity primary key,
    slug        text        not null unique,   -- 'marek', 'zuzka' (do URL i kódu)
    name        text        not null,          -- zobrazované jméno
    ntfy_topic  text        not null,          -- vlastní ntfy téma (kam chodí push)
    active      boolean     not null default true,  -- false = dočasně vypnout posílání
    created_at  timestamptz not null default now()
);

insert into public.subscribers (slug, name, ntfy_topic) values
    ('marek', 'Marek', 'ZMEN-ME-marek-topic'),
    ('zuzka', 'Zuzka', 'ZMEN-ME-zuzka-topic')
on conflict (slug) do nothing;

-- ---------- SUBSCRIBER_BOOKS (vlastní knihovna) ----------
-- Kdo má kterou knihu ve své knihovně. Naplní sync_books.py z Excelu.
create table if not exists public.subscriber_books (
    subscriber_id bigint not null references public.subscribers(id) on delete cascade,
    book_id       bigint not null references public.books(id)       on delete cascade,
    added_at      timestamptz not null default now(),
    primary key (subscriber_id, book_id)
);

create index if not exists idx_subscriber_books_sub  on public.subscriber_books(subscriber_id);
create index if not exists idx_subscriber_books_book on public.subscriber_books(book_id);

-- ---------- ACTIVITY: komu odešlo ----------
alter table public.activity
    add column if not exists subscriber_id bigint references public.subscribers(id) on delete cascade;

-- Dosavadní záznamy (jednouživatelská éra) přiřaď hlavnímu uživateli (marek).
update public.activity
set subscriber_id = (select id from public.subscribers where slug = 'marek')
where subscriber_id is null;

create index if not exists idx_activity_subscriber
    on public.activity(subscriber_id, sent_at desc);

-- ---------- RLS ----------
-- Web (anon) smí ze subscribers číst jen bezpečné sloupce — NIKDY ntfy_topic.
alter table public.subscribers    enable row level security;
alter table public.subscriber_books enable row level security;

drop policy if exists "anon read subscribers"      on public.subscribers;
drop policy if exists "anon read subscriber_books" on public.subscriber_books;
create policy "anon read subscribers"      on public.subscribers      for select to anon using (true);
create policy "anon read subscriber_books" on public.subscriber_books for select to anon using (true);

revoke select on public.subscribers from anon;
grant  select (id, slug, name) on public.subscribers to anon;

-- ============================================================
-- Pohled: NEPOSLANÉ myšlenky ZVLÁŠŤ pro každého odběratele.
-- Jen z KNIH V JEHO KNIHOVNĚ (subscriber_books), aktivní kniha i odběratel,
-- a co mu ještě neodešlo. Čte jen service_role (anon NEmá grant).
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

-- ============================================================
-- Pohled: POSLEDNÍ odeslaná myšlenka pro každého odběratele.
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
