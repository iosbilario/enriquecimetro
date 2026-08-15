/* Enriquecímetro — página inicial: rankings, busca e filtros client-side. */
"use strict";

(() => {
  const { money, moneyCompact, pct, normalize, titleCase, fetchJSON, inflate, debounce, el, fmtDate, avatar } = ENR;

  const state = {
    all: null,          // índice completo (lazy)
    rankings: null,
    meta: null,
    sort: "top_increase_abs",
    query: "",
    uf: "",
    office: "",
    party: "",
    range: "",
    shown: 24,
  };

  const $ = (sel) => document.querySelector(sel);

  const RANGES = {
    "ate-100k": [0, 100_000],
    "100k-1m": [100_000, 1_000_000],
    "1m-10m": [1_000_000, 10_000_000],
    "acima-10m": [10_000_000, Infinity],
  };

  /* ---------- URL <-> estado (compartilhamento de filtros) ---------- */
  function readURL() {
    const p = new URLSearchParams(location.search);
    state.query = p.get("q") || "";
    state.uf = p.get("uf") || "";
    state.office = p.get("cargo") || "";
    state.party = p.get("partido") || "";
    state.range = p.get("faixa") || "";
    state.sort = p.get("ordem") || state.sort;
  }
  function writeURL() {
    const p = new URLSearchParams();
    if (state.query) p.set("q", state.query);
    if (state.uf) p.set("uf", state.uf);
    if (state.office) p.set("cargo", state.office);
    if (state.party) p.set("partido", state.party);
    if (state.range) p.set("faixa", state.range);
    if (state.sort !== "top_increase_abs") p.set("ordem", state.sort);
    const qs = p.toString();
    history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
  }

  const hasActiveFilter = () =>
    state.query || state.uf || state.office || state.party || state.range;

  async function ensureIndex() {
    if (state.all) return state.all;
    const doc = await fetchJSON("public/data/search-index.json");
    state.all = inflate(doc);
    return state.all;
  }

  /* Opções vêm do meta.json (leve), preenchidas já na inicialização —
     o índice de busca (pesado) segue carregando só sob demanda. */
  function fillFilterOptions(filters) {
    const ufs = filters?.uf || [];
    const parties = filters?.party || [];
    const offices = filters?.office || [];
    const fill = (sel, values, current, fmt = (v) => v) => {
      const node = $(sel);
      const keep = node.firstElementChild;
      node.innerHTML = "";
      node.append(keep);
      values.forEach((v) => node.append(el("option", { value: v }, fmt(v))));
      node.value = current || "";
    };
    fill("#f-uf", ufs, state.uf);           // siglas ficam como estão
    fill("#f-party", parties, state.party); // siglas ficam como estão
    fill("#f-office", offices, state.office, titleCase);
  }

  /* ---------- renderização ---------- */
  function card(item) {
    const dir = (item.change_abs ?? 0) >= 0 ? "up" : "down";
    const arrowSym = (item.change_abs ?? 0) >= 0 ? "▲" : "▼";
    const hasBoth = item.a2022 !== null && item.a2026 !== null;
    const pctText =
      item.change_pct !== null && item.change_pct !== undefined
        ? pct(item.change_pct)
        : hasBoth && item.a2022 === 0
          ? "Não aplicável — patrimônio anterior declarado como R$ 0"
          : null;

    return el(
      "li",
      { class: "card" },
      el(
        "div",
        { class: "who" },
        avatar(item, { hasPhoto: hasBoth }),
        el(
          "div",
          { class: "who-text" },
          el("h3", { class: "name" }, titleCase(item.ballot_name || item.name)),
          el(
            "p",
            { class: "meta" },
            item.party || "—",
            el("span", { class: "sep", "aria-hidden": "true" }, "·"),
            item.uf || "—",
            el("span", { class: "sep", "aria-hidden": "true" }, "·"),
            titleCase(item.office || "")
          )
        )
      ),
      el(
        "div",
        { class: "flow", role: "group", "aria-label": "Patrimônio declarado por eleição" },
        el("div", { class: "col" },
          el("div", { class: "yr" }, "2022"),
          el("div", { class: "val" }, moneyCompact(item.a2022))),
        el("span", { class: "arrow", "aria-hidden": "true" }, "→"),
        el("div", { class: "col" },
          el("div", { class: "yr" }, "2026"),
          el("div", { class: "val" }, moneyCompact(item.a2026)))
      ),
      hasBoth
        ? el(
            "div",
            { class: `delta ${dir}` },
            el("span", { class: "abs" }, `${arrowSym} ${moneyCompact(Math.abs(item.change_abs))}`),
            pctText ? el("span", { class: "pct" }, pctText) : null
          )
        : el("div", { class: "delta" },
            el("span", { class: "pct" },
              item.a2026 === null ? "Sem candidatura registrada em 2026" : "Sem declaração localizada em 2022")),
      item.outlier
        ? el("span", { class: "badge outlier", title: "Variação percentual acima de Q3 + 3×IQR do conjunto analisado. Indicador estatístico descritivo — ver metodologia." }, "variação atípica no conjunto")
        : item.status && item.status !== "exact" && hasBoth
          ? el("span", { class: "badge" }, "correspondência provável")
          : null,
      el("a", { class: "cta", href: `candidate.html?id=${item.id}` }, "Ver evolução patrimonial")
    );
  }

  function applyFilters(items) {
    const q = normalize(state.query);
    return items.filter((i) => {
      if (state.uf && i.uf !== state.uf) return false;
      if (state.office && i.office !== state.office) return false;
      if (state.party && i.party !== state.party) return false;
      if (state.range) {
        const [lo, hi] = RANGES[state.range] || [0, Infinity];
        const v = i.a2026 ?? i.a2022;
        if (v === null || v < lo || v >= hi) return false;
      }
      if (q) {
        const hay = `${normalize(i.name)} ${normalize(i.ballot_name)} ${normalize(i.party)}`;
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function sortItems(items) {
    const key = {
      top_increase_abs: (a, b) => (b.change_abs ?? -Infinity) - (a.change_abs ?? -Infinity),
      top_increase_pct: (a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity),
      top_assets: (a, b) => (b.a2026 ?? -Infinity) - (a.a2026 ?? -Infinity),
      top_decrease_abs: (a, b) => (a.change_abs ?? Infinity) - (b.change_abs ?? Infinity),
      top_multiple: (a, b) => (b.multiple ?? -Infinity) - (a.multiple ?? -Infinity),
      name: (a, b) => (a.name || "").localeCompare(b.name || "", "pt-BR"),
    }[state.sort];
    return key ? [...items].sort(key) : items;
  }

  async function render() {
    const listNode = $("#results");
    const statusNode = $("#result-status");
    listNode.setAttribute("aria-busy", "true");

    let items;
    let usingRanking = false;
    if (!hasActiveFilter() && state.rankings?.rankings?.[state.sort]) {
      items = state.rankings.rankings[state.sort].entries;
      usingRanking = true;
    } else {
      const all = await ensureIndex();
      items = sortItems(applyFilters(all));
      if (state.sort !== "name" && !state.query) {
        // ordenar por variação exige ambos os lados; sem eles, joga pro fim
        items = items.filter((i) => state.sort === "top_assets" ? i.a2026 !== null : true);
      }
    }

    listNode.innerHTML = "";
    const slice = items.slice(0, state.shown);
    slice.forEach((i) => listNode.append(card(i)));

    statusNode.textContent = items.length
      ? usingRanking
        ? `Top ${slice.length} — somente candidaturas com correspondência exata entre 2022 e 2026.`
        : `${items.length.toLocaleString("pt-BR")} candidatura(s) encontradas — exibindo ${slice.length}.`
      : "";
    $("#empty").hidden = items.length > 0;
    $("#more").hidden = items.length <= state.shown;
    listNode.setAttribute("aria-busy", "false");
  }

  const rerender = () => { state.shown = 24; writeURL(); render(); };

  async function init() {
    readURL();

    const [rankings, meta] = await Promise.all([
      fetchJSON("public/data/rankings.json"),
      fetchJSON("public/data/meta.json"),
    ]);
    state.rankings = rankings;
    state.meta = meta;

    $("#updated-at").textContent =
      `Dados do TSE processados em ${fmtDate(meta.generated_at)} · ` +
      `${(meta.candidate_count?.["2026"] ?? 0).toLocaleString("pt-BR")} candidaturas em 2026`;

    fillFilterOptions(meta.filters);

    const search = $("#search");
    search.value = state.query;
    search.addEventListener("focus", () => { ensureIndex(); }, { once: true });
    search.addEventListener("input", debounce(() => {
      state.query = search.value;
      rerender();
    }, 220));

    const bind = (sel, prop) => {
      $(sel).addEventListener("change", (e) => {
        state[prop] = e.target.value;
        rerender();
      });
    };
    bind("#f-uf", "uf");
    bind("#f-office", "office");
    bind("#f-party", "party");
    bind("#f-range", "range");
    $("#f-range").value = state.range;

    $("#sort").value = state.sort;
    $("#sort").addEventListener("change", (e) => {
      state.sort = e.target.value;
      rerender();
    });

    $("#clear").addEventListener("click", () => {
      state.query = state.uf = state.office = state.party = state.range = "";
      search.value = "";
      ["#f-uf", "#f-office", "#f-party", "#f-range"].forEach((s) => ($(s).value = ""));
      rerender();
    });

    $("#more-btn").addEventListener("click", () => {
      state.shown += 24;
      render();
    });

    if (hasActiveFilter()) await ensureIndex();
    await render();
  }

  init().catch((err) => {
    $("#result-status").textContent =
      "Não foi possível carregar os dados. Se o site acabou de ser publicado, o primeiro processamento pode ainda não ter rodado.";
    console.error(err);
  });
})();
