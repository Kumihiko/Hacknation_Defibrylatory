"""Gdańsk – tabela HTML (stan 2022) z adresami, geokodowanymi usługą GUGiK UUG (zwraca też TERYT/SIMC/ULIC)."""

from __future__ import annotations

import html
import json
import logging
import re
import time

from ..config import Source
from ..http import cached, fetch_bytes, fetch_json, raw_path, with_params

log = logging.getLogger(__name__)
UUG_URL = "https://services.gugik.gov.pl/uug/"


def _cell(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def geocode_uug(address: str) -> dict | None:
    try:
        data = fetch_json(with_params(UUG_URL, {"request": "GetAddress", "address": address, "srid": "4326"}), retries=2)
    except Exception as exc:  # noqa: BLE001
        log.warning("UUG: %s (%s)", address, exc)
        return None
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, dict) or "1" not in results:
        return None
    return results["1"]


def fetch(source: Source, offline: bool) -> list[tuple[str, dict]]:
    page = cached(source.id, "html", offline, lambda: fetch_bytes(source.url)).decode("utf-8", errors="replace")
    geo_cache_path = raw_path(source.id + "_geokodowanie", "json")
    geo_cache = json.loads(geo_cache_path.read_text(encoding="utf-8")) if geo_cache_path.exists() else {}

    rows = []
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S)
    for tr in trs[1:]:
        cells = [_cell(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) < 5 or not cells[1]:
            continue
        lp, adres, opis, polozenie, godziny = cells[:5]
        obiekt = re.search(r"\(([^)]+)\)", adres)
        ulica = re.sub(r"\(.*?\)", "", adres)
        ulica = ulica.split(",")[-1] if "," in ulica else ulica
        ulica = re.sub(r"\bul\.\s*", "", ulica).strip(" -")
        query = f"Gdańsk, {ulica}"
        if query not in geo_cache and not offline:
            geo_cache[query] = geocode_uug(query)
            time.sleep(0.2)
        hit = geo_cache.get(query)
        if not hit:
            continue
        pol = polozenie.lower()
        fields = {
            "nazwa_obiektu": obiekt.group(1).strip() if obiekt else ulica,
            "ulica_nazwa": hit.get("street"),
            "nr_budynku": hit.get("number"),
            "kod_pocztowy": hit.get("code"),
            "miejscowosc": hit.get("city") or "Gdańsk",
            "kod_terc": hit.get("teryt"),
            "kod_simc": hit.get("simc"),
            "kod_ulic": hit.get("ulic"),
            "opis_lokalizacji": opis,
            "godziny_opis_zrodlowy": godziny or None,
            "wewnatrz_budynku": False if pol.startswith("na zewn") else (True if pol.startswith("wewn") else None),
            # lista miasta obejmuje AED w przestrzeni publicznej: urządzenie na zewnątrz = publiczne
            "typ_dostepu": "mobilny" if ("pojeźd" in pol or "pojazd" in pol) else ("publiczny" if pol.startswith("na zewn") else None),
            "szerokosc_geo": float(hit["y"]),
            "dlugosc_geo": float(hit["x"]),
        }
        rows.append((lp or str(len(rows) + 1), fields))
    geo_cache_path.write_text(json.dumps(geo_cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows
