"""Resolve Aruba Central site names to saved map coordinates."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_SITE_DATA_PATH = Path(__file__).with_name("data") / "aruba_sites.json"


def _normalize_site_name(value: str) -> str:
    """Normalize harmless API/display differences without fuzzy matching sites."""
    return re.sub(r"\s+", " ", value).strip().casefold()


@lru_cache(maxsize=1)
def _site_index() -> dict[str, dict[str, Any]]:
    with _SITE_DATA_PATH.open(encoding="utf-8") as site_file:
        records = json.load(site_file)["sites"]
    return {
        _normalize_site_name(record["name"]): record
        for record in records
        if record.get("mapped")
    }


def get_aruba_site_location(site_name: str | None) -> dict[str, Any] | None:
    """Return a copy of the saved location for an exact Aruba site-name match."""
    if not isinstance(site_name, str) or not site_name.strip():
        return None
    location = _site_index().get(_normalize_site_name(site_name))
    return dict(location) if location else None
