"""OpenStreetMap przez OpenAEDMap: GeoJSON wszystkich węzłów emergency=defibrillator w Polsce (ODbL)."""

from __future__ import annotations

import json
import re

from ..config import Source
from ..http import cached, fetch_bytes
from ..normalize.availability import access_from_osm


def _first(tags: dict, *keys: str):
    for k in keys:
        v = tags.get(k)
        if v not in (None, ""):
            return v
    return None


def _date(value: str | None) -> str | None:
    if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return value.strip()
    return None


def _indoor(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    if v in ("yes", "room", "area", "corridor", "true"):
        return True
    if v in ("no", "false"):
        return False
    return None


def map_tags(tags: dict) -> dict:
    links = []
    if tags.get("ref:api-um-warszawa-pl"):
        links.append(f"um_warszawa:{tags['ref:api-um-warszawa-pl'].strip()}")
    return {
        "nazwa_obiektu": _first(tags, "name", "name:pl", "operator", "description"),
        "opis_lokalizacji": _first(tags, "defibrillator:location:pl", "defibrillator:location", "location", "description:pl"),
        "_osm_opening_hours": tags.get("opening_hours"),
        "typ_dostepu": access_from_osm(tags.get("access")),
        "wewnatrz_budynku": _indoor(tags.get("indoor")),
        "pietro": _first(tags, "level", "level:ref"),
        "dysponent_nazwa": tags.get("operator"),
        "dysponent_telefon": _first(tags, "phone", "contact:phone"),
        "producent": tags.get("manufacturer"),
        "model": tags.get("model"),
        "ulica_nazwa": tags.get("addr:street"),
        "nr_budynku": tags.get("addr:housenumber"),
        "kod_pocztowy": tags.get("addr:postcode"),
        "miejscowosc": _first(tags, "addr:city", "addr:place"),
        "data_weryfikacji": _date(_first(tags, "check_date", "survey:date")),
        "_links": links,
    }


def fetch(source: Source, offline: bool) -> list[tuple[str, dict]]:
    raw = cached(source.id, "geojson", offline, lambda: fetch_bytes(source.url, timeout=180))
    data = json.loads(raw.decode("utf-8"))
    rows = []
    for feat in data.get("features", []):
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        tags = feat.get("properties") or {}
        fields = map_tags(tags)
        fields["dlugosc_geo"], fields["szerokosc_geo"] = geom["coordinates"][:2]
        key = f"{tags.get('@osm_type', 'node')}/{tags.get('@osm_id')}"
        rows.append((key, fields))
    return rows
