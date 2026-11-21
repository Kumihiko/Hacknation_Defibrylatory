"""Łączenie rekordów tego samego AED pochodzących z różnych źródeł.

Reguły:
* łączymy tylko rekordy z RÓŻNYCH źródeł (w jednym budynku bywa kilka AED z tego samego źródła),
* kandydaci: odległość <= max_distance_m; poniżej auto_merge_distance_m łączymy od razu,
  powyżej – gdy nazwy lub adresy są podobne (rapidfuzz token_set_ratio),
* twarde powiązania (np. tag OSM ref:api-um-warszawa-pl) łączą niezależnie od odległości (do 150 m),
* pola bierzemy ze źródła o najwyższym priorytecie, braki uzupełniamy z kolejnych;
  współrzędne preferujemy z OSM (mapowane ręcznie na miejscu), chyba że go brak.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from rapidfuzz import fuzz

from .normalize.availability import classify
from .normalize.coords import haversine_m
from .normalize.hours import UNKNOWN, Hours

NAMESPACE = uuid.UUID("6f1d3c52-8f4e-4b8e-9f0e-6a1f2b3c4d5e")
HARD_LINK_MAX_M = 150.0


class _DSU:
    def __init__(self, records: list[dict]):
        self.parent = list(range(len(records)))
        self.sources = [{r["_source"].id} for r in records]

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb or self.sources[ra] & self.sources[rb]:
            return False  # ten sam klaster albo kolizja źródeł
        self.parent[rb] = ra
        self.sources[ra] |= self.sources[rb]
        return True


def _text(rec: dict) -> str:
    return " ".join(str(rec.get(k) or "") for k in ("nazwa_obiektu", "opis_lokalizacji")).lower()


def _address(rec: dict) -> str:
    return " ".join(str(rec.get(k) or "") for k in ("ulica_nazwa", "nr_budynku")).lower().strip()


def _similar(a: dict, b: dict, threshold: int) -> bool:
    ta, tb = _text(a), _text(b)
    if ta.strip() and tb.strip() and fuzz.token_set_ratio(ta, tb) >= threshold:
        return True
    aa, ab = _address(a), _address(b)
    return bool(aa and ab and fuzz.token_set_ratio(aa, ab) >= threshold)


def find_clusters(records: list[dict], settings: dict[str, Any]) -> list[list[dict]]:
    max_d = float(settings.get("max_distance_m", 40))
    auto_d = float(settings.get("auto_merge_distance_m", 12))
    threshold = int(settings.get("name_similarity", 70))

    cell = max_d / 111_000  # rozmiar komórki siatki w stopniach (szerokość)
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        grid[(int(r["szerokosc_geo"] / cell), int(r["dlugosc_geo"] / (cell * 1.6)))].append(i)

    pairs: list[tuple[float, int, int]] = []
    for (gy, gx), members in grid.items():
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for j in grid.get((gy + dy, gx + dx), []):
                    for i in members:
                        if i >= j:
                            continue
                        a, b = records[i], records[j]
                        if a["_source"].id == b["_source"].id:
                            continue
                        d = haversine_m(a["szerokosc_geo"], a["dlugosc_geo"], b["szerokosc_geo"], b["dlugosc_geo"])
                        if d <= auto_d or (d <= max_d and _similar(a, b, threshold)):
                            pairs.append((d, i, j))

    # twarde powiązania między źródłami
    by_key = {f"{r['_source'].id}:{r['_key']}": i for i, r in enumerate(records)}
    for i, r in enumerate(records):
        for link in r.get("_links") or []:
            j = by_key.get(link)
            if j is not None:
                d = haversine_m(r["szerokosc_geo"], r["dlugosc_geo"], records[j]["szerokosc_geo"], records[j]["dlugosc_geo"])
                if d <= HARD_LINK_MAX_M:
                    pairs.append((-1.0, i, j))  # najwyższy priorytet łączenia

    dsu = _DSU(records)
    for _, i, j in sorted(pairs):
        dsu.union(i, j)
    clusters: dict[int, list[dict]] = defaultdict(list)
    for i, r in enumerate(records):
        clusters[dsu.find(i)].append(r)
    return list(clusters.values())


_AVAIL_FIELDS = ("dostepny_24_7", "godziny_dostepnosci", "godziny_opis_zrodlowy")


def merge(cluster: list[dict]) -> dict:
    members = sorted(cluster, key=lambda r: -r["_source"].priority)
    out: dict[str, Any] = {}
    for rec in members:
        for k, v in rec.items():
            if k.startswith("_") or k in _AVAIL_FIELDS or k in ("zrodla", "zrodlo_id", "zrodlo_licencja", "klasa_dostepnosci"):
                continue
            if out.get(k) in (None, "") and v not in (None, ""):
                out[k] = v

    osm = next((r for r in members if r["_source"].id == "osm"), None)
    anchor = osm or members[0]
    out["szerokosc_geo"], out["dlugosc_geo"] = anchor["szerokosc_geo"], anchor["dlugosc_geo"]

    # dostępność: pierwsze (wg priorytetu) źródło, które ją zna; jawne 24/7 ma pierwszeństwo przed godzinami
    hours: Hours = UNKNOWN
    avail_src = next((r for r in members if r["_hours"].is_24_7), None) or next((r for r in members if r["_hours"].week), None)
    if avail_src:
        hours = avail_src["_hours"]
        for k in _AVAIL_FIELDS:
            out[k] = avail_src.get(k)
    else:
        for k in _AVAIL_FIELDS:
            out[k] = next((r.get(k) for r in members if r.get(k) not in (None, "")), None)

    # typ dostępu i wewnątrz/na zewnątrz pochodzą ze źródła o najwyższym priorytecie, które je podaje
    out["klasa_dostepnosci"] = classify(hours, out.get("typ_dostepu"), out.get("wewnatrz_budynku"))

    out["zrodla"] = ";".join(r["_source"].id for r in members)
    out["zrodlo_id"] = ";".join(r["zrodlo_id"] for r in members)
    out["zrodlo_licencja"] = ";".join(dict.fromkeys(r["_source"].license for r in members))
    out["data_danych"] = max(r["data_danych"] for r in members)
    dates = [r.get("data_weryfikacji") for r in members if r.get("data_weryfikacji")]
    out["data_weryfikacji"] = max(dates) if dates else None
    out["id"] = str(uuid.uuid5(NAMESPACE, anchor["zrodlo_id"]))
    out["_hours"] = hours
    out["_members"] = len(members)
    return out


def deduplicate(records: list[dict], settings: dict[str, Any]) -> tuple[list[dict], dict[str, Any]]:
    clusters = find_clusters(records, settings)
    merged = [merge(c) for c in clusters]
    pair_stats: dict[str, int] = defaultdict(int)
    for c in clusters:
        if len(c) > 1:
            pair_stats["+".join(sorted({r["_source"].id for r in c}))] += 1
    report = {
        "rekordow_wejsciowych": len(records),
        "rekordow_po_deduplikacji": len(merged),
        "polaczonych_klastrow": sum(1 for c in clusters if len(c) > 1),
        "polaczenia_wg_zrodel": dict(sorted(pair_stats.items(), key=lambda kv: -kv[1])),
    }
    merged.sort(key=lambda r: (r["szerokosc_geo"], r["dlugosc_geo"]))
    return merged, report

