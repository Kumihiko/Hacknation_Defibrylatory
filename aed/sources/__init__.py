"""Konektory źródeł danych. Każdy zwraca listę par (klucz_w_źródle, pola), gdzie pola używają nazw ze schematu
(plus pola pomocnicze z prefiksem "_")."""

from __future__ import annotations

from typing import Callable

from ..config import Source
from . import gdansk, openaedmap, tabular, warszawa

Rows = list[tuple[str, dict]]
Connector = Callable[[Source, bool], Rows]

CONNECTORS: dict[str, Connector] = {
    "openaedmap": openaedmap.fetch,
    "warszawa": warszawa.fetch,
    "csv": tabular.fetch_csv,
    "geojson": tabular.fetch_geojson,
    "arcgis": tabular.fetch_arcgis,
    "kml": tabular.fetch_kml,
    "gdansk_html": gdansk.fetch,
}


def fetch_source(source: Source, offline: bool = False) -> Rows:
    try:
        connector = CONNECTORS[source.connector]
    except KeyError as exc:
        raise ValueError(f"Nieznany konektor '{source.connector}' w źródle {source.id}") from exc
    return connector(source, offline)
