"""Adresy i telefony zgodnie ze Standardem technicznym dane.gov.pl (osobne pola, telefon 9 cyfr)."""

from __future__ import annotations

import re

_CECHY = {
    "ul": "ul.", "ulica": "ul.", "al": "al.", "aleja": "al.", "aleje": "al.", "pl": "pl.", "plac": "pl.",
    "os": "os.", "osiedle": "os.", "rondo": "rondo", "skwer": "skwer", "bulw": "bulw.", "bulwar": "bulw.",
    "rynek": "rynek", "park": "park", "wyb": "wyb.", "wybrzeże": "wyb.", "droga": "droga",
}
_POSTCODE = re.compile(r"\b(\d{2})\s*-?\s*(\d{3})\b")
_NUMBER = re.compile(r"\s+(\d+[A-Za-z]?(?:\s*[/-]\s*\d+[A-Za-z]?)?)\s*$")


def clean(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip(" ,;")
    return text or None


def normalize_postcode(value) -> str | None:
    text = clean(value)
    if not text:
        return None
    m = _POSTCODE.search(text)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def split_cecha(street: str | None) -> tuple[str | None, str | None]:
    """'ul. Jasna' -> ('ul.', 'Jasna'); 'Aleje Jerozolimskie' -> ('al.', 'Jerozolimskie')."""
    text = clean(street)
    if not text:
        return None, None
    m = re.match(r"^([A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+)\.*\s*(?<=[.\s])(.+)$", text)
    if m and m.group(1).lower() in _CECHY:
        return _CECHY[m.group(1).lower()], m.group(2)
    return None, text


def parse_address(text: str | None) -> dict[str, str | None]:
    """Rozbija adres w jednym polu, np. 'ul. Jasna 5, 38-400 Krosno' lub 'Gałowska 8D, 54-530 Wrocław'."""
    out: dict[str, str | None] = {"ulica_cecha": None, "ulica_nazwa": None, "nr_budynku": None,
                                  "nr_lokalu": None, "kod_pocztowy": None, "miejscowosc": None}
    text = clean(text)
    if not text:
        return out
    pc = _POSTCODE.search(text)
    street_part = text
    if pc:
        out["kod_pocztowy"] = f"{pc.group(1)}-{pc.group(2)}"
        after = clean(text[pc.end():])
        if after:
            out["miejscowosc"] = after.split(",")[0].strip() or None
        street_part = clean(text[:pc.start()]) or ""
    parts = [p.strip() for p in street_part.split(",") if p.strip()]
    if parts:
        street = parts[0]
        if not pc and len(parts) > 1 and not out["miejscowosc"]:
            out["miejscowosc"] = parts[-1]
        m = _NUMBER.search(street)
        if m:
            # "25/27" bywa zakresem budynków, a "12/4" numerem lokalu – nie rozstrzygamy,
            # zapisujemy dosłownie (Standard techniczny: dane adresowe literalnie zgodne ze źródłem)
            out["nr_budynku"] = re.sub(r"\s+", "", m.group(1))
            street = street[:m.start()]
        out["ulica_cecha"], out["ulica_nazwa"] = split_cecha(street)
    return out


def normalize_phone(value) -> str | None:
    """Telefon jako 9 cyfr (bez +48), zgodnie ze Standardem technicznym dane.gov.pl."""
    text = clean(value)
    if not text:
        return None
    first = re.split(r"[;,]|\bwew\b|\bw\.", text)[0]
    digits = re.sub(r"\D", "", first)
    if digits.startswith("0048"):
        digits = digits[4:]
    elif len(digits) == 11 and digits.startswith("48"):
        digits = digits[2:]
    return digits if len(digits) == 9 else None
