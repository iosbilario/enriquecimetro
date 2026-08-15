"""Orquestrador do pipeline completo do Enriquecímetro.

Uso: python scripts/run_pipeline.py [--skip-download]

Etapas: download -> transform -> match -> generate (staging) -> validate ->
publish. A publicação só acontece se a validação passar; caso contrário os
dados anteriores em public/data permanecem intactos.
"""
from __future__ import annotations

import shutil
import sys
import time

import download
import generate_pages
import generate_site_data
import match_candidates
import transform
import validate
from common import load_config, resolve_path


def _rmtree_robust(path) -> None:
    """rmtree tolerante a locks transitórios do Windows/OneDrive."""
    for attempt in range(5):
        try:
            shutil.rmtree(path)
            return
        except (PermissionError, OSError):
            time.sleep(0.5 * (attempt + 1))
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        print(f"[publish] AVISO: não foi possível remover {path}; remova manualmente")


def publish(config: dict) -> int:
    staging = resolve_path(config, "work_dir") / "staging"
    output = resolve_path(config, "output_dir")
    tmp_old = output.parent / (output.name + ".old")
    output.parent.mkdir(parents=True, exist_ok=True)
    if tmp_old.exists():
        _rmtree_robust(tmp_old)
    if output.exists():
        output.rename(tmp_old)
    shutil.copytree(staging, output)
    if tmp_old.exists():
        _rmtree_robust(tmp_old)
    print(f"[publish] dados publicados em {output}")
    return 0


def main(argv: list[str]) -> int:
    config = load_config()
    if "--skip-download" not in argv:
        rc = download.main([])
        if rc != 0:
            print("[pipeline] download falhou; abortando sem tocar nos dados publicados")
            return rc
    for step in (transform.main, match_candidates.main, generate_site_data.main):
        rc = step()
        if rc != 0:
            print(f"[pipeline] etapa {step.__module__} falhou; abortando")
            return rc
    rc = validate.main([])
    if rc != 0:
        return rc
    rc = publish(config)
    if rc != 0:
        return rc
    # Pré-renderização de páginas estáticas (SEO/GEO) a partir dos dados publicados.
    return generate_pages.main()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
