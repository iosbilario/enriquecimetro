"""Baixa as fotos oficiais de urna (dataset foto_cand do TSE) e gera
miniaturas WebP apenas para candidatos com comparação entre eleições.

Uso: python scripts/fetch_photos.py [--force]

Requer Pillow (única dependência opcional do projeto — ver requirements.txt).
Pré-requisito: transform + match já executados (data_work/ populado).

Decisões:
  - Somente candidatos com match "exact"/"probable" ganham foto (são os que
    aparecem em rankings e comparações) — mantém o site dentro dos limites
    do GitHub Pages.
  - Miniaturas de 96 px em WebP (~3-5 KB cada), nomeadas pelo ID público
    ({id}.webp) — nenhum dado pessoal no nome do arquivo.
  - A foto usada é a da eleição mais recente (2026).
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from common import ROOT, load_config, read_json, resolve_path

USER_AGENT = "Enriquecimetro/1.0 (projeto open-source de transparencia; github)"

# Nome no ZIP: F{UF}{SQ_CANDIDATO}_div.jpg  (ex.: FAC10002544107_div.jpg)
PHOTO_NAME_RE = re.compile(r"F[A-Z]{2}(\d+)_div\.(jpe?g|png)$", re.IGNORECASE)


def sq_from_photo_name(name: str) -> str | None:
    """Extrai o SQ_CANDIDATO do nome de arquivo de foto do TSE."""
    m = PHOTO_NAME_RE.search(name)
    return m.group(1) if m else None


def index_photos_by_sq(names: list[str]) -> dict[str, str]:
    """Mapeia SQ_CANDIDATO -> nome do arquivo dentro do ZIP."""
    index = {}
    for n in names:
        sq = sq_from_photo_name(n)
        if sq:
            index[sq] = n
    return index


def make_thumbnail(jpeg_bytes: bytes, size_px: int) -> bytes:
    from PIL import Image  # import tardio: única dependência externa

    img = Image.open(io.BytesIO(jpeg_bytes))
    img = img.convert("RGB")
    # corte central quadrado antes do resize
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2,
                    (w + side) // 2, (h + side) // 2))
    img = img.resize((size_px, size_px), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=72, method=6)
    return out.getvalue()


def download_zip(url: str, dest: Path) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as fh:
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[photos] AVISO: falha ao baixar {url}: {exc}")
        return False


def main(argv: list[str]) -> int:
    force = "--force" in argv
    config = load_config()
    pconf = config.get("photos")
    if not pconf:
        print("[photos] config.photos ausente; nada a fazer")
        return 0
    year = pconf["election"]
    statuses = set(pconf.get("match_statuses", ["exact"]))
    size_px = pconf.get("thumbnail_px", 96)

    work_dir = resolve_path(config, "work_dir")
    raw_dir = resolve_path(config, "download_dir") / "photos"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir = ROOT / pconf.get("output_dir", "public/photos")
    out_dir.mkdir(parents=True, exist_ok=True)

    persons = read_json(work_dir / "persons.json")
    election = read_json(work_dir / f"election_{year}.json")["candidates"]

    # id público -> (uf, sq) da eleição de referência
    wanted: dict[str, tuple[str, str]] = {}
    for p in persons:
        if p["match_status"] not in statuses:
            continue
        sq = p["elections"].get(str(year))
        cand = election.get(sq) if sq else None
        if cand and cand.get("uf"):
            wanted[p["id"]] = (cand["uf"], sq)

    by_uf: dict[str, dict[str, str]] = {}
    for pid, (uf, sq) in wanted.items():
        by_uf.setdefault(uf, {})[sq] = pid

    generated = skipped = missing = 0
    for uf in sorted(by_uf):
        url = pconf["url_template"].format(year=year, uf=uf)
        zip_path = raw_dir / f"foto_{year}_{uf}.zip"
        if force or not zip_path.exists():
            print(f"[photos] baixando {uf}: {url}")
            if not download_zip(url, zip_path):
                missing += len(by_uf[uf])
                continue
        try:
            zf = zipfile.ZipFile(zip_path)
        except zipfile.BadZipFile:
            print(f"[photos] AVISO: zip corrompido para {uf}; pulando")
            missing += len(by_uf[uf])
            continue
        with zf:
            photo_index = index_photos_by_sq(zf.namelist())
            for sq, pid in by_uf[uf].items():
                dest = out_dir / f"{pid}.webp"
                if dest.exists() and not force:
                    skipped += 1
                    continue
                name = photo_index.get(sq)
                if not name:
                    missing += 1
                    continue
                try:
                    dest.write_bytes(make_thumbnail(zf.read(name), size_px))
                    generated += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"[photos] AVISO: erro ao processar {name}: {exc}")
                    missing += 1

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "election": year,
        "source_template": pconf["url_template"],
        "thumbnail_px": size_px,
        "eligible": len(wanted),
        "generated_now": generated,
        "already_present": skipped,
        "missing": missing,
        "note": "Fotos oficiais de urna publicadas pelo TSE (Portal de Dados "
                "Abertos). Miniaturas geradas apenas para candidaturas com "
                "correspondência entre eleições.",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[photos] elegíveis={len(wanted)} novas={generated} "
          f"existentes={skipped} sem_foto={missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
