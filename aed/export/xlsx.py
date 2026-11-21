"""XLSX: wzorcowy zakres danych (opis pól, słowniki, przykłady) oraz pełny eksport danych."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .files import csv_value

HEADER_FILL = PatternFill("solid", fgColor="B91C1C")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")

_TYPE_PL = {"string": "tekst", "number": "liczba dziesiętna", "integer": "liczba całkowita",
            "boolean": "logiczny (true/false)", "date": "data (RRRR-MM-DD)"}

_ENUM_DESC = {
    "typ_dostepu": {
        "publiczny": "Dostępny dla każdego bez ograniczeń.",
        "w_godzinach_obiektu": "Dostępny, gdy obiekt (sklep, urząd) jest otwarty.",
        "ograniczony": "Wymaga zgody, klucza lub kontaktu z ochroną.",
        "prywatny": "Niedostępny publicznie (np. tylko dla pracowników).",
        "mobilny": "Urządzenie w pojeździe (np. tramwaj, radiowóz).",
    },
    "klasa_dostepnosci": {
        "24h_pewny": "Jawnie dostępny całą dobę (źródło podaje 24/7).",
        "24h_wnioskowany": "Publiczny, na zewnątrz budynku, bez podanych godzin – prawdopodobnie całodobowy.",
        "godziny": "Znane godziny dostępności.",
        "nieznany": "Brak informacji o dostępności.",
        "prywatny": "Niedostępny publicznie, ograniczony lub mobilny.",
    },
    "status": {
        "aktywny": "Urządzenie sprawne i dostępne.",
        "niesprawny": "Urządzenie uszkodzone lub wycofane.",
        "w_serwisie": "Czasowo niedostępne – serwis, wymiana elektrod/baterii.",
        "nieznany": "Brak informacji.",
    },
}


def _header(ws, headers: list[str], widths: list[int]) -> None:
    ws.append(headers)
    for i, w in enumerate(widths, start=1):
        cell = ws.cell(row=1, column=i)
        cell.fill, cell.font, cell.alignment = HEADER_FILL, HEADER_FONT, WRAP
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _schema_sheet(wb: Workbook, schema: dict[str, Any]) -> None:
    ws = wb.active
    ws.title = "Zakres danych"
    _header(ws, ["Lp.", "Grupa", "Nazwa kolumny", "Nazwa pola", "Opis", "Typ", "Wymagane",
                 "Dozwolone wartości / format", "Przykład", "Odpowiednik schema.org"],
            [5, 14, 24, 26, 60, 20, 10, 34, 34, 22])
    for i, f in enumerate(schema["fields"], start=1):
        c = f.get("constraints", {})
        allowed = ", ".join(c["enum"]) if "enum" in c else (f"wzorzec: {c['pattern']}" if "pattern" in c else "")
        if "minimum" in c:
            allowed = f"{c['minimum']} – {c['maximum']}"
        ws.append([i, f.get("x-grupa", ""), f["name"], f["title"], f.get("description", ""),
                   _TYPE_PL.get(f["type"], f["type"]), "TAK" if c.get("required") else "nie",
                   allowed, f.get("x-przyklad", ""), f.get("x-schemaorg", "")])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP


def _dict_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Słowniki")
    _header(ws, ["Pole", "Wartość", "Znaczenie"], [22, 24, 80])
    for field, values in _ENUM_DESC.items():
        for value, desc in values.items():
            ws.append([field, value, desc])
    ws.append([])
    ws.append(["godziny_dostepnosci", "składnia OSM", "Np. „24/7”, „Mo-Fr 08:00-16:00”, „Mo 08:00-18:00; Tu-Fr 08:00-16:00”. "
               "Dni: Mo Tu We Th Fr Sa Su; reguły rozdzielone średnikiem."])
    ws.append(["(formaty)", "Standard techniczny dane.gov.pl",
               "CSV: UTF-8, przecinek, CRLF, jeden wiersz nagłówka; daty RRRR-MM-DD; kropka dziesiętna; true/false; "
               "adres w osobnych polach; telefon 9 cyfr; współrzędne WGS84 (EPSG:4326)."])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP


def _data_sheet(wb: Workbook, title: str, fields: list[str], records: list[dict]) -> None:
    ws = wb.create_sheet(title)
    _header(ws, fields, [max(12, min(40, len(f) + 4)) for f in fields])
    for r in records:
        ws.append([csv_value(r.get(f)) if isinstance(r.get(f), bool) else r.get(f) for f in fields])


def _sources_sheet(wb: Workbook, sources: list) -> None:
    ws = wb.create_sheet("Źródła")
    _header(ws, ["Identyfikator", "Nazwa", "Wydawca", "Licencja", "Atrybucja", "Strona", "Włączone"],
            [22, 44, 40, 14, 44, 50, 10])
    for s in sources:
        ws.append([s.id, s.name, s.publisher, s.license, s.attribution, s.homepage, "tak" if s.enabled else "nie"])


def _sample(records: list[dict], n: int = 25) -> list[dict]:
    """Różnorodna próbka: po kilka rekordów każdej klasy dostępności i każdego źródła."""
    picked: dict[str, dict] = {}
    for key_fn in (lambda r: r["klasa_dostepnosci"], lambda r: r["zrodla"]):
        seen: dict[str, int] = {}
        for r in records:
            k = key_fn(r)
            if seen.get(k, 0) < 3 and r["id"] not in picked:
                picked[r["id"]] = r
                seen[k] = seen.get(k, 0) + 1
    return list(picked.values())[:n]


def write_template(path: Path, schema: dict[str, Any], records: list[dict], sources: list) -> None:
    """Wzorcowy zakres danych – plik wymagany w zgłoszeniu (opis pól + słowniki + przykłady + źródła)."""
    wb = Workbook()
    _schema_sheet(wb, schema)
    _dict_sheet(wb)
    fields = [f["name"] for f in schema["fields"]]
    _data_sheet(wb, "Przykładowe dane", fields, _sample(records))
    _sources_sheet(wb, sources)
    wb.save(path)


def write_full(path: Path, schema: dict[str, Any], records: list[dict], sources: list) -> None:
    wb = Workbook()
    _schema_sheet(wb, schema)
    fields = [f["name"] for f in schema["fields"]]
    _data_sheet(wb, "Dane", fields, records)
    _sources_sheet(wb, sources)
    wb.save(path)
