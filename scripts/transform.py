"""Transforma os ZIPs brutos do TSE em arquivos intermediários por eleição.

Uso: python scripts/transform.py

Saída: data_work/election_{ano}.json (gitignored; contém CPF apenas para o
matching interno — NUNCA é publicado nem commitado).

Lê todos os CSVs dentro de cada ZIP (o TSE distribui por UF e/ou BRASIL),
deduplica por SQ_CANDIDATO e agrega os bens declarados.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from common import (
    load_config,
    normalize_name,
    parse_brl,
    redact_personal_numbers,
    resolve_path,
    write_json,
)

# Campos extraídos do consulta_cand. Qualquer coluna fora desta lista é
# descartada imediatamente (minimização de dados: e-mail, título de eleitor,
# endereço etc. nunca entram no pipeline).
CANDIDATE_FIELDS = {
    "SQ_CANDIDATO": "sq",
    "NM_CANDIDATO": "name",
    "NM_URNA_CANDIDATO": "ballot_name",
    "NR_CPF_CANDIDATO": "cpf",  # uso interno exclusivo para matching
    "SG_UF": "uf",
    "DS_CARGO": "office",
    "SG_PARTIDO": "party",
    "NM_PARTIDO": "party_name",
    "DT_NASCIMENTO": "birth",  # uso interno exclusivo para matching provável
    "DS_SITUACAO_CANDIDATURA": "situation",
    "NR_CANDIDATO": "number",
}

ASSET_FIELDS = {
    "SQ_CANDIDATO": "sq",
    "DS_TIPO_BEM_CANDIDATO": "type",
    "DS_BEM_CANDIDATO": "description",
    "VR_BEM_CANDIDATO": "value_raw",
}

NULLISH = {"#NULO#", "#NE#", "NULO", "#NULO", ""}


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    v = value.strip().strip('"').strip()
    return "" if v in NULLISH else v


def _decode(data: bytes) -> str:
    """TSE publica em Latin-1; alguns arquivos novos vêm em UTF-8."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        # Heurística: se decodificou como utf-8 sem erro, aceita; latin-1
        # nunca falha, então é o fallback final.
        return text
    return data.decode("latin-1", errors="replace")


def iter_zip_rows(zip_path: Path):
    """Itera linhas (como dicts) de todos os CSVs de um ZIP do TSE."""
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if not info.filename.lower().endswith((".csv", ".txt")):
                continue
            text = _decode(zf.read(info))
            reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"')
            header = None
            for row in reader:
                if header is None:
                    header = [h.strip().strip('"').upper() for h in row]
                    continue
                if len(row) != len(header):
                    continue
                yield dict(zip(header, row))


def load_candidates(zip_path: Path) -> dict[str, dict]:
    candidates: dict[str, dict] = {}
    for row in iter_zip_rows(zip_path):
        record = {}
        for column, key in CANDIDATE_FIELDS.items():
            record[key] = _clean(row.get(column))
        sq = record["sq"]
        if not sq:
            continue
        if sq in candidates:
            continue  # registros de 2º turno repetem o mesmo SQ
        record["name_norm"] = normalize_name(record["name"])
        record["assets"] = []
        record["assets_total"] = 0.0
        record["assets_count"] = 0
        candidates[sq] = record
    return candidates


def attach_assets(candidates: dict[str, dict], zip_path: Path) -> int:
    ignored = 0
    seen: set[tuple] = set()
    for row in iter_zip_rows(zip_path):
        sq = _clean(row.get("SQ_CANDIDATO"))
        cand = candidates.get(sq)
        if cand is None:
            ignored += 1
            continue
        value = parse_brl(row.get("VR_BEM_CANDIDATO"))
        if value is None:
            ignored += 1
            continue
        # Os ZIPs do TSE trazem o agregado _BRASIL.csv E os arquivos por UF:
        # a mesma linha aparece duas vezes. Deduplica pelo nº de ordem do bem
        # (ou, na ausência dele, pelo conteúdo completo da linha).
        order = _clean(row.get("NR_ORDEM_BEM_CANDIDATO")) or _clean(row.get("NR_ORDEM_CANDIDATO"))
        key = (
            (sq, "ord", order)
            if order
            else (sq, _clean(row.get("DS_TIPO_BEM_CANDIDATO")),
                  _clean(row.get("DS_BEM_CANDIDATO")), value)
        )
        if key in seen:
            continue
        seen.add(key)
        cand["assets"].append(
            {
                "type": _clean(row.get("DS_TIPO_BEM_CANDIDATO")) or "Não informado",
                "description": redact_personal_numbers(_clean(row.get("DS_BEM_CANDIDATO"))),
                "value": value,
            }
        )
    for cand in candidates.values():
        cand["assets_total"] = round(sum(a["value"] for a in cand["assets"]), 2)
        cand["assets_count"] = len(cand["assets"])
    return ignored


def main() -> int:
    config = load_config()
    raw_dir = resolve_path(config, "download_dir")
    work_dir = resolve_path(config, "work_dir")
    work_dir.mkdir(parents=True, exist_ok=True)

    manifest = {}
    manifest_path = raw_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for year in config["elections"]:
        cand_zip = raw_dir / f"candidates_{year}.zip"
        asset_zip = raw_dir / f"assets_{year}.zip"
        if not cand_zip.exists() or not asset_zip.exists():
            print(f"[transform] AVISO: arquivos de {year} ausentes, pulando")
            continue
        print(f"[transform] {year}: lendo candidatos de {cand_zip.name}")
        candidates = load_candidates(cand_zip)
        print(f"[transform] {year}: {len(candidates)} candidaturas únicas")
        ignored = attach_assets(candidates, asset_zip)
        with_assets = sum(1 for c in candidates.values() if c["assets_count"])
        print(
            f"[transform] {year}: bens agregados "
            f"({with_assets} candidaturas com bens, {ignored} linhas ignoradas)"
        )
        out = {
            "year": year,
            "sources": {
                "candidates": manifest.get(f"candidates_{year}.zip", {}),
                "assets": manifest.get(f"assets_{year}.zip", {}),
            },
            "candidates": candidates,
        }
        write_json(work_dir / f"election_{year}.json", out)
        print(f"[transform] {year}: gravado em data_work/election_{year}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
