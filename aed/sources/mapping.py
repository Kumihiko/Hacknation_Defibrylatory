"""Zastosowanie mapowania pól z config/sources.yaml do surowego rekordu źródła."""

from __future__ import annotations

import re
from typing import Any


def _get(props: dict[str, Any], name: str) -> Any:
    if name in props:
        return props[name]
    wanted = name.strip().lower()
    for k, v in props.items():
        if str(k).strip().lower() == wanted:
            return v
    return None


def resolve(spec: Any, props: dict[str, Any]) -> Any:
    if isinstance(spec, str):
        return _get(props, spec)
    if isinstance(spec, dict):
        if "const" in spec:
            return spec["const"]
        if "join" in spec:
            parts = []
            for item in spec["join"]:
                value = _get(props, item)
                value = item if value is None and item not in props else value
                if value not in (None, ""):
                    parts.append(str(value).strip())
            return spec.get("sep", " ").join(parts) or None
        if "field" in spec:
            value = _get(props, spec["field"])
            if value is None:
                return None
            if "regex" in spec:
                m = re.search(spec["regex"], str(value), flags=re.IGNORECASE | re.DOTALL)
                return m.group(1).strip() if m else None
            return value
    return None


def apply(mapping: dict[str, Any], props: dict[str, Any]) -> dict[str, Any]:
    return {target: resolve(spec, props) for target, spec in mapping.items()}
