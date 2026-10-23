"""Allowlists and leak checks. Raw addresses and raw coordinates must not survive."""

from __future__ import annotations

import math
import re
from typing import Any

# Keys that must never appear in normalized output, snapshots, briefings, or traces.
FORBIDDEN_KEYS = frozenset(
    {
        "incident_address",
        "street_name",
        "cross_street_1",
        "cross_street_2",
        "intersection_street_1",
        "intersection_street_2",
        "address_type",
        "landmark",
        "resolution_description",
        "descriptor",
        "descriptor_2",
        "alarm_box_location",
        "location",
        "lat_lon",
        "geocoded_column",
        "latitude",
        "longitude",
        "x_coordinate_state_plane",
        "y_coordinate_state_plane",
        "x_coord_cd",
        "y_coord_cd",
        "phone",
        "caller_phone",
        "name",
        "email",
        "susp_age_group",
        "susp_race",
        "susp_sex",
        "vic_age_group",
        "vic_race",
        "vic_sex",
        "incident_zip",
        "addr_pct_cd",
        "pd_desc",
        "prem_typ_desc",
    }
)

PHONE_RE = re.compile(r"\b\d{3}[-.)\s]\d{3}[-.\s]\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

# Schematic borough centers, rounded to 2 decimal degrees. Not survey monuments.
BOROUGH_CENTROIDS: dict[str, tuple[float, float]] = {
    "Manhattan": (40.78, -73.97),
    "Brooklyn": (40.65, -73.95),
    "Queens": (40.73, -73.79),
    "Bronx": (40.85, -73.87),
    "Staten Island": (40.58, -74.15),
}

BOROUGH_ALIASES = {
    "MANHATTAN": "Manhattan",
    "BROOKLYN": "Brooklyn",
    "QUEENS": "Queens",
    "BRONX": "Bronx",
    "STATEN ISLAND": "Staten Island",
    "RICHMOND / STATEN ISLAND": "Staten Island",
    "RICHMOND": "Staten Island",
}


def round_coord(value: float, places: int = 2) -> float:
    rounded = round(float(value), places)
    if math.isnan(rounded) or math.isinf(rounded):
        raise ValueError("coordinate is not finite")
    return rounded


def normalize_borough(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text or text.upper() in {"UNSPECIFIED", "N/A", "NA", "NULL"}:
        return None
    return BOROUGH_ALIASES.get(text.upper(), text.title())


def normalize_community_area(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text or text.upper().startswith("0 ") or "UNSPECIFIED" in text.upper():
        return None
    return text


def forbidden_keys(payload: object) -> list[str]:
    found: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_text = str(key)
                if key_text.lower() in FORBIDDEN_KEYS:
                    found.append(f"{path}.{key_text}")
                walk(value, f"{path}.{key_text}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, "$")
    return found


def sensitive_strings(payload: object) -> list[str]:
    found: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, str):
            if PHONE_RE.search(node) or EMAIL_RE.search(node):
                found.append(path)
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, "$")
    return found


def coords_are_coarse(lat: float | None, lon: float | None) -> bool:
    if lat is None and lon is None:
        return True
    if lat is None or lon is None:
        return False
    return lat == round_coord(lat) and lon == round_coord(lon)


def dump_contains(text: str, needles: list[str]) -> list[str]:
    return [needle for needle in needles if needle and needle in text]


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number
