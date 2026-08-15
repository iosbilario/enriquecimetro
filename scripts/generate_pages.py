"""Pré-renderiza páginas estáticas para SEO/GEO.

Uso: python scripts/generate_pages.py   (após o pipeline de dados publicar)

Gera:
  c/{id}.html    página estática por candidato COM comparação entre eleições
                 (conteúdo completo no HTML — bots de IA não executam JS)
  sitemap.xml    home + páginas fixas + páginas de candidato
  robots.txt     liberado para buscadores e crawlers de IA + sitemap
  llms.txt       descrição do projeto para motores generativos
  index.html     bloco de cards do ranking reescrito entre marcadores SSR

Somente biblioteca padrão; saída determinística (só muda se os dados mudarem).
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from common import ROOT, load_config, read_json

SSR_START = "<!-- ssr:rankings:start -->"
SSR_END = "<!-- ssr:rankings:end -->"

DISCLAIMER = ("Uma variação patrimonial elevada, por si só, não representa evidência de "
              "irregularidade. Os valores exibidos correspondem às declarações "
              "apresentadas à Justiça Eleitoral.")


def fmt_brl(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f"R$ {s}"


def fmt_pct(v: float | None) -> str | None:
    if v is None:
        return None
    s = f"{v:+,.1f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f"{s}%"


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def title_case(s: str) -> str:
    keep = {"da", "de", "do", "das", "dos", "e"}
    words = (s or "").lower().split()
    out = []
    for i, w in enumerate(words):
        out.append(w if (i and w in keep) else w.capitalize())
    return " ".join(out)


def page_head(cfg: dict, *, title: str, description: str, path: str,
              og_image: str, extra_head: str = "") -> str:
    base = cfg["site"]["base_url"].rstrip("/")
    canonical = f"{base}/{path}" if path else f"{base}/"
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{esc(canonical)}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{esc(canonical)}">
  <meta property="og:image" content="{esc(og_image)}">
  <meta property="og:locale" content="pt_BR">
  <meta name="twitter:card" content="summary">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>">
  <link rel="stylesheet" href="../public/css/style.css">
{extra_head}</head>"""


HEADER = """<body>
  <a class="skip-link" href="#main">Pular para o conteúdo</a>
  <header class="site-header">
    <div class="wrap">
      <a class="brand" href="../">Enriquecí<span class="tld">metro</span></a>
      <nav class="site-nav" aria-label="Navegação principal">
        <a href="../">Início</a>
        <a href="../methodology.html">Metodologia</a>
        <a href="../about.html">Sobre</a>
      </nav>
    </div>
  </header>
  <main id="main" class="wrap">"""

SEAL = ('<a class="seal" href="https://carimbo.tec.br/v/3493811489d0e38dc4fa4546a1bbcd72" '
        'title="Ver o recibo público desta auditoria" rel="noopener">'
        '<img src="https://carimbo.tec.br/api/selo/3493811489d0e38dc4fa4546a1bbcd72.svg'
        '?template=circulo&amp;tema=escuro" '
        'alt="Carimbo de auditoria técnica independente — clique para ler o recibo público" '
        'width="104" height="104" loading="lazy" style="border:0"></a>')

FOOTER = f"""  </main>
  <footer class="site-footer">
    <div class="wrap">
      {SEAL}
      <p class="disclaimer">{DISCLAIMER}</p>
      <nav aria-label="Rodapé">
        <a href="../about.html">Sobre</a>
        <a href="../methodology.html">Metodologia</a>
        <a href="https://github.com/iosbilario/enriquecimetro" rel="noopener">GitHub</a>
      </nav>
      <p>Projeto independente, apartidário e sem fins lucrativos. Sem vínculo com o TSE.
        Fonte dos dados: Tribunal Superior Eleitoral — Portal de Dados Abertos.</p>
    </div>
  </footer>
</body>
</html>"""


def asset_list_html(year: str, rec: dict | None) -> str:
    if rec is None:
        return (f"<section class='assets-block'><h2>Bens declarados em {year}</h2>"
                "<p class='status-line'>Sem declaração localizada para esta eleição.</p></section>")
    if not rec["assets"]:
        return (f"<section class='assets-block'><h2>Bens declarados em {year}</h2>"
                "<p class='status-line'>Nenhum bem declarado nesta eleição "
                "(declaração registrada sem bens).</p></section>")
    items = "".join(
        f"<li><div class='a-desc'><span class='a-type'>{esc(a['type'])}</span>"
        f"{esc(a['description'] or '(sem descrição)')}</div>"
        f"<span class='a-val'>{fmt_brl(a['value'])}</span></li>"
        for a in sorted(rec["assets"], key=lambda x: -x["value"])
    )
    return (f"<section class='assets-block'><h2>Bens declarados em {year}</h2>"
            f"<ul class='asset-list'>{items}</ul>"
            f"<div class='asset-total'><span>Total declarado em {year}</span>"
            f"<span>{fmt_brl(rec['assets_total'])}</span></div></section>")


def candidate_page(cfg: dict, detail: dict, meta: dict) -> str:
    base = cfg["site"]["base_url"].rstrip("/")
    name = title_case(detail["name"])
    years = sorted(detail["elections"])
    y0, y1 = years[0], years[-1]
    e0, e1 = detail["elections"][y0], detail["elections"][y1]
    change = detail["change"]

    pct = fmt_pct(change.get("percentage"))
    pct_text = pct if pct else "variação percentual não aplicável (patrimônio anterior declarado como R$ 0)"
    desc = (f"Patrimônio declarado por {name} à Justiça Eleitoral: {fmt_brl(e0['assets_total'])} "
            f"em {y0} e {fmt_brl(e1['assets_total'])} em {y1} ({pct_text}). Dados oficiais do TSE.")
    title = f"{name} — evolução do patrimônio declarado | Enriquecímetro"

    photo = f"{base}/public/photos/{detail['id']}.webp"
    og_image = photo if detail["match_status"] in ("exact", "probable") else f"{base}/public/assets/og.png"

    ld = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": name,
        "alternateName": title_case(detail["ballot_name"]),
        "image": og_image,
        "affiliation": e1.get("party_name") or e1.get("party") or None,
        "description": desc,
        "url": f"{base}/c/{detail['id']}.html",
    }
    extra = ('  <script type="application/ld+json">'
             + json.dumps({k: v for k, v in ld.items() if v}, ensure_ascii=False)
             + "</script>\n")

    outlier_html = ""
    if detail.get("outlier"):
        outlier_html = ("<p><span class='badge outlier'>variação muito acima da mediana do "
                        "conjunto analisado</span> <small>— indicador estatístico descritivo; "
                        "ver <a href='../methodology.html#outliers'>metodologia</a>.</small></p>")

    mult = detail.get("multiple")
    mult_html = ""
    if mult:
        mult_html = f" · {str(mult).replace('.', ',')}× o valor anterior"

    up = (change.get("absolute") or 0) >= 0
    arrow = "▲" if up else "▼"

    status_note = ""
    if detail["match_status"] == "probable":
        status_note = ("<p class='status-line'>Correspondência provável entre as eleições "
                       "(nome completo e data de nascimento; ver metodologia).</p>")

    sources_html = "".join(
        f"<li><a href='{esc(s['url'])}' rel='noopener'>"
        f"{'Bens de candidatos' if s['kind'] == 'assets' else 'Candidatos'} — eleição {s['election']}</a>"
        f" (arquivo do TSE de {esc(s.get('file_last_modified') or 'data não informada')})</li>"
        for s in meta.get("sources", []) if s.get("url")
    )

    body = f"""{HEADER}
    <div class="profile-head">
      <div class="profile-id">
        <img class="avatar avatar-lg" src="../public/photos/{detail['id']}.webp" alt="" onerror="this.style.display='none'">
        <div>
          <h1>{esc(name)}</h1>
          <p class="ballot">Nome de urna: {esc(title_case(detail['ballot_name']))}</p>
        </div>
      </div>
      <div class="chips" style="margin-top:10px">
        <span class="chip">{esc(e1.get('party') or '—')}</span>
        <span class="chip">{esc(e1.get('uf') or '—')}</span>
        <span class="chip">{esc(title_case(e1.get('office') or ''))}</span>
      </div>
    </div>

    <section>
      <h2>Evolução patrimonial declarada</h2>
      <div class="timeline">
        <div class="big-flow">
          <div class="big-col"><div class="yr">{y0}</div><div class="val">{fmt_brl(e0['assets_total'])}</div></div>
          <span class="arrow" aria-hidden="true">→</span>
          <div class="big-col"><div class="yr">{y1}</div><div class="val">{fmt_brl(e1['assets_total'])}</div></div>
        </div>
        <div class="big-delta">
          <span class="delta {'up' if up else 'down'}"><strong class="abs">{arrow} {fmt_brl(abs(change['absolute'])) if change['absolute'] is not None else '—'}</strong></span>
          <span class="pct">{esc(pct_text)}{mult_html}</span>
          {outlier_html}
        </div>
      </div>
      {status_note}
      <p><a href="../candidate.html?id={detail['id']}">Ver versão interativa com gráfico →</a></p>
    </section>

    {asset_list_html(y0, e0)}
    {asset_list_html(y1, e1)}

    <section class="prose">
      <h2>O que esses números significam?</h2>
      <p>Todo candidato apresenta à Justiça Eleitoral, no registro da candidatura, uma relação dos
        bens que possui. Os valores desta página são exatamente os declarados, sem ajuste, estimativa
        de mercado ou correção monetária. Uma variação entre eleições pode ter muitas explicações
        legítimas. <strong>Este site não determina a origem do patrimônio e não classifica qualquer
        variação como lícita ou ilícita.</strong></p>
    </section>

    <section class="prose">
      <h2>Fonte dos dados</h2>
      <p>Tribunal Superior Eleitoral — <a href="https://dadosabertos.tse.jus.br/" rel="noopener">Portal de Dados Abertos</a>.</p>
      <ul>{sources_html}</ul>
      <p>Dados processados em {esc(meta.get('generated_at', ''))}. <a href="../methodology.html">Metodologia completa</a>.</p>
    </section>
{FOOTER}"""

    head = page_head(cfg, title=title, description=desc,
                     path=f"c/{detail['id']}.html", og_image=og_image, extra_head=extra)
    return head + "\n" + body


def ssr_card(item: dict) -> str:
    pct = fmt_pct(item.get("change_pct"))
    up = (item.get("change_abs") or 0) >= 0
    return f"""<li class="card">
  <div class="who"><div class="who-text">
    <h3 class="name">{esc(title_case(item['ballot_name'] or item['name']))}</h3>
    <p class="meta">{esc(item['party'] or '—')} · {esc(item['uf'] or '—')} · {esc(title_case(item['office'] or ''))}</p>
  </div></div>
  <div class="flow"><div class="col"><div class="yr">2022</div><div class="val">{fmt_brl(item['a2022'])}</div></div>
  <span class="arrow" aria-hidden="true">→</span>
  <div class="col"><div class="yr">2026</div><div class="val">{fmt_brl(item['a2026'])}</div></div></div>
  <div class="delta {'up' if up else 'down'}"><span class="abs">{'▲' if up else '▼'} {fmt_brl(abs(item['change_abs']))}</span>{f'<span class="pct">{pct}</span>' if pct else ''}</div>
  <a class="cta" href="c/{item['id']}.html">Ver evolução patrimonial</a>
</li>"""


def main() -> int:
    cfg = load_config()
    base = cfg["site"]["base_url"].rstrip("/")
    data_dir = ROOT / cfg["paths"]["output_dir"]
    if not (data_dir / "meta.json").exists():
        print("[pages] ERRO: public/data/meta.json ausente — rode o pipeline antes")
        return 1
    meta = read_json(data_dir / "meta.json")
    rankings = read_json(data_dir / "rankings.json")["rankings"]

    out_dir = ROOT / "c"
    out_dir.mkdir(exist_ok=True)

    # --- páginas de candidato (somente quem tem comparação entre eleições) ---
    written = set()
    for shard_path in sorted((data_dir / "candidates").glob("*.json")):
        shard = read_json(shard_path)
        for pid, detail in shard.items():
            if detail["match_status"] not in ("exact", "probable"):
                continue
            if len(detail["elections"]) < 2:
                continue
            (out_dir / f"{pid}.html").write_text(
                candidate_page(cfg, detail, meta), encoding="utf-8", newline="\n")
            written.add(pid)

    # remove páginas de candidatos que saíram dos dados
    removed = 0
    for old in out_dir.glob("*.html"):
        if old.stem not in written:
            old.unlink()
            removed += 1

    # --- bloco SSR na home (top do ranking nominal) ---
    index_path = ROOT / "index.html"
    src = index_path.read_text(encoding="utf-8")
    if SSR_START in src and SSR_END in src:
        top = rankings["top_increase_abs"]["entries"][:24]
        block = SSR_START + "\n" + "\n".join(ssr_card(e) for e in top) + "\n" + SSR_END
        src = re.sub(re.escape(SSR_START) + r".*?" + re.escape(SSR_END),
                     lambda _m: block, src, flags=re.DOTALL)
        index_path.write_text(src, encoding="utf-8", newline="\n")
        print(f"[pages] bloco SSR da home atualizado ({len(top)} cards)")
    else:
        print("[pages] AVISO: marcadores SSR ausentes em index.html")

    # --- sitemap.xml ---
    static_paths = ["", "methodology.html", "about.html", "dados.html"]
    urls = [f"{base}/{p}" if p else f"{base}/" for p in static_paths]
    urls += [f"{base}/c/{pid}.html" for pid in sorted(written)]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"<url><loc>{html.escape(u)}</loc></url>" for u in urls]
    sitemap.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8", newline="\n")

    # --- robots.txt ---
    (ROOT / "robots.txt").write_text(f"""# Enriquecímetro — dados públicos de transparência eleitoral.
# Indexação bem-vinda, inclusive por crawlers de IA.
User-agent: *
Allow: /

Sitemap: {base}/sitemap.xml
""", encoding="utf-8", newline="\n")

    # --- llms.txt (para motores generativos) ---
    counts = meta.get("candidate_count", {})
    (ROOT / "llms.txt").write_text(f"""# Enriquecímetro

> {cfg['site']['tagline']}. Site brasileiro, gratuito, apartidário e de código
> aberto que compara o patrimônio declarado pelos candidatos à Justiça
> Eleitoral entre as eleições de 2022 e 2026, usando exclusivamente dados
> oficiais do TSE (Portal de Dados Abertos). Princípio editorial: mostramos os
> números, não presumimos a origem. Variação patrimonial, isoladamente, não
> indica irregularidade.

Candidaturas processadas: {counts.get('2022', '?')} (2022) e {counts.get('2026', '?')} (2026).
Comparações seguras (mesmo indivíduo nas duas eleições): {meta.get('comparable_count', '?')}.

## Páginas
- [Início]({base}/): busca, filtros e rankings de variação patrimonial declarada
- [Metodologia]({base}/methodology.html): fontes, matching, cálculos, limitações
- [Sobre]({base}/about.html): princípios, licença (MIT), como contribuir
- [Dados abertos]({base}/dados.html): endpoints JSON estáticos documentados

## Dados (JSON estático, CORS aberto)
- [Manifesto]({base}/public/data/meta.json): fontes, datas, contagens
- [Rankings]({base}/public/data/rankings.json)
- [Índice de busca]({base}/public/data/search-index.json)
- Por estado: {base}/public/data/states/{{UF}}.json

## Como citar
"Enriquecímetro (dados do TSE/Portal de Dados Abertos), {base}/"
""", encoding="utf-8", newline="\n")

    print(f"[pages] {len(written)} páginas de candidato ({removed} removidas), "
          f"sitemap com {len(urls)} URLs, robots.txt e llms.txt gerados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
