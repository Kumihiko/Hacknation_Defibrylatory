import json

from aed.config import Source
from aed.record import build_record
from aed.sources import danegov

CSV = (
    "id,nazwa_obiektu,ulica_cecha,ulica_nazwa,nr_budynku,miejscowosc,szerokosc_geo,dlugosc_geo,"
    "wewnatrz_budynku,godziny_dostepnosci,typ_dostepu,klasa_dostepnosci,zrodla,dysponent_nazwa\r\n"
    "abc,Szkoła Podstawowa nr 3,ul.,Szkolna,5,Marki,52.3170,21.1041,true,Mo-Fr 08:00-16:00,publiczny,24h_pewny,falszywe,SP3\r\n"
)


def test_dysponent_dataset_is_ingested(monkeypatch):
    bundle = [{"id": "999", "url": "https://x/aed.csv", "dataset_id": "123", "dataset_title": "AED – SP3",
               "license": "CC0-1.0", "data_date": "2026-11-20", "csv": CSV}]
    monkeypatch.setattr(danegov, "cached", lambda *a, **k: json.dumps(bundle).encode())
    src = Source(id="danegov", name="d", connector="danegov_standard", url="https://x", license="wg-zbioru",
                 attribution="d", priority=95)
    rows = danegov.fetch(src, offline=True)
    assert len(rows) == 1
    key, fields = rows[0]
    assert key == "123/999/abc"
    assert "klasa_dostepnosci" not in fields and "zrodla" not in fields  # pola wyliczane liczy pipeline
    rec = build_record(src, key, fields, "2026-11-21")
    assert rec["zrodlo_licencja"] == "CC0-1.0"            # licencja ze zbioru na dane.gov.pl
    assert rec["klasa_dostepnosci"] == "godziny"          # nie „24h_pewny” z pliku
    assert rec["data_danych"] == "2026-11-20"
