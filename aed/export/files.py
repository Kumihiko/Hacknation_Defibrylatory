"""Eksport zbioru: CSV (RFC 4180, UTF-8), GeoJSON, kompaktowy JSON dla aplikacji, statystyki."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..normalize.availability import ROUTABLE

CLASS_CODES = {k: i for i, k in enumerate(ROUTABLE)}  # 0=24h_pewny, 1=24h_wnioskowany, 2=godziny


def csv_value(value: Any) -> str:
    """Formatowanie wg Standardu technicznego dane.gov.pl: true/false, kropka dziesiętna, puste = brak."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def write_csv(records: list[dict], fields: list[str], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writerow(fields)
        for r in records:
            writer.writerow([csv_value(r.get(f)) for f in fields])


def write_geojson(records: list[dict], fields: list[str], path: Path, meta: dict[str, Any]) -> None:
    features = [{
        "type": "Feature",
        "id": r["id"],
        "geometry": {"type": "Point", "coordinates": [r["dlugosc_geo"], r["szerokosc_geo"]]},
        "properties": {f: r.get(f) for f in fields if f not in ("szerokosc_geo", "dlugosc_geo") and r.get(f) not in (None, "")},
    } for r in records]
    doc = {"type": "FeatureCollection", "metadata": meta, "features": features}
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def write_web_json(records: list[dict], path: Path, meta: dict[str, Any]) -> int:
    """Tylko AED, do których aplikacja może poprowadzić (klasy 24h_pewny, 24h_wnioskowany, godziny)."""
    rows = []
    for r in records:
        klasa = r["klasa_dostepnosci"]
        if klasa not in CLASS_CODES:
            continue
        hours = r["_hours"]
        week = [list(t) for t in hours.week] if hours.week else 0
        inside = r.get("wewnatrz_budynku")
        rows.append([
            r["szerokosc_geo"], r["dlugosc_geo"], CLASS_CODES[klasa], week,
            r.get("nazwa_obiektu") or "", r.get("opis_lokalizacji") or "",
            r.get("pietro"), None if inside is None else int(inside),
            r.get("godziny_dostepnosci") or "", r["zrodla"], r["data_danych"], r["id"],
            " ".join(x for x in (r.get("ulica_cecha"), r.get("ulica_nazwa"), r.get("nr_budynku")) if x) +
            (", " + r["miejscowosc"] if r.get("miejscowosc") else ""),
        ])
    doc = {
        "meta": meta,
        "columns": ["lat", "lon", "klasa", "tydzien", "nazwa", "opis", "pietro", "wewnatrz",
                    "godziny", "zrodla", "data_danych", "id", "adres"],
        "klasy": list(CLASS_CODES),
        "rows": rows,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(rows)


def build_stats(per_source: dict[str, list[dict]], merged: list[dict], dedupe_report: dict[str, Any],
                sources: list, generated: str) -> dict[str, Any]:
    def summarize(recs: list[dict]) -> dict[str, Any]:
        n = len(recs)
        classes = Counter(r["klasa_dostepnosci"] for r in recs)
        with_hours = sum(1 for r in recs if r.get("dostepny_24_7") is True or r.get("godziny_dostepnosci"))
        return {
            "rekordow": n,
            "z_informacja_o_godzinach": with_hours,
            "procent_z_godzinami": round(100 * with_hours / n, 1) if n else 0,
            "klasy_dostepnosci": dict(classes.most_common()),
        }

    return {
        "wygenerowano": generated,
        "zbior": summarize(merged),
        "deduplikacja": dedupe_report,
        "zrodla": [{
            "id": s.id, "nazwa": s.name, "wydawca": s.publisher, "licencja": s.license,
            "atrybucja": s.attribution, "strona": s.homepage, "url_danych": s.url, "wlaczone": s.enabled,
            **({"statystyki": summarize(per_source[s.id])} if s.id in per_source else {}),
        } for s in sources],
    }
