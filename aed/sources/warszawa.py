"""m.st. Warszawa – API Stołecznego Centrum Bezpieczeństwa (token) z zapasową kopią ArcGIS (Esri Polska)."""

from __future__ import annotations

import json
import logging
import os

from ..config import Source
from ..http import cached, fetch_bytes, with_params

log = logging.getLogger(__name__)


def _map(p: dict) -> dict:
    """Pola API (device_*/location_*) i kopii ArcGIS (krótsze nazwy) -> schemat."""
    g = lambda *keys: next((p[k] for k in keys if p.get(k) not in (None, "")), None)  # noqa: E731
    availability = (g("device_availability", "availability") or "").strip().lower()
    location = (g("device_location", "device_loc") or "").strip().lower()
    return {
        "nazwa_obiektu": g("location_object_name", "object_name"),
        "ulica_nazwa": g("location_street", "street"),
        "nr_budynku": g("location_building", "building_no"),
        "kod_pocztowy": g("location_postcode", "postcode"),
        "miejscowosc": g("location_city", "city"),
        "opis_lokalizacji": g("location_description", "location_desc"),
        "godziny_opis_zrodlowy": g("device_access_description", "access_desc"),
        "_dostepny_24_7": True if availability == "tak" else None,
        "typ_dostepu": g("device_public_access", "public_access"),
        "wewnatrz_budynku": True if location.startswith("wewn") else (False if location.startswith("na zewn") else None),
        "producent": g("device_manufacturer", "manufacturer"),
    }


def _from_api(source: Source, token: str) -> bytes:
    return fetch_bytes(source.url, data=b"{}", headers={"Authorization": token, "Content-Type": "application/json"})


def _from_mirror(url: str) -> bytes:
    features, offset = [], 0
    while True:
        page = json.loads(fetch_bytes(with_params(url + "/query", {
            "where": "1=1", "outFields": "*", "f": "geojson", "outSR": 4326,
            "resultOffset": offset, "resultRecordCount": 1000})))
        features += page.get("features", [])
        if not page.get("properties", {}).get("exceededTransferLimit") and not page.get("exceededTransferLimit"):
            break
        offset += 1000
    return json.dumps({"type": "FeatureCollection", "features": features, "_mirror": True}, ensure_ascii=False).encode()


def fetch(source: Source, offline: bool) -> list[tuple[str, dict]]:
    token = os.environ.get(source.extra.get("token_env", "WAW_API_TOKEN"), "")

    def produce() -> bytes:
        if token:
            try:
                return _from_api(source, token)
            except Exception as exc:  # noqa: BLE001
                log.warning("API Warszawy niedostępne (%s) – używam kopii ArcGIS", exc)
        else:
            log.info("Brak tokenu %s – dane Warszawy z publicznej kopii ArcGIS", source.extra.get("token_env"))
        return _from_mirror(source.extra["fallback_url"])

    data = json.loads(cached(source.id, "json", offline, produce).decode("utf-8-sig"))
    features = data.get("features", data) if isinstance(data, dict) else data
    rows = []
    for feat in features:
        props = feat.get("properties") or feat.get("attributes") or {}
        coords = (feat.get("geometry") or {}).get("coordinates")
        if coords and isinstance(coords[0], list):  # API zwraca [[lon, lat]]
            coords = coords[0]
        if not coords:
            continue
        fields = _map(props)
        fields["dlugosc_geo"], fields["szerokosc_geo"] = coords[:2]
        key = str(props.get("defibrillator_id") or props.get("defib_id") or props.get("OBJECTID"))
        rows.append((key, fields))
    return rows
