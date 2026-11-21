"""Pipeline: pobranie źródeł -> normalizacja -> deduplikacja -> eksporty dla dane.gov.pl i aplikacji."""

from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import datetime, timezone
from typing import Any

from . import dedupe
from .config import OUT_DIR, ROOT, WEB_DIR, Source, field_names, load_env, load_schema, load_settings, load_sources
from .export import csvw, danegov_xml, files, xlsx
from .normalize.coords import haversine_m
from .record import build_record
from .sources import fetch_source

log = logging.getLogger(__name__)

RESOURCES = [
    ("csv", "aed.csv", "CSV", "Zbiór w formacie CSV (UTF-8, RFC 4180) zgodny ze wzorcowym zakresem danych HeartSpot."),
    ("geojson", "aed.geojson", "GeoJSON", "Zbiór w formacie GeoJSON (WGS84) do wykorzystania w systemach GIS i mapach."),
    ("xlsx", "aed.xlsx", "XLSX", "Zbiór w formacie arkusza XLSX wraz z opisem pól i listą źródeł."),
]


def _drop_outliers(src: Source, recs: list[dict], max_km: float = 50.0) -> list[dict]:
    """Źródła lokalne (gmina, miasto): odrzuca punkty odległe od mediany źródła – zwykle błędnie skopiowane
    współrzędne (np. w pliku Marek jeden wiersz ma współrzędne z Krosna)."""
    if src.extra.get("scope", "lokalny") != "lokalny" or len(recs) < 5:
        return recs
    lat = statistics.median(r["szerokosc_geo"] for r in recs)
    lon = statistics.median(r["dlugosc_geo"] for r in recs)
    kept = []
    for r in recs:
        if haversine_m(lat, lon, r["szerokosc_geo"], r["dlugosc_geo"]) > max_km * 1000:
            log.warning("%s: odrzucono %s – współrzędne %.5f,%.5f daleko od obszaru źródła (%s)",
                        src.id, r["zrodlo_id"], r["szerokosc_geo"], r["dlugosc_geo"], r.get("nazwa_obiektu"))
            continue
        kept.append(r)
    return kept


def _load_records(sources: list[Source], offline: bool, data_date: str) -> tuple[list[dict], dict[str, list[dict]], list[str]]:
    records: list[dict] = []
    per_source: dict[str, list[dict]] = {}
    errors: list[str] = []
    for src in sources:
        t0 = time.time()
        try:
            rows = fetch_source(src, offline)
        except Exception as exc:  # noqa: BLE001 – błąd jednego źródła nie zatrzymuje całości
            if not offline:
                log.warning("Źródło %s: %s – próbuję danych z poprzedniego pobrania", src.id, exc)
                try:
                    rows = fetch_source(src, True)
                except Exception as exc2:  # noqa: BLE001
                    errors.append(f"{src.id}: {exc2}")
                    log.error("Źródło %s pominięte: %s", src.id, exc2)
                    continue
            else:
                errors.append(f"{src.id}: {exc}")
                log.error("Źródło %s pominięte: %s", src.id, exc)
                continue
        recs = [r for key, fields in rows if (r := build_record(src, key, fields, data_date)) is not None]
        recs = _drop_outliers(src, recs)
        per_source[src.id] = recs
        records.extend(recs)
        log.info("%-24s %6d rekordów (%d odrzuconych bez współrzędnych) w %.1fs",
                 src.id, len(recs), len(rows) - len(recs), time.time() - t0)
    return records, per_source, errors


def run(offline: bool = False, enable: list[str] | None = None) -> dict[str, Any]:
    load_env()
    settings = load_settings()
    schema = load_schema()
    fields = field_names()
    all_sources = load_sources(include_disabled=True)
    for s in all_sources:
        if enable and s.id in enable:
            s.enabled = True
    sources = [s for s in all_sources if s.enabled]

    now = datetime.now(timezone.utc).replace(microsecond=0)
    generated = now.isoformat().replace("+00:00", "Z")
    data_date = now.date().isoformat()

    records, per_source, errors = _load_records(sources, offline, data_date)
    merged, report = dedupe.deduplicate(records, settings.get("dedupe", {}))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / "data").mkdir(parents=True, exist_ok=True)
    meta = {
        "tytul": settings["dataset"]["title_pl"], "wygenerowano": generated, "licencja": "ODbL-1.0",
        "atrybucja": [s.attribution for s in sources], "rekordow": len(merged),
    }
    files.write_csv(merged, fields, OUT_DIR / "aed.csv")
    files.write_geojson(merged, fields, OUT_DIR / "aed.geojson", meta)
    xlsx.write_full(OUT_DIR / "aed.xlsx", schema, merged, all_sources)
    xlsx.write_template(OUT_DIR / "wzorcowy-zakres-danych-AED.xlsx", schema, merged, all_sources)
    # kopia w repozytorium – plik wymagany w zgłoszeniu konkursowym
    xlsx.write_template(ROOT / "schema" / "wzorcowy-zakres-danych-AED.xlsx", schema, merged, all_sources)
    csvw.write(schema, "aed.csv", settings, generated, OUT_DIR / "aed.csv-metadata.json")
    (OUT_DIR / "aed.schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")

    base = settings["publish_base_url"].rstrip("/") + "/dane/"
    ds = settings["dataset"]
    resources = [{
        "ext_ident": f"{ds['ext_ident'][:28]}-{ext}",
        "url": base + name,
        "title_pl": f"{ds['title_pl']} ({label})",
        "title_en": f"{ds['title_en']} ({label})",
        "description_pl": desc,
        "description_en": f"{ds['title_en']} – {label} file.",
    } for ext, name, label, desc in RESOURCES]
    danegov_xml.write(settings, resources, data_date, generated, OUT_DIR / "danegov-import.xml")

    web_count = files.write_web_json(merged, WEB_DIR / "data" / "aed.json", meta)
    stats = files.build_stats(per_source, merged, report, all_sources, generated)
    stats["aplikacja_rekordow"] = web_count
    stats["bledy_zrodel"] = errors
    (OUT_DIR / "zrodla.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Zapisano eksporty w %s", OUT_DIR.relative_to(ROOT))
    return stats


def print_report(stats: dict[str, Any]) -> None:
    z = stats["zbior"]
    d = stats["deduplikacja"]
    print("\n=== HeartSpot – raport ===")
    print(f"Wygenerowano: {stats['wygenerowano']}")
    print(f"Rekordy wejściowe: {d['rekordow_wejsciowych']}  ->  po deduplikacji: {d['rekordow_po_deduplikacji']}"
          f"  (połączono {d['polaczonych_klastrow']} klastrów)")
    for pair, n in list(d["polaczenia_wg_zrodel"].items())[:8]:
        print(f"   {pair:40s} {n}")
    print(f"Z informacją o godzinach/24h: {z['z_informacja_o_godzinach']} ({z['procent_z_godzinami']}%)")
    print("Klasy dostępności:", ", ".join(f"{k}={v}" for k, v in z["klasy_dostepnosci"].items()))
    print(f"Do aplikacji (AED, do których można poprowadzić): {stats['aplikacja_rekordow']}")
    print("Źródła:")
    for s in stats["zrodla"]:
        st = s.get("statystyki")
        mark = "✔" if s["wlaczone"] else "·"
        info = f"{st['rekordow']:6d} rek., {st['procent_z_godzinami']:5.1f}% z godzinami" if st else "     – (wyłączone)"
        print(f"  {mark} {s['id']:24s} {s['licencja']:10s} {info}")
    if stats["bledy_zrodel"]:
        print("Błędy:", *stats["bledy_zrodel"], sep="\n  ")
