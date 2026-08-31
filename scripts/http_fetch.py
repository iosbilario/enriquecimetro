"""Cliente HTTP resiliente para baixar os datasets do TSE.

Desde agosto/2026 o CDN do TSE (cdn.tse.jus.br, atrás da Akamai) passou a
responder 403 Forbidden a clientes que não apresentam o fingerprint TLS/HTTP
de um navegador real — trocar o User-Agent não basta. A biblioteca curl_cffi
(curl-impersonate) reproduz esse fingerprint e volta a receber 200.

Este módulo expõe duas funções — head() e download() — que usam curl_cffi
quando disponível e caem para urllib como fallback (ambientes de teste sem a
dependência instalada, onde não há download real).
"""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

# UA de navegador, usado tanto pelo curl_cffi quanto pelo fallback urllib.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
# Perfil de fingerprint que o curl_cffi deve imitar.
IMPERSONATE = "chrome"

try:  # pragma: no cover - depende do ambiente
    from curl_cffi import requests as _cffi_requests
except ImportError:  # pragma: no cover
    _cffi_requests = None


def _headers_lower(headers) -> dict:
    return {k.lower(): v for k, v in headers.items()}


def head(url: str, timeout: int = 60) -> dict:
    """Retorna os cabeçalhos da resposta (chaves em minúsculas) de um HEAD."""
    if _cffi_requests is not None:
        resp = _cffi_requests.head(
            url, impersonate=IMPERSONATE, timeout=timeout, allow_redirects=True
        )
        resp.raise_for_status()
        return _headers_lower(resp.headers)
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _headers_lower(resp.headers)


def download(url: str, dest: Path, timeout: int = 300) -> None:
    """Baixa url para dest de forma atômica (grava em .part e renomeia)."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    if _cffi_requests is not None:
        with _cffi_requests.Session() as session:
            resp = session.get(
                url, impersonate=IMPERSONATE, timeout=timeout, stream=True
            )
            resp.raise_for_status()
            with open(tmp, "wb") as out:
                for chunk in resp.iter_content(1 << 20):
                    if chunk:
                        out.write(chunk)
    else:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out, 1 << 20)
    tmp.replace(dest)
