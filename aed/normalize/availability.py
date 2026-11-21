"""Typ dostępu i klasa dostępności („czy mogę tam teraz iść?”)."""

from __future__ import annotations

import re

from .hours import Hours

ROUTABLE = ("24h_pewny", "24h_wnioskowany", "godziny")

_OSM_ACCESS = {
    "yes": "publiczny", "permissive": "publiczny", "public": "publiczny",
    "customers": "w_godzinach_obiektu", "visitors": "w_godzinach_obiektu",
    "permit": "ograniczony", "destination": "ograniczony",
    "private": "prywatny", "no": "prywatny", "employees": "prywatny", "staff": "prywatny",
}


def access_from_osm(value: str | None) -> str | None:
    return _OSM_ACCESS.get((value or "").strip().lower())


def access_from_text(value: str | None) -> str | None:
    t = (value or "").strip().lower()
    if not t:
        return None
    if t.startswith("publ") or "ogólnodost" in t or "ogolnodost" in t:
        return "publiczny"
    if t.startswith("pryw") or "tylko dla pracownik" in t or "niedostępn" in t:
        return "prywatny"
    if "ogranicz" in t:
        return "ograniczony"
    if "mobil" in t or "pojazd" in t:
        return "mobilny"
    return None


_OUTDOOR = re.compile(r"na zewn|zewnętrzn\w* ścian|elewac|wolnostoj|postument|kapsu[lł]|przy paczkomacie", re.IGNORECASE)
_INDOOR = re.compile(r"wewnątrz|wewnatrz|w holu|w budynku|w pomieszczeniu|przedsion|portier|recepcj|przy kasie|w pasażu|na piętrze|na parterze", re.IGNORECASE)


def indoor_from_text(value: str | None) -> bool | None:
    """True = wewnątrz, False = na zewnątrz, None = nie wiadomo."""
    if not value:
        return None
    outdoor, indoor = bool(_OUTDOOR.search(value)), bool(_INDOOR.search(value))
    if outdoor and not indoor:
        return False
    if indoor and not outdoor:
        return True
    return None


def classify(hours: Hours, typ_dostepu: str | None, wewnatrz: bool | None) -> str:
    """Klasa dostępności według planu:

    prywatny        – dostęp prywatny / ograniczony / mobilny (nie prowadzimy tam automatycznie),
    24h_pewny       – jawnie całodobowy,
    godziny         – znane godziny (trasa tylko, gdy otwarty teraz),
    24h_wnioskowany – publiczny, na zewnątrz budynku, bez podanych godzin (szafka zewnętrzna),
    nieznany        – brak informacji.
    """
    if typ_dostepu in ("prywatny", "ograniczony", "mobilny"):
        return "prywatny"
    if hours.is_24_7:
        return "24h_pewny"
    if hours.week:
        return "godziny"
    if typ_dostepu == "publiczny" and wewnatrz is False:
        return "24h_wnioskowany"
    return "nieznany"
