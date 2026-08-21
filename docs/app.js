// Ranní moudra — čte myšlenky ze Supabase přes anon klíč (jen SELECT).
// Routování přes query parametry:
//   ?id=<insight_id>   → jedno moudro (s listováním v rámci knihy)
//   ?book=<book_id>    → seznam mouder z jedné knihy
//   ?view=catalog      → seznam všech knih
//   ?user=<slug>       → poslední moudro daného odběratele (marek / zuzka)
//   (bez parametru)    → poslední odeslané moudro (globálně nejnovější)

(function () {
  const cfg = window.RM_CONFIG || {};
  const REST = `${cfg.SUPABASE_URL}/rest/v1`;
  const headers = {
    apikey: cfg.SUPABASE_ANON_KEY,
    Authorization: `Bearer ${cfg.SUPABASE_ANON_KEY}`,
  };

  const $ = (id) => document.getElementById(id);
  const api = async (path) => (await fetch(`${REST}/${path}`, { headers })).json();

  let allIds = null;          // pro náhodné moudro
  let currentId = null;
  const shown = new Set();
  const bookNavCache = {};    // book_id -> [insight_id, …] (seřazené)
  let prevId = null, nextId = null;

  // ---------- přepínání pohledů ----------
  function show(which) {
    $("card").hidden = which !== "card";
    $("list").hidden = which !== "list";
    $("more").hidden = which !== "card";
    $("pager").hidden = which !== "card";
    $("status").hidden = which !== "status";
  }
  function showStatus(msg) { $("status").textContent = msg; show("status"); }

  // ---------- jedno moudro ----------
  function renderCard(data) {
    currentId = data.insight_id;
    shown.add(data.insight_id);

    $("book-title").textContent = data.book_title;
    $("book-author").textContent = data.book_author;
    $("book-link").setAttribute("href", data.book_id ? `?book=${data.book_id}` : "?");
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
    updatePager(data.book_id, data.insight_id);
  }

  // Listování v rámci knihy: počítadlo + šipky předchozí/další.
  async function updatePager(bookId, id) {
    prevId = nextId = null;
    if (!bookId) { $("pager").hidden = true; return; }
    try {
      let ids = bookNavCache[bookId];
      if (!ids) {
        const rows = await api(`insights?select=id&book_id=eq.${encodeURIComponent(bookId)}&order=id.asc`);
        ids = rows.map((r) => r.id);
        bookNavCache[bookId] = ids;
      }
      if (currentId !== id) return; // uživatel už přešel jinam
      const idx = ids.indexOf(id);
      if (idx === -1) { $("pager").hidden = true; return; }
      prevId = idx > 0 ? ids[idx - 1] : null;
      nextId = idx < ids.length - 1 ? ids[idx + 1] : null;
      $("counter").textContent = `moudro ${idx + 1} / ${ids.length}`;
      $("prev").disabled = prevId === null;
      $("next").disabled = nextId === null;
      $("pager").hidden = false;
    } catch (err) {
      console.error(err);
      $("pager").hidden = true;
    }
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
  const mapInsight = (r) => ({
    insight_id: r.id, theme: r.theme, body: r.body, verified: r.verified,
    book_id: r.books.id, book_title: r.books.title, book_author: r.books.author,
  });

  async function fetchById(id) {
    const rows = await api(
      `insights?select=id,theme,body,verified,books(id,title,author)&id=eq.${encodeURIComponent(id)}&limit=1`
    );
    return rows.length ? mapInsight(rows[0]) : null;
  }

  async function ensureAllIds() {
    if (allIds) return allIds;
    allIds = (await api(`insights?select=id`)).map((r) => r.id);
    return allIds;
  }

  async function showRandom() {
    const btn = $("more");
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = "Načítám…";
    try {
      const ids = await ensureAllIds();
      let pool = ids.filter((i) => !shown.has(i));
      if (pool.length === 0) { shown.clear(); pool = ids.filter((i) => i !== currentId); }
      if (pool.length === 0) return;
      const id = pool[Math.floor(Math.random() * pool.length)];
      const data = await fetchById(id);
      if (data) { history.pushState(null, "", `?id=${id}`); renderCard(data); }
    } catch (err) {
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = label;
    }
  }

  function goTo(id) {
    if (id == null) return;
    history.pushState(null, "", `?id=${id}`);
    route();
  }

  // ---------- pohledy ----------
  async function viewInsight(id) {
    const data = await fetchById(id);
    if (!data) { showStatus("Myšlenka nenalezena."); return; }
    renderCard(data);
  }

  async function viewCatalog() {
    const books = await api(`books?select=id,title,author&order=title.asc`);
    if (!books.length) { showStatus("Katalog je zatím prázdný."); return; }
    renderList({
      title: "📖 Katalog", sub: `${books.length} knih`, backHref: null,
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
    bookNavCache[b.id] = insights.map((i) => i.id);
    renderList({
      title: b.title, sub: `${b.author} · ${insights.length} mouder`, backHref: "?view=catalog",
      items: insights.map((i) => ({ href: `?id=${i.id}`, main: i.theme })),
    });
  }

  // Poslední odeslané moudro. S ?user=<slug> pro konkrétního člověka,
  // bez něj to globálně nejnovější napříč odběrateli.
  async function viewLast(userSlug) {
    const filter = userSlug
      ? `subscriber_slug=eq.${encodeURIComponent(userSlug)}&limit=1`
      : `order=sent_at.desc&limit=1`;
    const rows = await api(`v_last_sent?select=insight_id&${filter}`);
    if (!rows.length) { showStatus("Zatím nebyla odeslána žádná myšlenka. Otevři si nahoře Katalog."); return; }
    await viewInsight(rows[0].insight_id);
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
      return await viewLast(p.get("user"));
    } catch (err) {
      console.error(err);
      showStatus("Něco se pokazilo při načítání. Zkus obnovit stránku.");
    }
  }

  // Interní odkazy (?...) přepínají bez reloadu.
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="?"], a#list-back');
    if (!a) return;
    e.preventDefault();
    if (a.id === "list-back" && a.getAttribute("href") === "#") { history.back(); return; }
    history.pushState(null, "", a.getAttribute("href"));
    route();
  });

  // Klávesnice: šipky listují v rámci knihy (jen na kartě moudra).
  document.addEventListener("keydown", (e) => {
    if ($("card").hidden) return;
    if (e.key === "ArrowLeft" && prevId != null) { e.preventDefault(); goTo(prevId); }
    if (e.key === "ArrowRight" && nextId != null) { e.preventDefault(); goTo(nextId); }
  });

  window.addEventListener("popstate", route);
  $("more").addEventListener("click", showRandom);
  $("prev").addEventListener("click", () => goTo(prevId));
  $("next").addEventListener("click", () => goTo(nextId));
  route();
})();
