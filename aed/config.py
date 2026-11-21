"""Ładowanie konfiguracji, schematu i ścieżek projektu."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SCHEMA_PATH = ROOT / "schema" / "aed.schema.json"
RAW_DIR = ROOT / "data" / "raw"
WEB_DIR = ROOT / "web"
OUT_DIR = WEB_DIR / "dane"  # eksporty publikowane razem ze stroną


@dataclass
class Source:
    id: str
    name: str
    connector: str
    url: str
    license: str
    attribution: str
    priority: int = 50
    enabled: bool = True
    publisher: str = ""
    homepage: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def mapping(self) -> dict[str, Any]:
        return self.extra.get("mapping", {})


def load_env(path: Path | None = None) -> None:
    """Minimalny loader pliku .env (KEY=VALUE), bez nadpisywania istniejących zmiennych."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_settings() -> dict[str, Any]:
    settings = yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8"))
    # w GitHub Actions adres publikacji pochodzi z konfiguracji GitHub Pages
    if os.environ.get("AED_PUBLISH_BASE_URL"):
        settings["publish_base_url"] = os.environ["AED_PUBLISH_BASE_URL"].rstrip("/")
    return settings


def load_sources(include_disabled: bool = False) -> list[Source]:
    data = yaml.safe_load((CONFIG_DIR / "sources.yaml").read_text(encoding="utf-8"))
    known = {"id", "name", "connector", "url", "license", "attribution", "priority", "enabled", "publisher", "homepage"}
    sources = []
    for item in data["sources"]:
        src = Source(
            id=item["id"],
            name=item["name"],
            connector=item["connector"],
            url=item["url"],
            license=item["license"],
            attribution=item.get("attribution", ""),
            priority=int(item.get("priority", 50)),
            enabled=bool(item.get("enabled", True)),
            publisher=item.get("publisher", ""),
            homepage=item.get("homepage", ""),
            extra={k: v for k, v in item.items() if k not in known},
        )
        if src.enabled or include_disabled:
            sources.append(src)
    return sources


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def field_names() -> list[str]:
    return [f["name"] for f in load_schema()["fields"]]
