import pytest

from aed.config import Source
from aed.normalize.address import normalize_phone, parse_address, split_cecha
from aed.normalize.availability import classify
from aed.normalize.coords import fix_coords, haversine_m, puwg1992_to_wgs84
from aed.normalize.hours import parse_text
from aed.record import build_record


def test_swapped_coords_are_fixed():  # przypadek Marek: szerokość i długość zamienione
    assert fix_coords(21.107557, 52.326697) == (52.326697, 21.107557)
    assert fix_coords(52.326697, 21.107557) == (52.326697, 21.107557)
    assert fix_coords(0, 0) is None


def test_puwg1992():
    lat, lon = puwg1992_to_wgs84(500000.0, 459000.0)  # południk osiowy układu = 19°E
    assert lon == pytest.approx(19.0, abs=1e-9) and 51.9 < lat < 52.1
    lat, lon = puwg1992_to_wgs84(471775.7908439991, 730765.27134461)  # UM Sopot, ul. Kościuszki 25-27
    assert 54.42 < lat < 54.46 and 18.53 < lon < 18.59
    assert haversine_m(lat, lon, 54.44009, 18.56469) < 5


@pytest.mark.parametrize("text,expected", [
    ("ul. Jasna, 38-400 Krosno", {"ulica_cecha": "ul.", "ulica_nazwa": "Jasna", "kod_pocztowy": "38-400", "miejscowosc": "Krosno"}),
    ("Al.. Piłsudskiego 95, 05-270 Marki", {"ulica_cecha": "al.", "ulica_nazwa": "Piłsudskiego", "nr_budynku": "95"}),
    ("Gałowska 8D, 54-530 Wrocław", {"ulica_nazwa": "Gałowska", "nr_budynku": "8D", "miejscowosc": "Wrocław"}),
])
def test_parse_address(text, expected):
    got = parse_address(text)
    for k, v in expected.items():
        assert got[k] == v


def test_split_cecha_and_phone():
    assert split_cecha("Aleje Jerozolimskie") == ("al.", "Jerozolimskie")
    assert split_cecha("Parkowa") == (None, "Parkowa")
    assert normalize_phone("+48 22 597-09-27") == "225970927"
    assert normalize_phone("(22) 694-60-00 wew. 12") == "226946000"
    assert normalize_phone("123") is None


@pytest.mark.parametrize("hours,typ,inside,expected", [
    ("24/7", "publiczny", True, "24h_pewny"),
    ("24/7", "prywatny", True, "prywatny"),          # całodobowy, ale prywatny – nie prowadzimy
    (None, "publiczny", False, "24h_wnioskowany"),    # szafka zewnętrzna bez godzin
    (None, "publiczny", True, "nieznany"),
    (None, "w_godzinach_obiektu", None, "nieznany"),
    ("Mo-Fr 08:00-16:00", None, True, "godziny"),
])
def test_classify(hours, typ, inside, expected):
    assert classify(parse_text(hours), typ, inside) == expected


def _src(**kw):
    base = dict(id="test", name="t", connector="csv", url="https://x", license="CC0-1.0", attribution="t")
    base.update(kw)
    return Source(**base)


def test_build_record_warszawa_style():
    rec = build_record(_src(), "1", {
        "nazwa_obiektu": "Urząd Dzielnicy", "szerokosc_geo": "52.2086", "dlugosc_geo": "21,0149",
        "godziny_opis_zrodlowy": "Dni powszednie 07:00-17:00", "typ_dostepu": "Publiczny",
        "wewnatrz_budynku": True, "kod_pocztowy": "02517",
    }, "2026-11-21")
    assert rec["klasa_dostepnosci"] == "godziny"
    assert rec["godziny_dostepnosci"] == "Mo-Fr 07:00-17:00"
    assert rec["typ_dostepu"] == "publiczny"
    assert rec["kod_pocztowy"] == "02-517"
    assert rec["dlugosc_geo"] == pytest.approx(21.0149)


def test_build_record_without_coords_is_dropped():
    assert build_record(_src(), "1", {"nazwa_obiektu": "x"}, "2026-11-21") is None
