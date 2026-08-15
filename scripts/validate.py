"""Valida o staging antes da publicação. Se algo crítico falhar, ABORTA.

Uso: python scripts/validate.py [diretório]   (padrão: data_work/staging)

Checagens:
  - arquivos essenciais existem e não estão vazios;
  - número de candidatos dentro de limites plausíveis;
  - valores numéricos ou null; nenhum patrimônio total negativo;
  - datas válidas (ISO 8601);
  - nenhuma chave sensível (cpf, e-mail, título de eleitor, endereço, telefone);
  - nenhum CPF real (lista interna gitignored) aparece em qualquer arquivo;
  - nenhum número de 11 dígitos com checksum de CPF válido fora de descrições
    de bens (que são texto livre declarado pelo próprio candidato ao TSE).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from common import is_valid_cpf, load_config, read_json, resolve_path

FORBIDDEN_KEY_RE = re.compile(
    r"cpf|titulo|email|e-mail|endereco|telefone|nr_titulo", re.IGNORECASE
)


class ValidationError(Exception):
    pass


def _iter_keys(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield f"{path}.{k}", k
            yield from _iter_keys(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _iter_keys(v, f"{path}[{i}]")


def validate_staging(staging: Path, config: dict, sensitive: set[str]) -> list[str]:
    problems: list[str] = []

    meta_path = staging / "meta.json"
    if not meta_path.exists() or meta_path.stat().st_size == 0:
        return ["meta.json ausente ou vazio"]
    meta = read_json(meta_path)

    try:
        datetime.fromisoformat(meta["generated_at"])
    except (KeyError, ValueError):
        problems.append("meta.generated_at inválido")

    vmin = config["validation"]["min_candidates_per_election"]
    vmax = config["validation"]["max_candidates_per_election"]
    for year, count in meta.get("candidate_count", {}).items():
        if not (vmin <= count <= vmax):
            problems.append(f"contagem de candidatos implausível em {year}: {count}")
    if not meta.get("candidate_count"):
        problems.append("meta.candidate_count vazio")

    for name in ("rankings.json", "search-index.json"):
        p = staging / name
        if not p.exists() or p.stat().st_size == 0:
            problems.append(f"{name} ausente ou vazio")

    idx = read_json(staging / "search-index.json") if (staging / "search-index.json").exists() else {}
    fields = idx.get("fields", [])
    items = idx.get("items", [])
    if not items:
        problems.append("search-index.json sem itens")
    if items and fields:
        fi = {f: i for i, f in enumerate(fields)}
        for row in items:
            for key in ("a2022", "a2026"):
                v = row[fi[key]]
                if v is not None:
                    if not isinstance(v, (int, float)):
                        problems.append(f"valor não numérico em {key}: {v!r}")
                        break
                    if v < 0:
                        problems.append(
                            f"patrimônio total negativo ({key}={v}) — possível erro de parsing"
                        )
                        break

    # Varredura de dados sensíveis em TODOS os arquivos publicáveis.
    cpf_like = re.compile(r"(?<!\d)\d{11}(?!\d)")
    for path in staging.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        for keypath, key in _iter_keys(data):
            if FORBIDDEN_KEY_RE.search(key):
                problems.append(f"chave sensível '{keypath}' em {path.name}")
        digits_found = set(cpf_like.findall(text))
        leaked = digits_found & sensitive
        if leaked:
            problems.append(f"CPF real detectado em {path.relative_to(staging)}")
        # fora das descrições de bens, nenhum número tipo-CPF é aceitável
        if "candidates/" not in path.as_posix() and any(
            is_valid_cpf(d) for d in digits_found
        ):
            problems.append(
                f"número com checksum de CPF em arquivo de índice: {path.name}"
            )
    return problems


def main(argv: list[str]) -> int:
    config = load_config()
    work_dir = resolve_path(config, "work_dir")
    staging = Path(argv[0]) if argv else work_dir / "staging"
    if not staging.exists():
        print(f"[validate] ERRO: staging inexistente: {staging}")
        return 1

    sensitive: set[str] = set()
    scan_file = work_dir / "sensitive_scan.txt"
    if scan_file.exists():
        sensitive = {l.strip() for l in scan_file.read_text(encoding="utf-8").splitlines() if l.strip()}

    problems = validate_staging(staging, config, sensitive)
    if problems:
        print(f"[validate] FALHA — {len(problems)} problema(s):")
        for p in problems[:50]:
            print(f"  - {p}")
        print("[validate] publicação ABORTADA; dados anteriores preservados.")
        return 1
    n_files = sum(1 for _ in staging.rglob("*.json"))
    print(f"[validate] OK — {n_files} arquivos validados, nenhum dado sensível encontrado")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
