"""Budowa znormalizowanego rekordu AED z surowych pól źródła."""

from __future__ import annotations

import re
from typing import Any

from .config import Source
from .normalize.address import clean, normalize_phone, normalize_postcode, parse_address, split_cecha
from .normalize.availability import access_from_text, classify, indoor_from_text
from .normalize.coords import fix_coords, to_float
from .normalize.hours import UNKNOWN, Hours, mentions_24h, parse_osm, parse_text

Record = dict[str, Any]

_BOOL_TRUE = {"true", "tak", "yes", "1", "t", "y"}
_BOOL_FALSE = {"false", "nie", "no", "0", "f", "n"}


def to_bool(value) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    t = str(value).strip().lower()
    if t in _BOOL_TRUE:
        return True
    if t in _BOOL_FALSE:
        return False
    return None


def to_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    m = re.match(r"^\s*(-?\d+)", str(value))
    return int(m.group(1)) if m else None


def build_record(source: Source, key: str, fields: dict[str, Any], data_date: str) -> Record | None:
    """Zwraca rekord w układzie schematu (plus pola pomocnicze z prefiksem "_") albo None, gdy brak współrzędnych."""
    f = {k: v for k, v in fields.items()}
    for k, v in (source.extra.get("defaults") or {}).items():
        if not clean(f.get(k)):
            f[k] = v

    coords = fix_coords(to_float(f.get("szerokosc_geo")), to_float(f.get("dlugosc_geo")))
    if coords is None:
        return None
    lat, lon = coords

    rec: Record = {k: (clean(v) if isinstance(v, str) else v) for k, v in f.items() if not k.startswith("_")}
    rec["szerokosc_geo"], rec["dlugosc_geo"] = round(lat, 6), round(lon, 6)

    # --- adres
    if f.get("_adres_tekst"):
        parsed = parse_address(f["_adres_tekst"])
        for k, v in parsed.items():
            if v and not rec.get(k):
                rec[k] = v
    if rec.get("ulica_nazwa") and not rec.get("ulica_cecha"):
        rec["ulica_cecha"], rec["ulica_nazwa"] = split_cecha(rec["ulica_nazwa"])
    if rec.get("ulica_cecha"):
        rec["ulica_cecha"] = split_cecha(rec["ulica_cecha"] + " X")[0] or rec["ulica_cecha"]
    rec["kod_pocztowy"] = normalize_postcode(rec.get("kod_pocztowy"))
    for k in ("dysponent_telefon", "telefon_dostep"):
        rec[k] = normalize_phone(rec.get(k))
    for k in ("kod_terc", "kod_simc", "kod_ulic"):
        if rec.get(k):
            digits = re.sub(r"\D", "", str(rec[k]))
            width = {"kod_simc": 7, "kod_ulic": 5}.get(k)
            rec[k] = digits.zfill(width) if width else digits
    if not rec.get("nazwa_obiektu"):
        rec["nazwa_obiektu"] = "Defibrylator AED"

    # --- dostępność
    hours: Hours = UNKNOWN
    explicit_24 = to_bool(f.get("_dostepny_24_7"))
    if explicit_24 is True:
        hours = Hours(True, None)
    else:
        for candidate in (f.get("_osm_opening_hours"), rec.get("godziny_opis_zrodlowy")):
            if candidate:
                parsed = parse_osm(candidate) if candidate is f.get("_osm_opening_hours") else UNKNOWN
                if not parsed.known:
                    parsed = parse_text(candidate)
                if parsed.known:
                    hours = parsed
                    break
    if not hours.known and mentions_24h(rec.get("opis_lokalizacji")):
        hours = Hours(True, None)  # np. OSM: "Przedsionek schroniska, otwarte całodobowo"
    rec["dostepny_24_7"] = True if hours.is_24_7 else (False if hours.week else explicit_24)
    rec["godziny_dostepnosci"] = hours.to_osm()

    typ = rec.get("typ_dostepu")
    if typ and typ not in ("publiczny", "w_godzinach_obiektu", "ograniczony", "prywatny", "mobilny"):
        typ = access_from_text(typ)
    rec["typ_dostepu"] = typ

    inside = to_bool(rec.get("wewnatrz_budynku"))
    if inside is None:
        inside = indoor_from_text(" ".join(str(x) for x in (rec.get("opis_lokalizacji"), rec.get("godziny_opis_zrodlowy")) if x))
    rec["wewnatrz_budynku"] = inside
    rec["pietro"] = to_int(rec.get("pietro"))
    for k in ("szafka_zamknieta", "elektrody_pediatryczne"):
        rec[k] = to_bool(rec.get(k))

    rec["klasa_dostepnosci"] = classify(hours, typ, inside)

    # --- pochodzenie
    rec["zrodla"] = source.id
    rec["zrodlo_id"] = f"{source.id}:{key}"
    rec["zrodlo_licencja"] = f.get("_license") or source.license
    rec["data_danych"] = clean(f.get("data_danych")) or source.extra.get("data_date") or data_date
    rec["_hours"] = hours
    rec["_source"] = source
    rec["_key"] = key
    rec["_links"] = f.get("_links") or []  # twarde powiązania z innymi źródłami, np. ["um_warszawa:622"]
    return rec
