"""Plik importu XML dla harwestera dane.gov.pl (schemat urn:otwarte-dane:harvester:1.13).

Struktura według XSD https://dane.gov.pl/static/xml/otwarte_dane_latest.xsd (kopia w schema/vendor/)
oraz instrukcji COI „Instrukcja przygotowania pliku XML” v1.0.6.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

NS = "urn:otwarte-dane:harvester:1.13"


def _text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.text = value
    return el


def _bilingual(parent: ET.Element, tag: str, pl: str, en: str, limit: int) -> None:
    el = ET.SubElement(parent, tag)
    _text(el, "polish", pl[:limit])
    _text(el, "english", en[:limit])


def build(settings: dict[str, Any], resources: list[dict[str, str]], data_date: str, generated: str) -> ET.ElementTree:
    ds = settings["dataset"]
    ET.register_namespace("p", NS)
    root = ET.Element(f"{{{NS}}}datasets")
    dataset = ET.SubElement(root, "dataset", {"status": "published"})
    _text(dataset, "extIdent", ds["ext_ident"][:36])
    _bilingual(dataset, "title", ds["title_pl"], ds["title_en"], 300)
    _bilingual(dataset, "description", ds["description_pl"], ds["description_en"], 1000)
    _text(dataset, "url", settings["publish_base_url"] + "/")
    _text(dataset, "updateFrequency", "daily")
    cats = ET.SubElement(dataset, "categories")
    _text(cats, "category", ds["category"])
    cond = ET.SubElement(dataset, "conditions")
    _text(cond, "source", "true")
    _text(cond, "modification", "true")
    _text(cond, "dbOrCopyrighted", ds["conditions_text"][:4000])
    res_el = ET.SubElement(dataset, "resources")
    for res in resources:
        r = ET.SubElement(res_el, "resource", {"status": "published"})
        _text(r, "extIdent", res["ext_ident"][:36])
        _text(r, "url", res["url"])
        _bilingual(r, "title", res["title_pl"], res["title_en"], 300)
        _bilingual(r, "description", res["description_pl"], res["description_en"], 1000)
        _text(r, "availability", "local")
        _text(r, "dataDate", data_date)
        _text(r, "lastUpdateDate", generated)
        _text(r, "hasDynamicData", "false")
        _text(r, "hasHighValueData", "false")
        _text(r, "hasHighValueDataFromEuropeanCommissionList", "false")
        _text(r, "hasResearchData", "false")
        _text(r, "containsProtectedData", "false")
    tags = ET.SubElement(dataset, "tags")
    for t in ds["tags_pl"]:
        ET.SubElement(tags, "tag", {"lang": "pl"}).text = t
    for t in ds["tags_en"]:
        ET.SubElement(tags, "tag", {"lang": "en"}).text = t
    _text(dataset, "lastUpdateDate", generated)
    _text(dataset, "hasDynamicData", "false")
    _text(dataset, "hasHighValueData", "false")
    _text(dataset, "hasHighValueDataFromEuropeanCommissionList", "false")
    _text(dataset, "hasResearchData", "false")
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def write(settings: dict[str, Any], resources: list[dict[str, str]], data_date: str, generated: str, path: Path) -> None:
    build(settings, resources, data_date, generated).write(path, encoding="UTF-8", xml_declaration=True)
