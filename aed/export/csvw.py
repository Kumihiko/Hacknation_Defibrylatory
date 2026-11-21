"""Metadane CSVW (W3C „CSV on the Web”) – wymagane na 4. poziomie otwartości wg Standardu technicznego dane.gov.pl."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATATYPES = {"string": "string", "number": "decimal", "integer": "integer", "boolean": "boolean", "date": "date"}
_SCHEMA_ORG = "http://schema.org/"


def build(schema: dict[str, Any], csv_name: str, settings: dict[str, Any], generated: str) -> dict[str, Any]:
    ds = settings["dataset"]
    columns = []
    for f in schema["fields"]:
        datatype: dict[str, Any] | str = _DATATYPES.get(f["type"], "string")
        constraints = f.get("constraints", {})
        if f["type"] == "boolean":
            datatype = {"base": "boolean", "format": "true|false"}
        elif "pattern" in constraints:
            datatype = {"base": "string", "format": constraints["pattern"]}
        elif "enum" in constraints:
            datatype = {"base": "string", "format": "|".join(constraints["enum"])}
        col: dict[str, Any] = {
            "name": f["name"],
            "titles": {"pl": f["title"]},
            "datatype": datatype,
            "required": bool(constraints.get("required")),
        }
        if f.get("description"):
            col["dc:description"] = {"@value": f["description"], "@language": "pl"}
        if f.get("x-schemaorg"):
            col["propertyUrl"] = _SCHEMA_ORG + f["x-schemaorg"].split(":", 1)[1]
        columns.append(col)
    return {
        "@context": ["http://www.w3.org/ns/csvw", {"@language": "pl"}],
        "url": csv_name,
        "dc:title": ds["title_pl"],
        "dc:description": ds["description_pl"],
        "dc:license": {"@id": "https://opendatacommons.org/licenses/odbl/1-0/"},
        "dc:modified": {"@value": generated, "@type": "xsd:dateTime"},
        "dcat:keyword": ds["tags_pl"],
        "dialect": {"delimiter": ",", "encoding": "utf-8", "header": True, "lineTerminators": ["\r\n"]},
        "tableSchema": {
            "columns": columns,
            "primaryKey": "id",
            "aboutUrl": "#aed-{id}",
        },
    }


def write(schema: dict[str, Any], csv_name: str, settings: dict[str, Any], generated: str, path: Path) -> None:
    path.write_text(json.dumps(build(schema, csv_name, settings, generated), ensure_ascii=False, indent=2), encoding="utf-8")
