// Ranní moudra — čte myšlenky ze Supabase přes anon klíč (jen SELECT).
// ?id=<insight_id> ukáže konkrétní myšlenku; bez id poslední odeslanou.
// Tlačítko "Další moudro" zobrazí náhodnou další myšlenku (jen ke čtení).

(function () {
  const cfg = window.RM_CONFIG || {};
  const REST = `${cfg.SUPABASE_URL}/rest/v1`;
  const headers = {
    apikey: cfg.SUPABASE_ANON_KEY,
    Authorization: `Bearer ${cfg.SUPABASE_ANON_KEY}`,
  };

  const $ = (id) => document.getElementById(id);

  // Stav pro tlačítko "další": seznam všech id a co už jsme v této návštěvě viděli.
  let allIds = null;
  let currentId = null;
  const shown = new Set();

  function showStatus(msg) {
    $("status").textContent = msg;
    $("status").hidden = false;
    $("card").hidden = true;
    $("more").hidden = true;
  }

  function render(data) {
    currentId = data.insight_id;
    shown.add(data.insight_id);

    $("book-title").textContent = data.book_title;
    $("book-author").textContent = data.book_author;
    $("theme").textContent = data.theme;

    const bodyEl = $("body");
    bodyEl.innerHTML = "";
    data.body.split(/\n\s*\n/).forEach((para) => {
      const p = document.createElement("p");
      p.textContent = para.trim();
      bodyEl.appendChild(p);
    });

    $("verified").hidden = !data.verified;

    document.title = `${data.theme} — ${data.book_title}`;
    $("status").hidden = true;
    $("card").hidden = false;
    $("more").hidden = false;
    // Udrž URL v souladu, ať funguje obnovení stránky i sdílení.
    history.replaceState(null, "", `?id=${data.insight_id}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function fetchById(id) {
    const url =
      `${REST}/insights?select=id,theme,body,verified,books(title,author)` +
      `&id=eq.${encodeURIComponent(id)}&limit=1`;
    const rows = await (await fetch(url, { headers })).json();
    if (!rows.length) return null;
    const r = rows[0];
    return {
      insight_id: r.id,
      theme: r.theme,
      body: r.body,
      verified: r.verified,
      book_title: r.books.title,
      book_author: r.books.author,
    };
  }

  async function fetchLastSent() {
    const url = `${REST}/v_last_sent?select=*&limit=1`;
    const rows = await (await fetch(url, { headers })).json();
    return rows.length ? rows[0] : null;
  }

  async function ensureAllIds() {
    if (allIds) return allIds;
    const rows = await (await fetch(`${REST}/insights?select=id`, { headers })).json();
    allIds = rows.map((r) => r.id);
    return allIds;
  }

  async function showRandom() {
    const btn = $("more");
    btn.disabled = true;
    btn.textContent = "Načítám…";
    try {
      const ids = await ensureAllIds();
      // Přednostně to, co jsme dnes ještě neviděli; když dojdou, začni nanovo.
      let pool = ids.filter((id) => !shown.has(id));
      if (pool.length === 0) {
        shown.clear();
        pool = ids.filter((id) => id !== currentId);
      }
      if (pool.length === 0) return; // knihovna má jedinou myšlenku
      const id = pool[Math.floor(Math.random() * pool.length)];
      const data = await fetchById(id);
      if (data) render(data);
    } catch (err) {
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Další moudro →";
    }
  }

  async function main() {
    if (!cfg.SUPABASE_URL || cfg.SUPABASE_URL.includes("TVUJ-PROJEKT")) {
      showStatus("Nastav prosím Supabase údaje v docs/config.js.");
      return;
    }
    try {
      const id = new URLSearchParams(location.search).get("id");
      const data = id ? await fetchById(id) : await fetchLastSent();
      if (!data) {
        showStatus(id ? "Myšlenka nenalezena." : "Zatím nebyla odeslána žádná myšlenka.");
        return;
      }
      render(data);
    } catch (err) {
      console.error(err);
      showStatus("Něco se pokazilo při načítání. Zkus obnovit stránku.");
    }
  }

  $("more").addEventListener("click", showRandom);
  main();
})();
