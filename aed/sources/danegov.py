"""dane.gov.pl – automatyczne wyszukiwanie zbiorów dysponentów opublikowanych we wzorcowym zakresie HeartSpot.

Dysponent przygotowuje plik w zakładce „Dodaj AED”, publikuje go na dane.gov.pl, a ten konektor znajduje go
przez API portalu (wyszukiwanie po słowach kluczowych), rozpoznaje po nagłówku zgodnym ze schematem
i włącza do zbioru – z licencją podaną przy zbiorze na dane.gov.pl.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re

from ..config import Source, field_names, load_settings
from ..http import cached, fetch_bytes, fetch_json, with_params

log = logging.getLogger(__name__)
API = "https://api.dane.gov.pl/1.4"
REQUIRED_COLUMNS = {"nazwa_obiektu", "szerokosc_geo", "dlugosc_geo"}
_LICENSES = {"CC0 1.0": "CC0-1.0", "CC BY 4.0": "CC-BY-4.0", "CC BY-SA 4.0": "CC-BY-SA-4.0"}


def _discover(queries: list[str]) -> list[dict]:
    """Zwraca listę zasobów CSV (id, url, dataset_id, tytuł zbioru, licencja) pasujących do zapytań."""
    seen: dict[str, dict] = {}
    for q in queries:
        data = fetch_json(with_params(f"{API}/search", {"q": q, "per_page": 100}))
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            if attrs.get("model") != "resource" or str(attrs.get("format", "")).lower() != "csv":
                continue
            seen.setdefault(item["id"], {"id": item["id"]})
    resources = []
    for rid in seen:
        try:
            res = fetch_json(f"{API}/resources/{rid}?include=dataset")
        except Exception as exc:  # noqa: BLE001
            log.warning("dane.gov.pl: zasób %s niedostępny (%s)", rid, exc)
            continue
        attrs = res["data"]["attributes"]
        ds = next((x for x in res.get("included", []) if x.get("type") == "dataset"), {})
        ds_attrs = ds.get("attributes", {})
        resources.append({
            "id": rid,
            "url": attrs.get("download_url") or attrs.get("link"),
            "dataset_id": ds.get("id"),
            "dataset_title": ds_attrs.get("title", ""),
            "license": _LICENSES.get(ds_attrs.get("license_name") or "", ds_attrs.get("license_name") or "NIEZNANA"),
            "data_date": attrs.get("data_date"),
        })
    return resources


def fetch(source: Source, offline: bool) -> list[tuple[str, dict]]:
    own_title = load_settings()["dataset"]["title_pl"]
    queries = source.extra.get("queries", ["defibrylator", "defibrylatory", "AED"])

    def produce() -> bytes:
        bundle = []
        for res in _discover(queries):
            if not res["url"] or re.sub(r"<[^>]+>", "", res["dataset_title"]) == own_title:
                continue  # pomijamy własny zbiór zintegrowany (unikamy pętli)
            try:
                text = fetch_bytes(res["url"]).decode("utf-8-sig", errors="replace")
            except Exception as exc:  # noqa: BLE001
                log.warning("dane.gov.pl: nie pobrano %s (%s)", res["url"], exc)
                continue
            header = next(csv.reader(io.StringIO(text.splitlines()[0] if text else "")), [])
            if REQUIRED_COLUMNS <= {h.strip() for h in header}:
                bundle.append({**res, "csv": text})
        return json.dumps(bundle, ensure_ascii=False).encode("utf-8")

    bundle = json.loads(cached(source.id, "json", offline, produce).decode("utf-8"))
    names = set(field_names())
    rows: list[tuple[str, dict]] = []
    for res in bundle:
        reader = csv.DictReader(io.StringIO(res["csv"]))
        n = 0
        for i, row in enumerate(reader, start=1):
            fields = {k.strip(): (v or "").strip() for k, v in row.items() if k and k.strip() in names}
            # pola wyliczane i proweniencję ustala nasz pipeline – nie ufamy wartościom z pliku
            for k in ("klasa_dostepnosci", "zrodla", "zrodlo_id", "zrodlo_licencja", "id", "dostepny_24_7"):
                fields.pop(k, None)
            if fields.get("godziny_dostepnosci") and not fields.get("godziny_opis_zrodlowy"):
                fields["godziny_opis_zrodlowy"] = fields["godziny_dostepnosci"]
            fields.pop("godziny_dostepnosci", None)
            fields["_license"] = res["license"]
            fields["data_danych"] = fields.get("data_danych") or res.get("data_date")
            rows.append((f"{res['dataset_id']}/{res['id']}/{row.get('id') or i}", fields))
            n += 1
        log.info("dane.gov.pl: zbiór %s „%s” – %d AED (%s)", res["dataset_id"], res["dataset_title"], n, res["license"])
    return rows
