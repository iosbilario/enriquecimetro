"""Relaciona a mesma pessoa entre eleições diferentes.

Uso: python scripts/match_candidates.py

Metodologia (documentada em methodology.html):
  1. "exact"    — mesmo CPF válido, único em cada eleição.
  2. "probable" — mesmo nome normalizado + mesma data de nascimento,
                  combinação única em cada eleição (usado quando o CPF
                  está ausente ou inválido em um dos lados).
  3. "unverified" — nenhuma correspondência segura. NUNCA inventamos match.

Somente "exact" entra nos rankings comparativos principais.

O CPF é usado APENAS aqui, em memória e em arquivos de trabalho gitignored.
A saída persons.json NÃO contém CPF. Uma lista separada (sensitive_scan.txt,
gitignored) alimenta a validação que garante que nenhum CPF vazou para os
arquivos publicados.
"""
from __future__ import annotations

import re
import sys

from common import (
    is_valid_cpf,
    load_config,
    public_candidate_id,
    read_json,
    resolve_path,
    write_json,
)


def build_matches(elections: dict[int, dict]) -> list[dict]:
    """Recebe {ano: {sq: registro}} e devolve a lista de pessoas."""
    years = sorted(elections)
    persons: list[dict] = []

    def cpf_index(year: int) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for sq, cand in elections[year].items():
            cpf = re.sub(r"\D", "", cand.get("cpf") or "")
            if is_valid_cpf(cpf):
                index.setdefault(cpf, []).append(sq)
        return index

    def namebirth_index(year: int, exclude: set[str]) -> dict[tuple, list[str]]:
        index: dict[tuple, list[str]] = {}
        for sq, cand in elections[year].items():
            if sq in exclude:
                continue
            key = (cand.get("name_norm") or "", cand.get("birth") or "")
            if key[0] and key[1]:
                index.setdefault(key, []).append(sq)
        return index

    matched: dict[int, set[str]] = {y: set() for y in years}

    if len(years) >= 2:
        base_year, target_year = years[0], years[-1]
        base_cpfs = cpf_index(base_year)
        target_cpfs = cpf_index(target_year)

        # Nível 1: CPF exato e único nos dois lados.
        for cpf, target_sqs in target_cpfs.items():
            base_sqs = base_cpfs.get(cpf)
            if not base_sqs or len(base_sqs) != 1 or len(target_sqs) != 1:
                continue
            persons.append(
                {
                    "id": public_candidate_id(target_year, target_sqs[0]),
                    "match_status": "exact",
                    "elections": {str(base_year): base_sqs[0], str(target_year): target_sqs[0]},
                }
            )
            matched[base_year].add(base_sqs[0])
            matched[target_year].add(target_sqs[0])

        # Nível 2: nome normalizado + data de nascimento, únicos nos dois lados.
        base_nb = namebirth_index(base_year, matched[base_year])
        target_nb = namebirth_index(target_year, matched[target_year])
        for key, target_sqs in target_nb.items():
            base_sqs = base_nb.get(key)
            if not base_sqs or len(base_sqs) != 1 or len(target_sqs) != 1:
                continue
            persons.append(
                {
                    "id": public_candidate_id(target_year, target_sqs[0]),
                    "match_status": "probable",
                    "elections": {str(base_year): base_sqs[0], str(target_year): target_sqs[0]},
                }
            )
            matched[base_year].add(base_sqs[0])
            matched[target_year].add(target_sqs[0])

    # Candidaturas sem correspondência: publicadas como "unverified".
    for year in years:
        for sq in elections[year]:
            if sq in matched[year]:
                continue
            persons.append(
                {
                    "id": public_candidate_id(year, sq),
                    "match_status": "unverified",
                    "elections": {str(year): sq},
                }
            )
    return persons


def main() -> int:
    config = load_config()
    work_dir = resolve_path(config, "work_dir")

    elections: dict[int, dict] = {}
    for year in config["elections"]:
        path = work_dir / f"election_{year}.json"
        if not path.exists():
            print(f"[match] AVISO: {path.name} ausente")
            continue
        elections[year] = read_json(path)["candidates"]

    if not elections:
        print("[match] ERRO: nenhuma eleição transformada")
        return 1

    persons = build_matches(elections)
    write_json(work_dir / "persons.json", persons)

    # Lista de valores sensíveis para a varredura de validação (gitignored).
    sensitive: set[str] = set()
    for cands in elections.values():
        for cand in cands.values():
            cpf = re.sub(r"\D", "", cand.get("cpf") or "")
            if len(cpf) == 11:
                sensitive.add(cpf)
    scan_path = work_dir / "sensitive_scan.txt"
    scan_path.write_text("\n".join(sorted(sensitive)), encoding="utf-8")

    by_status: dict[str, int] = {}
    for p in persons:
        by_status[p["match_status"]] = by_status.get(p["match_status"], 0) + 1
    print(f"[match] pessoas: {len(persons)} | {by_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
