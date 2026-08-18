/* Enriquecímetro — página individual do candidato. */
"use strict";

(() => {
  const { money, moneyCompact, pct, titleCase, fetchJSON, el, fmtDate, avatar } = ENR;
  const $ = (sel) => document.querySelector(sel);

  function svgBarChart(entries) {
    // Gráfico de barras honesto: eixo sempre começa em zero, valores sempre visíveis.
    const W = 560, H = 220, padL = 16, padR = 16, padT = 34, padB = 34;
    const max = Math.max(...entries.map((e) => e.total), 1);
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;
    const barW = Math.min(140, innerW / entries.length - 40);
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      "Gráfico de barras do patrimônio declarado: " +
        entries.map((e) => `${e.year}: ${money(e.total)}`).join("; ")
    );
    entries.forEach((e, i) => {
      const cx = padL + (innerW / entries.length) * (i + 0.5);
      const h = max > 0 ? (e.total / max) * innerH : 0;
      const y = padT + innerH - h;
      const rect = document.createElementNS(svgNS, "rect");
      rect.setAttribute("x", cx - barW / 2);
      rect.setAttribute("y", y);
      rect.setAttribute("width", barW);
      rect.setAttribute("height", Math.max(h, e.total > 0 ? 2 : 0));
      rect.setAttribute("rx", 6);
      rect.setAttribute("class", "bar-rect");
      svg.append(rect);

      const val = document.createElementNS(svgNS, "text");
      val.setAttribute("x", cx);
      val.setAttribute("y", y - 8);
      val.setAttribute("text-anchor", "middle");
      val.setAttribute("class", "bar-label");
      val.textContent = moneyCompact(e.total);
      svg.append(val);

      const yr = document.createElementNS(svgNS, "text");
      yr.setAttribute("x", cx);
      yr.setAttribute("y", H - 12);
      yr.setAttribute("text-anchor", "middle");
      yr.setAttribute("class", "bar-year");
      yr.textContent = e.year;
      svg.append(yr);
    });
    // linha de base (zero)
    const base = document.createElementNS(svgNS, "line");
    base.setAttribute("x1", padL);
    base.setAttribute("x2", W - padR);
    base.setAttribute("y1", padT + innerH);
    base.setAttribute("y2", padT + innerH);
    base.setAttribute("stroke", "currentColor");
    base.setAttribute("opacity", "0.35");
    svg.append(base);
    return svg;
  }

  function assetSection(year, data) {
    const container = el("section", { class: "assets-block" });
    container.append(el("h2", {}, `Bens declarados em ${year}`));
    if (!data || data.assets_count === 0) {
      container.append(
        el("p", { class: "status-line" },
          data
            ? "Nenhum bem declarado nesta eleição (declaração registrada sem bens)."
            : "Sem declaração localizada para esta eleição.")
      );
      return container;
    }
    const list = el("ul", { class: "asset-list" });
    [...data.assets]
      .sort((a, b) => b.value - a.value)
      .forEach((a) => {
        list.append(
          el("li", {},
            el("div", { class: "a-desc" },
              el("span", { class: "a-type" }, a.type),
              a.description || "(sem descrição)"),
            el("span", { class: "a-val" }, money(a.value)))
        );
      });
    container.append(list);
    container.append(
      el("div", { class: "asset-total" },
        el("span", {}, `Total declarado em ${year}`),
        el("span", {}, money(data.assets_total)))
    );
    return container;
  }

  async function init() {
    const id = new URLSearchParams(location.search).get("id");
    const root = $("#profile");
    if (!id || !/^[0-9a-f]{6,16}$/.test(id)) {
      root.innerHTML = "<p class='empty'>Candidato não especificado.</p>";
      return;
    }
    let detail;
    try {
      const shard = await fetchJSON(`public/data/candidates/${id.slice(0, 2)}.json`);
      detail = shard[id];
      if (!detail) throw new Error("id ausente no shard");
    } catch {
      root.innerHTML = "<p class='empty'>Candidato não encontrado.</p>";
      return;
    }
    const meta = await fetchJSON("public/data/meta.json").catch(() => null);

    const years = Object.keys(detail.elections).sort();
    const latest = detail.elections[years[years.length - 1]];
    const displayName = titleCase(detail.name);

    document.title = `${displayName} — evolução do patrimônio declarado | Enriquecímetro`;
    const desc = document.querySelector('meta[name="description"]');
    if (desc) desc.content =
      `Patrimônio declarado por ${displayName} à Justiça Eleitoral nas eleições de ${years.join(" e ")}.`;

    $("#p-avatar").replaceWith(
      avatar(detail, {
        large: true,
        hasPhoto: "2026" in detail.elections,
      })
    );
    $("#p-name").textContent = displayName;
    $("#p-ballot").textContent = `Nome de urna: ${titleCase(detail.ballot_name)}`;
    const chips = $("#p-chips");
    chips.append(
      el("span", { class: "chip" }, latest.party || "—"),
      el("span", { class: "chip" }, latest.uf || "—"),
      el("span", { class: "chip" }, titleCase(latest.office || "")),
    );
    if (detail.match_status !== "exact" && years.length > 1) {
      chips.append(el("span", { class: "chip" }, "correspondência provável entre eleições"));
    }
    if (years.length === 1) {
      chips.append(el("span", { class: "chip" }, `dados de ${years[0]} apenas`));
    }

    // Timeline
    const flow = $("#big-flow");
    years.forEach((y, i) => {
      if (i > 0) flow.append(el("span", { class: "arrow", "aria-hidden": "true" }, "→"));
      flow.append(
        el("div", { class: "big-col" },
          el("div", { class: "yr" }, y),
          el("div", { class: "val" }, money(detail.elections[y].assets_total)))
      );
    });

    const deltaNode = $("#big-delta");
    if (years.length > 1 && detail.change.absolute !== null) {
      const up = detail.change.absolute >= 0;
      const pctText =
        detail.change.percentage !== null
          ? pct(detail.change.percentage)
          : "Variação percentual não aplicável — patrimônio anterior declarado como R$ 0";
      deltaNode.append(
        el("span", { class: `delta ${up ? "up" : "down"}` },
          el("strong", { class: "abs" },
            `${up ? "▲" : "▼"} ${moneyCompact(Math.abs(detail.change.absolute))}`)),
        el("span", { class: "pct" }, pctText),
        detail.multiple ? el("span", { class: "pct" }, ` · ${String(detail.multiple).replace(".", ",")}× o valor anterior`) : null
      );
      if (detail.outlier) {
        deltaNode.append(
          el("p", {},
            el("span", { class: "badge outlier" }, "variação muito acima da mediana do conjunto analisado"),
            el("small", {}, " — indicador estatístico descritivo; ver ",
              el("a", { href: "methodology.html#outliers" }, "metodologia"), "."))
        );
      }
    } else {
      deltaNode.append(
        el("span", { class: "pct" },
          "Comparação entre eleições indisponível para esta candidatura.")
      );
    }

    // Gráfico
    const chartEntries = years.map((y) => ({ year: y, total: detail.elections[y].assets_total }));
    const box = $("#chart");
    box.append(svgBarChart(chartEntries));

    // Ação: gerar card para redes sociais (Fábrica de Posts abre já neste candidato)
    const timeline = document.querySelector(".timeline");
    if (timeline) {
      timeline.after(
        el("p", { class: "actions" },
          el("a", { class: "btn-share", href: `social/fabrica-de-posts.html?id=${id}` },
            "Gerar post deste candidato"))
      );
    }

    // Bens por eleição (mais recente primeiro na leitura? ordem cronológica)
    const assetsRoot = $("#assets");
    ["2022", "2026"].forEach((y) => {
      if (y in detail.elections || ["2022", "2026"].includes(y)) {
        assetsRoot.append(assetSection(y, detail.elections[y] || null));
      }
    });

    // Fontes
    if (meta) {
      const list = $("#source-list");
      (meta.sources || []).forEach((s) => {
        if (!s.url) return;
        list.append(
          el("li", {},
            el("a", { href: s.url, rel: "noopener" },
              `${s.kind === "assets" ? "Bens de candidatos" : "Candidatos"} — eleição ${s.election}`),
            ` (arquivo do TSE de ${s.file_last_modified || "data não informada"}, baixado em ${fmtDate(s.downloaded_at)})`)
        );
      });
      $("#gen-at").textContent = fmtDate(meta.generated_at);
    }
  }

  init().catch((err) => {
    console.error(err);
    document.querySelector("#profile").innerHTML =
      "<p class='empty'>Erro ao carregar os dados do candidato.</p>";
  });
})();
