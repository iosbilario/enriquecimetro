"""Utilidades compartilhadas do pipeline do Enriquecímetro.

Somente biblioteca padrão. Todas as funções aqui são puras e testáveis.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "data_sources.json"

# Colunas dos CSVs do TSE que NUNCA podem chegar aos arquivos publicados.
SENSITIVE_COLUMN_PATTERNS = (
    "CPF",
    "TITULO_ELEITORAL",
    "EMAIL",
    "ENDERECO",
    "TELEFONE",
)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_path(config: dict, key: str) -> Path:
    """Resolve um diretório do pipeline; ENRIQ_<KEY> no ambiente sobrepõe."""
    env = os.environ.get(f"ENRIQ_{key.upper()}")
    if env:
        return Path(env)
    return ROOT / config["paths"][key]


def parse_brl(raw: str | None) -> float | None:
    """Converte valor monetário no formato brasileiro do TSE para float.

    Aceita "1234,56", "1.234.567,89", "500000", "-1,00".
    Retorna None para vazio/#NULO#/inválido (o chamador decide o que fazer).
    """
    if raw is None:
        return None
    s = str(raw).strip().strip('"').strip()
    if not s or s in {"#NULO#", "#NE#", "-1", "NULO"}:
        return None
    negative = s.startswith("-")
    s = s.lstrip("+-")
    # Remove separador de milhar e troca vírgula decimal por ponto.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        cents = round(float(s) * 100)
    except ValueError:
        return None
    value = cents / 100.0
    return -value if negative else value


def normalize_name(name: str | None) -> str:
    """Normaliza nome para busca/matching: sem acentos, maiúsculas, espaços únicos."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", stripped).strip().upper()


def is_valid_cpf(cpf: str | None) -> bool:
    """Valida CPF (11 dígitos + dígitos verificadores). Uso interno no ETL."""
    if not cpf:
        return False
    digits = re.sub(r"\D", "", str(cpf))
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        check = (total * 10) % 11 % 10
        if check != int(digits[size]):
            return False
    return True


_CPF_FORMATTED_RE = re.compile(r"\d{3}\.\d{3}\.\d{3}-?\d{2}")
_CPF_BARE_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
REDACTION = "[número pessoal removido]"


def redact_personal_numbers(text: str | None) -> str:
    """Remove CPFs digitados em texto livre (ex.: descrições de bens).

    O TSE publica as descrições cruas; candidatos às vezes incluem CPF de
    terceiros ali. Minimização: redigimos CPFs formatados e qualquer sequência
    de 11 dígitos cujo checksum de CPF seja válido.
    """
    if not text:
        return text or ""
    out = _CPF_FORMATTED_RE.sub(REDACTION, text)
    out = _CPF_BARE_RE.sub(
        lambda m: REDACTION if is_valid_cpf(m.group()) else m.group(), out
    )
    return out


def public_candidate_id(election_year: int, sq_candidato: str) -> str:
    """Gera o identificador público de um candidato.

    Derivado exclusivamente do SQ_CANDIDATO (número sequencial PÚBLICO do TSE)
    e do ano da eleição — nunca de CPF ou outro dado pessoal. Portanto é
    impossível reconstruir CPF a partir do ID.
    """
    basis = f"enr1:{election_year}:{str(sq_candidato).strip()}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def compute_change(assets_before: float | None, assets_after: float | None) -> dict:
    """Calcula variação nominal, percentual e multiplicador.

    percentage/multiple são None quando o patrimônio anterior é 0 ou ausente
    (nunca exibir "infinito %").
    """
    if assets_before is None or assets_after is None:
        return {"absolute": None, "percentage": None, "multiple": None}
    absolute = round(assets_after - assets_before, 2)
    if assets_before > 0:
        percentage = round((assets_after - assets_before) / assets_before * 100, 2)
        multiple = round(assets_after / assets_before, 2)
    else:
        percentage = None
        multiple = None
    return {"absolute": absolute, "percentage": percentage, "multiple": multiple}


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def quartiles(values: list[float]) -> tuple[float, float] | None:
    """Q1 e Q3 pelo método da mediana das metades (Tukey)."""
    if len(values) < 4:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    lower = ordered[:mid]
    upper = ordered[mid + 1:] if n % 2 else ordered[mid:]
    q1 = median(lower)
    q3 = median(upper)
    if q1 is None or q3 is None:
        return None
    return q1, q3


def write_json(path: Path, data, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        if compact:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, fh, ensure_ascii=False, indent=2)


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
