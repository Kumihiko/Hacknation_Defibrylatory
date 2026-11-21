import csv
from pathlib import Path

from aed.config import Source, load_schema, load_settings
from aed.dedupe import deduplicate
from aed.export import danegov_xml, files
from aed.record import build_record

XSD = Path(__file__).resolve().parent.parent / "schema" / "vendor" / "otwarte_dane_harvester_1.13.xsd"
SETTINGS = {"max_distance_m": 40, "auto_merge_distance_m": 12, "name_similarity": 70}


def src(sid, priority):
    return Source(id=sid, name=sid, connector="csv", url="https://x", license="CC0-1.0", attribution=sid, priority=priority)


OSM, WAW = src("osm", 10), src("um_warszawa", 90)


def rec(source, key, lat, lon, **fields):
    return build_record(source, key, {"szerokosc_geo": lat, "dlugosc_geo": lon, **fields}, "2026-11-21")


def test_merge_across_sources_takes_hours_from_official():
    a = rec(OSM, "node/1", 52.20860, 21.01490, nazwa_obiektu="Urząd Dzielnicy Mokotów")
    b = rec(WAW, "622", 52.20865, 21.01495, nazwa_obiektu="Urząd Dzielnicy Mokotów m.st. Warszawy",
            godziny_opis_zrodlowy="Dni powszednie 08:00-16:00", typ_dostepu="Publiczny")
    merged, report = deduplicate([a, b], SETTINGS)
    assert len(merged) == 1
    m = merged[0]
    assert m["zrodla"] == "um_warszawa;osm"
    assert m["klasa_dostepnosci"] == "godziny"
    assert (m["szerokosc_geo"], m["dlugosc_geo"]) == (a["szerokosc_geo"], a["dlugosc_geo"])  # współrzędne z OSM
    assert report["polaczonych_klastrow"] == 1


def test_same_source_never_merged():
    a = rec(OSM, "node/1", 52.2086, 21.0149, nazwa_obiektu="Hala")
    b = rec(OSM, "node/2", 52.2086, 21.0149, nazwa_obiektu="Hala")
    merged, _ = deduplicate([a, b], SETTINGS)
    assert len(merged) == 2


def test_far_records_with_different_names_not_merged():
    a = rec(OSM, "node/1", 52.2086, 21.0149, nazwa_obiektu="Szkoła")
    b = rec(WAW, "1", 52.2089, 21.0149, nazwa_obiektu="Apteka")  # ok. 33 m, inna nazwa
    merged, _ = deduplicate([a, b], SETTINGS)
    assert len(merged) == 2


def test_hard_link_merges():
    a = rec(OSM, "node/1", 52.2086, 21.0149, nazwa_obiektu="X", _links=["um_warszawa:622"])
    b = rec(WAW, "622", 52.2096, 21.0149, nazwa_obiektu="Y")  # ok. 110 m, ale powiązane tagiem
    merged, _ = deduplicate([a, b], SETTINGS)
    assert len(merged) == 1


def test_csv_follows_standard(tmp_path):
    r = rec(WAW, "1", 52.2, 21.0, nazwa_obiektu="A, B", wewnatrz_budynku=True)
    merged, _ = deduplicate([r], SETTINGS)
    fields = [f["name"] for f in load_schema()["fields"]]
    out = tmp_path / "a.csv"
    files.write_csv(merged, fields, out)
    raw = out.read_bytes()
    assert b"\r\n" in raw and not raw.startswith(b"\xef\xbb\xbf")
    row = next(csv.DictReader(out.open(encoding="utf-8")))
    assert row["wewnatrz_budynku"] == "true" and row["nazwa_obiektu"] == "A, B" and row["szerokosc_geo"] == "52.2"


def test_danegov_xml_valid_against_xsd(tmp_path):
    from lxml import etree
    out = tmp_path / "import.xml"
    res = [{"ext_ident": "aed-csv", "url": "https://example.github.io/aed/dane/aed.csv", "title_pl": "A",
            "title_en": "A", "description_pl": "Opis", "description_en": "Desc"}]
    danegov_xml.write(load_settings(), res, "2026-11-21", "2026-11-21T12:00:00Z", out)
    schema = etree.XMLSchema(etree.parse(str(XSD)))
    assert schema.validate(etree.parse(str(out))), schema.error_log
