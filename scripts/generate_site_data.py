"""Gera os JSONs estáticos otimizados consumidos pelo site.

Uso: python scripts/generate_site_data.py

Escreve em data_work/staging/ (nunca direto em public/data). O orquestrador
valida o staging e só então publica — dados válidos nunca são substituídos
por dados quebrados.

Saída:
  staging/meta.json                 manifesto (datas, fontes, contagens, outlier)
  staging/rankings.json             top-N por categoria (somente match "exact")
  staging/search-index.json         índice compacto p/ busca e filtros (lazy)
  staging/states/{UF}.json          índice por estado
  staging/candidates/{xy}.json      detalhes completos, em 256 shards pelo
                                    prefixo hexadecimal do id (evita dezenas
                                    de milhares de arquivos no repositório)
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone

from common import (
    compute_change,
    load_config,
    median,
    quartiles,
    read_json,
    resolve_path,
    write_json,
)

INDEX_FIELDS = [
    "id", "name", "ballot_name", "party", "uf", "office",
    "a2022", "a2026", "status", "change_abs", "change_pct", "outlier",
]

RANKING_DEFS = [
    ("top_increase_abs", "Maior aumento nominal", "change_abs", True, False),
    ("top_increase_pct", "Maior aumento percentual", "change_pct", True, True),
    ("top_assets", "Maior patrimônio declarado em 2026", "a2026", True, False),
    ("top_decrease_abs", "Maior redução nominal", "change_abs", False, False),
    ("top_multiple", "Patrimônio que mais multiplicou", "multiple", True, True),
]

DISCLAIMER = (
    "Os valores representam bens declarados pelos próprios candidatos à "
    "Justiça Eleitoral. Uma variação patrimonial, isoladamente, não indica "
    "irregularidade."
)


def build(config: dict, elections: dict[int, dict], persons: list[dict], manifest: dict) -> dict:
    """Monta todas as estruturas em memória. Retorna dict {caminho_relativo: dado}."""
    years = sorted(elections)
    base_year, target_year = (years[0], years[-1]) if len(years) >= 2 else (None, years[0])

    out: dict[str, object] = {}
    index_items: list[list] = []
    detail_files: dict[str, dict] = {}
    comparable: list[dict] = []

    for person in persons:
        refs = {int(y): sq for y, sq in person["elections"].items()}
        records = {y: elections[y][sq] for y, sq in refs.items() if sq in elections.get(y, {})}
        if not records:
            continue
        latest_year = max(records)
        latest = records[latest_year]
        a_base = records[base_year]["assets_total"] if base_year in records else None
        a_target = records[target_year]["assets_total"] if target_year in records else None
        change = compute_change(a_base, a_target)

        entry = {
            "id": person["id"],
            "name": latest["name"],
            "ballot_name": latest["ballot_name"],
            "party": latest["party"],
            "uf": latest["uf"],
            "office": latest["office"],
            "a2022": a_base,
            "a2026": a_target,
            "status": person["match_status"],
            "change_abs": change["absolute"],
            "change_pct": change["percentage"],
            "multiple": change["multiple"],
        }
        if person["match_status"] == "exact" and a_base is not None and a_target is not None:
            comparable.append(entry)

        detail_files[person["id"]] = {
            "id": person["id"],
            "name": latest["name"],
            "ballot_name": latest["ballot_name"],
            "match_status": person["match_status"],
            "elections": {
                str(y): {
                    "year": y,
                    "party": rec["party"],
                    "party_name": rec.get("party_name", ""),
                    "uf": rec["uf"],
                    "office": rec["office"],
                    "situation": rec.get("situation", ""),
                    "assets_total": rec["assets_total"],
                    "assets_count": rec["assets_count"],
                    "assets": [
                        {"type": a["type"], "description": a["description"], "value": a["value"]}
                        for a in rec["assets"]
                    ],
                }
                for y, rec in sorted(records.items())
            },
            "change": change,
            "disclaimer": DISCLAIMER,
        }
        index_items.append(entry)

    # Indicador estatístico de outlier (método de Tukey sobre a variação %
    # do conjunto comparável): pct > Q3 + 3×IQR. Puramente descritivo.
    pcts = [e["change_pct"] for e in comparable if e["change_pct"] is not None]
    q = quartiles(pcts)
    outlier_threshold = None
    if q:
        q1, q3 = q
        outlier_threshold = round(q3 + 3 * (q3 - q1), 2)
    for entry in index_items:
        entry["outlier"] = bool(
            outlier_threshold is not None
            and entry["status"] == "exact"
            and entry["change_pct"] is not None
            and entry["change_pct"] > outlier_threshold
        )
    for entry in index_items:
        if entry["id"] in detail_files:
            detail_files[entry["id"]]["outlier"] = entry["outlier"]
            detail_files[entry["id"]]["multiple"] = entry["multiple"]

    # Rankings — somente correspondência "exact", metodologia idêntica para todos.
    ranking_size = config.get("ranking_size", 100)
    rankings = {}
    for key, label, field, descending, needs_base in RANKING_DEFS:
        pool = [
            e for e in comparable
            if e.get(field) is not None and (not needs_base or (e["a2022"] or 0) > 0)
        ]
        pool.sort(key=lambda e: e[field], reverse=descending)
        if key == "top_decrease_abs":
            pool = [e for e in pool if e["change_abs"] is not None and e["change_abs"] < 0]
        rankings[key] = {
            "label": label,
            "entries": [
                {k: e[k] for k in (
                    "id", "name", "ballot_name", "party", "uf", "office",
                    "a2022", "a2026", "change_abs", "change_pct", "multiple", "outlier",
                )}
                for e in pool[:ranking_size]
            ],
        }

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status_counts: dict[str, int] = {}
    for p in persons:
        status_counts[p["match_status"]] = status_counts.get(p["match_status"], 0) + 1

    out["meta.json"] = {
        "project": config.get("project", "Enriquecímetro"),
        "generated_at": generated_at,
        "elections": years,
        "sources": [
            {
                "election": meta.get("election"),
                "kind": meta.get("kind"),
                "url": meta.get("url"),
                "file_last_modified": meta.get("last_modified"),
                "downloaded_at": meta.get("downloaded_at"),
            }
            for meta in manifest.values()
        ],
        "attribution": config.get("attribution", {}),
        "filters": {
            "uf": sorted({e["uf"] for e in index_items if e["uf"]}),
            "party": sorted({e["party"] for e in index_items if e["party"]}),
            "office": sorted({e["office"] for e in index_items if e["office"]}),
        },
        "candidate_count": {str(y): len(elections[y]) for y in years},
        "person_count": len(persons),
        "match_status_counts": status_counts,
        "comparable_count": len(comparable),
        "outlier_method": {
            "description": "Variação percentual acima de Q3 + 3×IQR (método de Tukey) "
                           "do conjunto de candidaturas com correspondência exata e "
                           "patrimônio anterior maior que zero.",
            "threshold_pct": outlier_threshold,
            "median_pct": round(median(pcts), 2) if pcts else None,
            "sample_size": len(pcts),
        },
        "disclaimer": DISCLAIMER,
    }
    # generated_at vive APENAS em meta.json: os demais arquivos só mudam
    # quando os dados de fato mudam, mantendo os commits diários mínimos.
    out["rankings.json"] = {"rankings": rankings}

    def compact(e: dict) -> list:
        return [e[f] for f in INDEX_FIELDS]

    out["search-index.json"] = {
        "fields": INDEX_FIELDS,
        "items": [compact(e) for e in index_items],
    }
    by_uf: dict[str, list] = {}
    for e in index_items:
        by_uf.setdefault(e["uf"] or "ZZ", []).append(compact(e))
    for uf, items in by_uf.items():
        out[f"states/{uf}.json"] = {"fields": INDEX_FIELDS, "items": items}

    # Detalhes por candidato em 256 shards (prefixo de 2 hex do id).
    shards: dict[str, dict] = {}
    for pid, detail in detail_files.items():
        shards.setdefault(pid[:2], {})[pid] = detail
    for prefix, bucket in shards.items():
        out[f"candidates/{prefix}.json"] = bucket
    return out


def main() -> int:
    config = load_config()
    work_dir = resolve_path(config, "work_dir")
    staging = work_dir / "staging"

    elections: dict[int, dict] = {}
    for year in config["elections"]:
        path = work_dir / f"election_{year}.json"
        if path.exists():
            elections[year] = read_json(path)["candidates"]
    if not elections:
        print("[generate] ERRO: nenhum dado transformado")
        return 1
    persons = read_json(work_dir / "persons.json")

    raw_dir = resolve_path(config, "download_dir")
    manifest_path = raw_dir / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}

    files = build(config, elections, persons, manifest)

    if staging.exists():
        shutil.rmtree(staging)
    for rel, data in files.items():
        write_json(staging / rel, data)
    print(f"[generate] {len(files)} arquivos gerados em {staging}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
