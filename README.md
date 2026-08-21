# 📖 Ranní moudra

Osobní appka pro jednoho člověka: 2× denně (v **6:00** a **16:00**, Europe/Prague)
přijde na Android **tichá push notifikace** s destilovanou myšlenkou z knihy.
Klepnutím se otevře tvoje vlastní stránka s plným textem té myšlenky.

Vše běží **zdarma**: Supabase (databáze) + ntfy (push) + GitHub Actions (plánovač) + GitHub Pages (stránka).

---

## Jak to funguje (v kostce)

```
GitHub Actions (cron, UTC)
        │  2× denně spustí…
        ▼
   scripts/send.py  ──►  vybere neposlanou myšlenku ze Supabase
        │                 (náhodně, ne stejná kniha 2× po sobě)
        │                 zapíše řádek do tabulky `activity`
        ▼
     ntfy.sh  ──►  📱 tichá notifikace na Android (bez zvuku/vibrace)
        │  proklik…
        ▼
  GitHub Pages (docs/) ──► zobrazí myšlenku ze Supabase (jen ke čtení)
```

- **Databáze (Supabase)** je jediný zdroj pravdy: knihy, myšlenky, historie odeslání.
- **Odesílací skript** čte přes tajný `service_role` klíč (smí i zapisovat).
- **Stránka** čte přes veřejný `anon` klíč, který díky Row Level Security **umí jen číst**.

---

## Struktura repozitáře

```
ranni-moudra/
├─ supabase/
│  ├─ schema.sql            # tabulky, RLS, pohledy — spustíš v Supabase jednou
│  └─ migrations/           # dodatečné migrace (např. více uživatelů)
├─ knihy.xlsx              # Excel „ovladač knih“ — JEDINÝ zdroj pravdy (knihy + Komu)
├─ scripts/
│  ├─ send.py               # vybere + zapíše + pošle notifikaci (cron i ručně)
│  ├─ sync_books.py         # načte knihy.xlsx → metadata + knihovny + dogeneruje nové knihy
│  ├─ generate.py           # generátor jedné knihy přes Claude API
│  └─ lib/{config,db}.py    # config z env + tenký Supabase klient
├─ docs/                    # webová stránka (GitHub Pages)
│  ├─ index.html  style.css  app.js  config.js
├─ .github/workflows/send.yml   # cron plánovač
├─ requirements.txt
├─ .env.example
└─ README.md
```

---

## Zprovoznění krok za krokem

Postupuj v tomto pořadí. Odhad: ~30 minut.

### 1) Supabase — databáze

1. Založ účet na <https://supabase.com> a vytvoř **nový projekt** (region klidně Frankfurt).
   Zapamatuj si databázové heslo (nebudeš ho ale k tomuhle potřebovat).
2. V projektu otevři **SQL Editor** → **New query**, vlož celý obsah
   [`supabase/schema.sql`](supabase/schema.sql) a klikni **Run**.
   Tím vzniknou tabulky `books`, `insights`, `activity`, zapne se RLS a vytvoří se pohledy.
3. Otevři **Project Settings → API** a poznamenej si:
   - **Project URL** → to je `SUPABASE_URL`
   - **anon public** klíč → `SUPABASE_ANON_KEY` (půjde do stránky, je to OK)
   - **service_role** klíč → `SUPABASE_SERVICE_KEY` (**TAJNÝ**, jen do skriptů/Secrets)

### 2) Lokální nastavení (Windows) + naplnění knihovny

1. Nainstaluj Python 3.11+ (`python --version`).
2. V kořeni projektu:
   ```bash
   pip install -r requirements.txt
   ```
3. Zkopíruj `.env.example` na `.env` a vyplň (aspoň Supabase část):
   ```bash
   copy .env.example .env
   ```
   Vyplň `SUPABASE_URL` a `SUPABASE_SERVICE_KEY`.
4. Naplň knihovnu ze souboru `knihy.xlsx` (přidá metadata, knihovny a u nových
   knih dogeneruje myšlenky přes Claude — potřebuje `ANTHROPIC_API_KEY`):
   ```bash
   python scripts/sync_books.py --dry-run   # náhled, nic nezapíše
   python scripts/sync_books.py             # ostrý běh
   ```
   Skript je bezpečné pouštět opakovaně — existující knihy se nepřegenerují.

### 3) ntfy — push na Android

1. Vymysli **neuhodnutelný název tématu**, např. `rm-a7f3k9zq-moudra`
   (veřejný server ntfy.sh = kdo zná téma, čte i publikuje — proto ať je náhodné).
2. Zapiš ho do `.env` jako `NTFY_TOPIC`.
3. Na telefonu nainstaluj appku **ntfy** (Google Play nebo F-Droid), dej **+**,
   zadej **přesně stejný název tématu** a přidej odběr.
4. Tichá notifikace: skript posílá s prioritou „low“ (bez zvuku i vibrace).
   V appce ntfy navíc můžeš u tématu ztlumit kanál úplně, kdyby něco pípalo.

### 4) GitHub — repo, stránka, plánovač

1. Vytvoř na GitHubu **veřejný** repozitář (GitHub Pages zdarma vyžadují veřejný repo)
   a nahraj do něj tento projekt.
2. **GitHub Pages:** Repo → **Settings → Pages** → *Source: Deploy from a branch* →
   větev `main`, složka `/docs` → **Save**.
   Za chvíli poběží na `https://<tvůj-username>.github.io/<repo>`.
   To je tvoje `SITE_BASE_URL`.
3. Vyplň [`docs/config.js`](docs/config.js): `SUPABASE_URL` a `SUPABASE_ANON_KEY`
   (ten **anon**, ne service_role!) a změnu commitni.
4. **GitHub Secrets:** Repo → **Settings → Secrets and variables → Actions → New repository secret**.
   Přidej tyto (názvy přesně takto):

   | Secret | Hodnota |
   |---|---|
   | `SUPABASE_URL` | Project URL ze Supabase |
   | `SUPABASE_SERVICE_KEY` | **service_role** klíč (tajný) |
   | `NTFY_TOPIC` | tvůj náhodný název tématu |
   | `NTFY_SERVER` | `https://ntfy.sh` (volitelné) |
   | `SITE_BASE_URL` | `https://<username>.github.io/<repo>` (bez lomítka na konci) |

5. **Test běhu:** Repo → **Actions** → workflow *Ranní moudra – push* →
   **Run workflow** (tlačítko `workflow_dispatch`). Za chvíli ti má přijít notifikace.
   *(Pozn.: při ručním spuštění mimo časové okno skript nic nepošle — na test použij
   raději lokální `python scripts/send.py --force`, viz níže.)*

Hotovo. Od teď chodí myšlenky samy 2× denně.

---

## Ruční spuštění a testování (Windows)

- **Poslat teď hned na test** (ignoruje časové okno, zapíše se jako `channel='manual'`):
  ```bash
  python scripts/send.py --force
  ```
- **Normální běh** (pošle jen v ranním/odpoledním okně, jinak tiše skončí):
  ```bash
  python scripts/send.py
  ```

---

## Stránka: čtení a tlačítko „Další moudro“

- Notifikace 2× denně otevře myšlenku dne. Na stránce je pod ní tlačítko **„Další moudro →“**,
  které načte náhodnou další myšlenku z knihovny — takže si ráno můžeš přečíst klidně 2–3.
- Tlačítko je **jen ke čtení** (stránka má read-only anon klíč). Přečtená myšlenka se
  *neoznačuje jako odeslaná*, takže se může někdy objevit i v pozdější notifikaci — u osobní
  appky neškodí. Plná verze (co si pamatuje přečtené + hodnocení + vážený výběr) je **v2**.
- **Kolik myšlenek vydrží:** 2 zprávy denně = 2 myšlenky. Startovních 50 (5 knih × 10) vystačí
  ~25 dní; každá další vygenerovaná kniha přidá ~12 (~6 dní). Až se každá jednou pošle, v1
  přestane mít co posílat (zapíše to do logu) — přidej knihy, nebo počkej na v2 (opakování oblíbených).

---

## Přidání další knihy (generátor)

Potřebuje `ANTHROPIC_API_KEY` v `.env`. Máš dvě cesty:

### A) Nejjednodušší — Excel [`knihy.xlsx`](knihy.xlsx)

Otevři [`knihy.xlsx`](knihy.xlsx) (list **Knihy**), dopiš řádek — povinné jsou jen **Název** a **Autor**,
zbytek (Rok, Kategorie, Posílat, Ověřeno, Počet myšlenek, Poznámka, **Komu**) je volitelný.
Sloupec **Komu** říká, do čí knihovny kniha patří: `marek`, `zuzka`, nebo `oba` (prázdné = `marek`).
Ulož a spusť:

```bash
python scripts/sync_books.py
```

Co skript udělá:
- **novou** knihu vygeneruje přes Claude a nahraje do Supabase (`Počet myšlenek` řádků),
- u **existující** knihy aktualizuje metadata (autor, rok, kategorie, **Posílat**, poznámka) — negeneruje znovu,
- nastaví **knihovny** (tabulku `subscriber_books`) podle sloupce **Komu** (přidá i odebere),
- řádek, jehož **Název** začíná `#`, přeskočí (poznámka/příklad).

Je bezpečné ho pouštět opakovaně. Náhled bez zápisu: `python scripts/sync_books.py --dry-run`.

> **Posílat = 0** knihu vyřadí z automatických zpráv. Totéž jde přepnout i **z mobilu**:
> Supabase → Table Editor → tabulka `books` → sloupec `active`.

### B) Jedna kniha přímo z příkazu

```bash
# napřed si zkontroluj, co vygeneruje, bez nahrání:
python scripts/generate.py --book "Proč spíme" --author "Matthew Walker" --dry-run

# když jsi spokojený, nahraj:
python scripts/generate.py --book "Proč spíme" --author "Matthew Walker" --count 12
```

### Ruční úprava textů

Vygenerované myšlenky žijí v Supabase v tabulce `insights` (to je živý katalog).
Když chceš konkrétní text opravit ručně, edituj ho přímo v **Supabase → Table Editor →
`insights`** (sloupec `body`). Žádný seed soubor už neudržujeme — jediný zdroj knih
je `knihy.xlsx`, texty vznikají generátorem a dál žijí v databázi.

Chceš-li knize myšlenky vygenerovat úplně znovu (třeba po změně stylu), smaž její
řádky v `insights` a spusť `sync_books.py` (kniha bez myšlenek se dogeneruje).

- U **novějších knih** si napřed sám ověř jádro myšlenky (web) a přidej `--verified`
  (na stránce se pak ukáže „✓ jádro ověřeno“).
- Skript nikdy neukládá doslovné citace ani vymyšlená čísla stránek — je tak instruovaný.
- Do budoucna počítáme s 20–30 knihami včetně tématu **fyzického a psychického zdraví** —
  stačí generátor spouštět pro další tituly.

---

## Úprava časů

Časy jsou v [`.github/workflows/send.yml`](.github/workflows/send.yml) v **UTC** a řídí je
`SLOTS` v [`scripts/send.py`](scripts/send.py) (v pražském čase).

- Cíle jsou **6:00** a **16:00** Praha. Kvůli letnímu/zimnímu času workflow spouští
  oba posuny (4/5 a 14/15 UTC) a `send.py` pošle jen ve správném okně —
  **funguje automaticky celý rok**, nemusíš na jaře/podzim nic přepínat.
- Chceš jiný čas? Uprav `target` a `window` ve `SLOTS` **a** odpovídající `cron` řádky v `send.yml`
  (nezapomeň, že cron je v UTC: pražská hodina −1 v zimě, −2 v létě).
- GitHub cron **není minutově přesný** a občas se o pár minut zpozdí — okno v `send.py`
  má proto rezervu (ráno 6–10 h, odpoledne 16–20 h), takže zpoždění nevadí.

---

## Bezpečnost a free tier

- **`service_role` a `ANTHROPIC_API_KEY` nikdy** nedávej do `docs/` ani do repa —
  jen do `.env` (lokálně, je v `.gitignore`) a do **GitHub Secrets**.
- **`anon` klíč** ve stránce je v pořádku: RLS povoluje přes něj **jen čtení** (SELECT).
- **ntfy** téma je veřejné — proto náhodný název a v notifikaci nic citlivého.
- **Free tier bez obav:** jeden uživatel, 2 běhy denně. Supabase free (0,5 GB DB, egress),
  GitHub Actions (2000 min/měsíc — spotřebuješ jednotky minut), ntfy i Pages jsou zdarma.
  Supabase free projekt se uspává po ~7 dnech nečinnosti — tvoje denní běhy ho drží živý.

---

## Databázové schéma (přehled)

| Tabulka | K čemu |
|---|---|
| `books` | id, title, author, `active`, added_at |
| `insights` | id, book_id→books, theme, body, `verified`, lang, created_at |
| `activity` | id, insight_id→insights, sent_at, channel (`push`/`manual`), `rating` (v2), `rated_at` (v2) |

Pohledy: `v_unsent_insights` (neposlané myšlenky pro výběr), `v_last_sent` (poslední odeslaná — pro stránku bez `?id=`).

**Připraveno na v2** (teď nestavíme, ale schéma to unese bez přestavby):
hvězdičkové hodnocení (`activity.rating`), tlačítko „další moudro“ a vážený výběr
(nikdy neposílat 1★, občas zopakovat 5★ po prodlevě).
