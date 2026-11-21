"""Pobieranie danych przez HTTP (biblioteka standardowa) z ponawianiem i zapisem surowych odpowiedzi."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import RAW_DIR

log = logging.getLogger(__name__)

USER_AGENT = "misja-aed/0.1 (+https://github.com/; agregator otwartych danych AED)"


def fetch_bytes(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None,
                timeout: int = 60, retries: int = 3) -> bytes:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    hdrs.update(headers or {})
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data is not None else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            code = getattr(exc, "code", None)
            if code is not None and 400 <= code < 500 and code != 429:
                break
            log.warning("Błąd pobierania %s (próba %d/%d): %s", url, attempt, retries, exc)
            time.sleep(2 * attempt)
    raise RuntimeError(f"Nie udało się pobrać {url}: {last_exc}")


def fetch_json(url: str, **kwargs: Any) -> Any:
    return json.loads(fetch_bytes(url, **kwargs).decode("utf-8-sig"))


def with_params(url: str, params: dict[str, Any]) -> str:
    sep = "&" if "?" in url else "?"
    return url + sep + urllib.parse.urlencode(params)


def raw_path(source_id: str, ext: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{source_id}.{ext}"


def cached(source_id: str, ext: str, offline: bool, producer) -> bytes:
    """Zwraca surowe dane źródła: z pliku (offline) albo pobrane przez producer() i zapisane w data/raw."""
    path = raw_path(source_id, ext)
    if offline:
        if not path.exists():
            raise FileNotFoundError(f"Brak surowych danych {path} – uruchom bez --offline")
        return path.read_bytes()
    content = producer()
    path.write_bytes(content)
    return content
