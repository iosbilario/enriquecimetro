/* Enriquecímetro — utilidades compartilhadas (sem dependências externas). */
"use strict";

const ENR = (() => {
  const brl = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  });
  const brlCents = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
  });
  const pctFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

  function money(v) {
    if (v === null || v === undefined) return "—";
    return Math.abs(v) < 1000 ? brlCents.format(v) : brl.format(v);
  }

  /* Forma compacta: R$ 5,48 milhões / R$ 18,3 mil */
  function moneyCompact(v) {
    if (v === null || v === undefined) return "—";
    const abs = Math.abs(v);
    const sign = v < 0 ? "-" : "";
    const n = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: abs >= 1e4 ? 2 : 1 });
    if (abs >= 1e9) return `${sign}R$ ${n.format(abs / 1e9)} bi`;
    if (abs >= 1e6) return `${sign}R$ ${n.format(abs / 1e6)} mi`;
    if (abs >= 1e3) return `${sign}R$ ${n.format(abs / 1e3)} mil`;
    return brlCents.format(v);
  }

  function pct(v) {
    if (v === null || v === undefined) return null;
    const sign = v > 0 ? "+" : "";
    return `${sign}${pctFmt.format(v)}%`;
  }

  function normalize(s) {
    return (s || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toUpperCase()
      .trim();
  }

  function titleCase(s) {
    const keepLower = new Set(["DA", "DE", "DO", "DAS", "DOS", "E"]);
    return (s || "")
      .toLowerCase()
      .split(/\s+/)
      .map((w, i) => {
        if (i > 0 && keepLower.has(w.toUpperCase())) return w;
        return w.charAt(0).toUpperCase() + w.slice(1);
      })
      .join(" ");
  }

  const cache = new Map();
  async function fetchJSON(path) {
    if (cache.has(path)) return cache.get(path);
    const promise = fetch(path).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status} em ${path}`);
      return r.json();
    });
    cache.set(path, promise);
    return promise;
  }

  /* Converte linhas compactas do índice ({fields, items}) em objetos. */
  function inflate(indexDoc) {
    const f = indexDoc.fields;
    return indexDoc.items.map((row) => {
      const o = {};
      f.forEach((name, i) => (o[name] = row[i]));
      return o;
    });
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k.startsWith("data-") || k.startsWith("aria-")) node.setAttribute(k, v);
      else node[k] = v;
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined) continue;
      node.append(child.nodeType ? child : document.createTextNode(child));
    }
    return node;
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    try {
      return new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
        timeZone: "America/Sao_Paulo",
      }).format(new Date(iso));
    } catch {
      return iso;
    }
  }

  return { money, moneyCompact, pct, normalize, titleCase, fetchJSON, inflate, debounce, el, fmtDate };
})();
