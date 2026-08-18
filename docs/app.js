// Ranní moudra — čte myšlenky ze Supabase přes anon klíč (jen SELECT).
// Routování přes query parametry:
//   ?id=<insight_id>   → jedno moudro
//   ?book=<book_id>    → seznam mouder z jedné knihy
//   ?view=catalog      → seznam všech knih
//   (bez parametru)    → poslední odeslané moudro
// Tlačítko "Další moudro" zobrazí náhodné další moudro.

(function () {
  const cfg = window.RM_CONFIG || {};
  const REST = `${cfg.SUPABASE_URL}/rest/v1`;
  const headers = {
    apikey: cfg.SUPABASE_ANON_KEY,
    Authorization: `Bearer ${cfg.SUPABASE_ANON_KEY}`,
  };

  const $ = (id) => document.getElementById(id);
  const api = async (path) => (await fetch(`${REST}/${path}`, { headers })).json();

  // Stav pro tlačítko "další": seznam všech id a co už jsme v této návštěvě viděli.
  let allIds = null;
  let currentId = null;
  const shown = new Set();

  // ---------- přepínání pohledů ----------
  function show(which) {
    $("card").hidden = which !== "card";
    $("list").hidden = which !== "list";
    $("more").hidden = which !== "card";
    $("status").hidden = which !== "status";
  }

  function showStatus(msg) {
    $("status").textContent = msg;
    show("status");
  }

  // ---------- jedno moudro ----------
  function renderCard(data) {
    currentId = data.insight_id;
    shown.add(data.insight_id);

    $("book-title").textContent = data.book_title;
    $("book-author").textContent = data.book_author;
    $("book-link").setAttribute("href", `?book=${data.book_id}`);
    $("theme").textContent = data.theme;

    const bodyEl = $("body");
    bodyEl.innerHTML = "";
    data.body.split(/\n\s*\n/).forEach((para) => {
      const text = para.trim();
      const summary = text.match(/^Ve zkratce:\s*(.*)$/s);
      if (summary) {
        const p = document.createElement("p");
        p.className = "summary";
        const label = document.createElement("strong");
        label.textContent = "Ve zkratce: ";
        p.appendChild(label);
        p.appendChild(document.createTextNode(summary[1]));
        bodyEl.appendChild(p);
      } else {
        const p = document.createElement("p");
        p.textContent = text;
        bodyEl.appendChild(p);
      }
    });

    $("verified").hidden = !data.verified;
    document.title = `${data.theme} — ${data.book_title}`;
    show("card");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---------- seznamy (katalog / kniha) ----------
  function renderList({ title, sub, backHref, items }) {
    $("list-title").textContent = title;
    const subEl = $("list-sub");
    if (sub) { subEl.textContent = sub; subEl.hidden = false; } else { subEl.hidden = true; }

    const back = $("list-back");
    if (backHref) { back.setAttribute("href", backHref); back.hidden = false; } else { back.hidden = true; }

    const wrap = $("list-items");
    wrap.innerHTML = "";
    items.forEach((it) => {
      const a = document.createElement("a");
      a.className = "list-item";
      a.setAttribute("href", it.href);
      const main = document.createElement("span");
      main.className = "li-main";
      main.textContent = it.main;
      a.appendChild(main);
      if (it.sub) {
        const s = document.createElement("span");
        s.className = "li-sub";
        s.textContent = it.sub;
        a.appendChild(s);
      }
      wrap.appendChild(a);
    });

    document.title = title;
    show("list");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---------- data ----------
  function mapInsight(r) {
    return {
      insight_id: r.id,
      theme: r.theme,
      body: r.body,
      verified: r.verified,
      book_id: r.books.id,
      book_title: r.books.title,
      book_author: r.books.author,
    };
  }

  async function fetchById(id) {
    const rows = await api(
      `insights?select=id,theme,body,verified,books(id,title,author)&id=eq.${encodeURIComponent(id)}&limit=1`
    );
    return rows.length ? mapInsight(rows[0]) : null;
  }

  async function fetchLastSent() {
    const rows = await api(`v_last_sent?select=*&limit=1`);
    if (!rows.length) return null;
    const r = rows[0];
    return {
      insight_id: r.insight_id, theme: r.theme, body: r.body, verified: r.verified,
      book_id: r.book_id ?? null, book_title: r.book_title, book_author: r.book_author,
    };
  }

  async function ensureAllIds() {
    if (allIds) return allIds;
    const rows = await api(`insights?select=id`);
    allIds = rows.map((r) => r.id);
    return allIds;
  }

  async function showRandom() {
    const btn = $("more");
    btn.disabled = true;
    btn.textContent = "Načítám…";
    try {
      const ids = await ensureAllIds();
      let pool = ids.filter((id) => !shown.has(id));
      if (pool.length === 0) { shown.clear(); pool = ids.filter((id) => id !== currentId); }
      if (pool.length === 0) return;
      const id = pool[Math.floor(Math.random() * pool.length)];
      const data = await fetchById(id);
      if (data) { history.pushState(null, "", `?id=${id}`); renderCard(data); }
    } catch (err) {
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Další moudro →";
    }
  }

  // ---------- pohledy katalogu ----------
  async function viewCatalog() {
    const books = await api(`books?select=id,title,author&order=title.asc`);
    if (!books.length) { showStatus("Katalog je zatím prázdný."); return; }
    renderList({
      title: "📖 Katalog",
      sub: `${books.length} knih`,
      backHref: null,
      items: books.map((b) => ({ href: `?book=${b.id}`, main: b.title, sub: b.author })),
    });
  }

  async function viewBook(bookId) {
    const [books, insights] = await Promise.all([
      api(`books?select=id,title,author&id=eq.${encodeURIComponent(bookId)}&limit=1`),
      api(`insights?select=id,theme&book_id=eq.${encodeURIComponent(bookId)}&order=id.asc`),
    ]);
    if (!books.length) { showStatus("Kniha nenalezena."); return; }
    const b = books[0];
    renderList({
      title: b.title,
      sub: `${b.author} · ${insights.length} mouder`,
      backHref: "?view=catalog",
      items: insights.map((i) => ({ href: `?id=${i.id}`, main: i.theme })),
    });
  }

  async function viewInsight(id) {
    const data = await fetchById(id);
    if (!data) { showStatus("Myšlenka nenalezena."); return; }
    renderCard(data);
  }

  async function viewLast() {
    const data = await fetchLastSent();
    if (!data) { showStatus("Zatím nebyla odeslána žádná myšlenka. Otevři si Katalog nahoře."); return; }
    renderCard(data);
  }

  // ---------- router ----------
  async function route() {
    if (!cfg.SUPABASE_URL || cfg.SUPABASE_URL.includes("TVUJ-PROJEKT")) {
      showStatus("Nastav prosím Supabase údaje v docs/config.js.");
      return;
    }
    const p = new URLSearchParams(location.search);
    try {
      if (p.get("id")) return await viewInsight(p.get("id"));
      if (p.get("book")) return await viewBook(p.get("book"));
      if (p.get("view") === "catalog") return await viewCatalog();
      return await viewLast();
    } catch (err) {
      console.error(err);
      showStatus("Něco se pokazilo při načítání. Zkus obnovit stránku.");
    }
  }

  // Odchyť kliknutí na interní odkazy (?...) a přepni bez reloadu.
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="?"], a#list-back');
    if (!a) return;
    e.preventDefault();
    if (a.id === "list-back" && a.getAttribute("href") === "#") { history.back(); return; }
    history.pushState(null, "", a.getAttribute("href"));
    route();
  });

  window.addEventListener("popstate", route);
  $("more").addEventListener("click", showRandom);
  route();
})();
