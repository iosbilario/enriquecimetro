"""Baixa os datasets oficiais do Portal de Dados Abertos do TSE.

Uso: python scripts/download.py [--force]

Os ZIPs vão para data_raw/ (gitignored). Um manifesto data_raw/manifest.json
registra URL, data de download e Last-Modified informado pelo servidor.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from common import load_config, resolve_path

USER_AGENT = "Enriquecimetro/1.0 (projeto open-source de transparencia; github)"
TIMEOUT = 300


def _head(url: str) -> dict:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return {k.lower(): v for k, v in resp.headers.items()}


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def main(argv: list[str]) -> int:
    force = "--force" in argv
    config = load_config()
    raw_dir = resolve_path(config, "download_dir")
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    failures = []
    for year in config["elections"]:
        datasets = config["datasets"].get(str(year))
        if not datasets:
            print(f"[download] AVISO: eleição {year} sem URLs em config/data_sources.json")
            continue
        for kind, url in datasets.items():
            dest = raw_dir / f"{kind}_{year}.zip"
            entry = manifest.get(dest.name, {})
            try:
                headers = _head(url)
            except Exception as exc:  # noqa: BLE001
                print(f"[download] ERRO ao consultar {url}: {exc}")
                if dest.exists():
                    print(f"[download] mantendo arquivo já baixado: {dest.name}")
                    continue
                failures.append(url)
                continue
            remote_mod = headers.get("last-modified", "")
            remote_len = headers.get("content-length", "")
            unchanged = (
                dest.exists()
                and not force
                and entry.get("last_modified") == remote_mod
                and str(dest.stat().st_size) == remote_len
            )
            if unchanged:
                print(f"[download] {dest.name}: sem mudanças no servidor, pulando")
                continue
            print(f"[download] baixando {url} -> {dest.name} ({remote_len} bytes)")
            try:
                _download(url, dest)
            except Exception as exc:  # noqa: BLE001
                print(f"[download] ERRO ao baixar {url}: {exc}")
                if not dest.exists():
                    failures.append(url)
                continue
            manifest[dest.name] = {
                "url": url,
                "election": year,
                "kind": kind,
                "last_modified": remote_mod,
                "content_length": remote_len,
                "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if failures:
        print(f"[download] FALHA: {len(failures)} arquivo(s) indisponíveis: {failures}")
        return 1
    print("[download] concluído")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
