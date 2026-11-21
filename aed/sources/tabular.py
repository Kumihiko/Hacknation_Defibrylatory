"""Generyczne konektory: CSV, GeoJSON, ArcGIS FeatureServer, KML. Pola mapowane przez config/sources.yaml."""

from __future__ import annotations

import csv
import io
import json
import re

from ..config import Source
from ..http import cached, fetch_bytes, with_params
from ..normalize.coords import puwg1992_to_wgs84
from .mapping import apply


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1250", "iso-8859-2"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_csv(source: Source, offline: bool) -> list[tuple[str, dict]]:
    text = _decode(cached(source.id, "csv", offline, lambda: fetch_bytes(source.url)))
    lines = text.splitlines()
    if source.extra.get("unwrap_quoted_lines"):
        # każdy wiersz w całości w cudzysłowie, a cudzysłowy wewnętrzne podwojone
        lines = [ln[1:-1].replace('""', '"') if ln.startswith('"') and ln.endswith('"') else ln for ln in lines]
    sample = "\n".join(lines[:5])
    delimiter = max([",", ";", "\t", "|"], key=sample.count)
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter, skipinitialspace=True)
    rows = []
    for i, row in enumerate(reader, start=1):
        props = {(k or "").strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        rows.append((str(i), apply(source.mapping, props)))
    return rows


def _features_to_rows(source: Source, features: list[dict], crs: str | None = None) -> list[tuple[str, dict]]:
    rows = []
    for i, feat in enumerate(features, start=1):
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point" or not geom.get("coordinates"):
            continue
        x, y = geom["coordinates"][:2]
        if crs and crs.upper().endswith("2180"):
            lat, lon = puwg1992_to_wgs84(x, y)
        else:
            lon, lat = x, y
        props = feat.get("properties") or {}
        fields = apply(source.mapping, props)
        fields["szerokosc_geo"], fields["dlugosc_geo"] = lat, lon
        key = str(props.get("id") or props.get("OBJECTID") or props.get("objectid") or feat.get("id") or i)
        rows.append((key, fields))
    return rows


def fetch_geojson(source: Source, offline: bool) -> list[tuple[str, dict]]:
    data = json.loads(_decode(cached(source.id, "geojson", offline, lambda: fetch_bytes(source.url))))
    crs = source.extra.get("crs") or ((data.get("crs") or {}).get("properties") or {}).get("name")
    return _features_to_rows(source, data.get("features", []), crs)


def fetch_arcgis(source: Source, offline: bool) -> list[tuple[str, dict]]:
    def produce() -> bytes:
        features, offset = [], 0
        while True:
            page = json.loads(fetch_bytes(with_params(source.url.rstrip("/") + "/query", {
                "where": "1=1", "outFields": "*", "f": "geojson", "outSR": 4326,
                "resultOffset": offset, "resultRecordCount": 1000})))
            features += page.get("features", [])
            if not (page.get("properties") or {}).get("exceededTransferLimit"):
                break
            offset += 1000
        return json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False).encode()

    data = json.loads(cached(source.id, "geojson", offline, produce).decode("utf-8"))
    return _features_to_rows(source, data.get("features", []))


def fetch_kml(source: Source, offline: bool) -> list[tuple[str, dict]]:
    text = _decode(cached(source.id, "kml", offline, lambda: fetch_bytes(source.url)))
    rows = []
    for i, pm in enumerate(re.findall(r"<Placemark>(.*?)</Placemark>", text, re.S), start=1):
        coords = re.search(r"<coordinates>\s*([-\d.]+),([-\d.]+)", pm)
        if not coords:
            continue
        name = re.search(r"<name>(.*?)</name>", pm, re.S)
        desc = re.search(r"<description>(.*?)</description>", pm, re.S)
        props = {
            "name": " ".join((name.group(1) if name else "").split()),
            "description": (desc.group(1) if desc else "").replace("<![CDATA[", "").replace("]]>", "").strip(),
        }
        fields = apply(source.mapping, props)
        fields["dlugosc_geo"], fields["szerokosc_geo"] = float(coords.group(1)), float(coords.group(2))
        rows.append((str(i), fields))
    return rows
