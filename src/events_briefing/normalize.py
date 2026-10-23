"""Map allowlisted source fields onto Incident. Unknown fields are ignored."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from events_briefing.geohash import encode
from events_briefing.models import CategoryGroup, Incident, LocationPrecision, SourceName
from events_briefing.privacy import (
    BOROUGH_CENTROIDS,
    as_float,
    coords_are_coarse,
    normalize_borough,
    normalize_community_area,
    round_coord,
)
from events_briefing.rubric import Rubric

NY_TZ = ZoneInfo("America/New_York")


class NormalizeError(ValueError):
    pass


def local_calendar_date(moment: datetime) -> date:
    """Calendar date in America/New_York.

    ``created_at`` is stored in UTC. Taking ``.date()`` on that instant uses the
    UTC day, which is the next day for a New York evening. Convert first.
    A naive value is treated as UTC.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(NY_TZ).date()


def parse_socrata_time(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise NormalizeError("missing timestamp")
    if text.endswith("Z"):
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NY_TZ)
    return parsed.astimezone(timezone.utc)


def _group(value: str) -> CategoryGroup:
    try:
        return CategoryGroup(value)
    except ValueError as exc:
        raise NormalizeError(f"unknown category group: {value}") from exc


def classify_311(complaint_type: str, rubric: Rubric) -> tuple[CategoryGroup, float]:
    spec = rubric.nyc_311
    exact = spec["exact"]
    assert isinstance(exact, dict)
    key = complaint_type.strip().lower()
    group_name = exact.get(key)
    if not isinstance(group_name, str):
        prefixes = spec["prefix"]
        assert isinstance(prefixes, list)
        for rule in prefixes:
            assert isinstance(rule, dict)
            prefix = str(rule["prefix"]).lower()
            if key.startswith(prefix):
                group_name = str(rule["group"])
                break
    if not isinstance(group_name, str):
        group_name = str(spec["default_group"])
    group = _group(group_name)
    overrides = spec["severity_overrides"]
    assert isinstance(overrides, dict)
    override = overrides.get(key)
    if isinstance(override, int | float):
        return group, float(override)
    by_group = spec["severity_by_group"]
    assert isinstance(by_group, dict)
    return group, float(by_group[group.value])


def classify_nypd(ofns_desc: str, law_cat: str, rubric: Rubric) -> tuple[CategoryGroup, float]:
    spec = rubric.nypd
    text = ofns_desc.upper()
    group = CategoryGroup.OTHER
    for keyword in _str_list(spec, "life_safety_keywords"):
        if keyword in text:
            group = CategoryGroup.LIFE_SAFETY
            break
    if group is CategoryGroup.OTHER:
        for keyword in _str_list(spec, "property_keywords"):
            if keyword in text:
                group = CategoryGroup.PROPERTY
                break
    if group is CategoryGroup.OTHER:
        for keyword in _str_list(spec, "qol_keywords"):
            if keyword in text:
                group = CategoryGroup.QUALITY_OF_LIFE
                break
    law_map = spec["law_severity"]
    assert isinstance(law_map, dict)
    severity = law_map.get(law_cat.strip().upper(), spec["default_severity"])
    return group, _as_float(severity, 0.4)


def classify_fdny(
    classification: str, classification_group: str, alarm: str, rubric: Rubric
) -> tuple[CategoryGroup, float]:
    spec = rubric.fdny
    mapping = spec["group_by_classification_group"]
    assert isinstance(mapping, dict)
    group_name = mapping.get(classification_group.strip(), spec["default_group"])
    group = _group(str(group_name))
    alarms = spec["alarm_severity"]
    assert isinstance(alarms, dict)
    severity = _as_float(alarms.get(alarm.strip().lower()), 0.4)
    if classification_group.strip() == "Structural Fires":
        severity = max(severity, _as_float(spec["structural_floor"], 0.7))
    if not classification and not classification_group:
        group = CategoryGroup.OTHER
    return group, min(severity, 1.0)


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def _str_list(spec: dict[str, object], key: str) -> list[str]:
    raw = spec[key]
    assert isinstance(raw, list)
    return [str(item) for item in raw]


def _location_from_coords(
    lat_raw: float | None, lon_raw: float | None
) -> tuple[float | None, float | None, str | None, LocationPrecision]:
    if lat_raw is None or lon_raw is None:
        return None, None, None, LocationPrecision.UNKNOWN
    lat = round_coord(lat_raw)
    lon = round_coord(lon_raw)
    if not coords_are_coarse(lat, lon):
        raise NormalizeError("coordinates are finer than 2 decimal degrees")
    return lat, lon, encode(lat, lon, precision=6), LocationPrecision.ROUNDED_2DP


def _location_from_borough(
    borough: str | None,
) -> tuple[float | None, float | None, str | None, LocationPrecision]:
    if borough is None:
        return None, None, None, LocationPrecision.UNKNOWN
    centroid = BOROUGH_CENTROIDS.get(borough)
    if centroid is None:
        return None, None, None, LocationPrecision.UNKNOWN
    lat, lon = centroid
    return lat, lon, encode(lat, lon, precision=6), LocationPrecision.BOROUGH_CENTROID


def _prefer_rounded(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """Use pre-rounded snapshot fields when present. Ignore raw latitude/longitude keys."""
    lat = as_float(row.get("lat_rounded"))
    lon = as_float(row.get("lon_rounded"))
    if lat is not None and lon is not None:
        return lat, lon
    return as_float(row.get("latitude")), as_float(row.get("longitude"))


def incident_from_311(row: dict[str, Any], rubric: Rubric, dataset_id: str) -> Incident:
    complaint = str(row.get("complaint_type") or "").strip()
    if not complaint:
        raise NormalizeError("311 row missing complaint_type")
    group, severity = classify_311(complaint, rubric)
    borough = normalize_borough(_optional_str(row.get("borough")))
    lat, lon = _prefer_rounded(row)
    lat_r, lon_r, geohash, precision = _location_from_coords(lat, lon)
    return Incident(
        id=f"nyc_311:{_require_id(row, 'unique_key')}",
        source="nyc_311",
        source_dataset_id=dataset_id,
        category=complaint,
        category_group=group,
        severity_hint=severity,
        created_at=parse_socrata_time(str(row.get("created_date") or "")),
        borough=borough,
        community_area=normalize_community_area(_optional_str(row.get("community_board"))),
        geohash6=geohash,
        lat_rounded=lat_r,
        lon_rounded=lon_r,
        location_precision=precision,
    )


def incident_from_nypd(row: dict[str, Any], rubric: Rubric, dataset_id: str) -> Incident:
    offense = str(row.get("ofns_desc") or "").strip() or "UNSPECIFIED"
    group, severity = classify_nypd(offense, str(row.get("law_cat_cd") or ""), rubric)
    borough = normalize_borough(_optional_str(row.get("boro_nm")))
    lat, lon = _prefer_rounded(row)
    lat_r, lon_r, geohash, precision = _location_from_coords(lat, lon)
    return Incident(
        id=f"nypd_complaint:{_require_id(row, 'cmplnt_num')}",
        source="nypd_complaint",
        source_dataset_id=dataset_id,
        category=offense,
        category_group=group,
        severity_hint=severity,
        created_at=parse_socrata_time(str(row.get("cmplnt_fr_dt") or "")),
        borough=borough,
        community_area=None,
        geohash6=geohash,
        lat_rounded=lat_r,
        lon_rounded=lon_r,
        location_precision=precision,
    )


def incident_from_fdny(row: dict[str, Any], rubric: Rubric, dataset_id: str) -> Incident:
    classification = str(row.get("incident_classification") or "").strip()
    classification_group = str(row.get("incident_classification_group") or "").strip()
    alarm = str(row.get("highest_alarm_level") or "").strip()
    group, severity = classify_fdny(classification, classification_group, alarm, rubric)
    borough = normalize_borough(_optional_str(row.get("incident_borough")))
    community = _optional_str(row.get("communitydistrict"))
    lat_r, lon_r, geohash, precision = _location_from_borough(borough)
    category = classification_group or classification or "FDNY incident"
    return Incident(
        id=f"fdny_fire:{_require_id(row, 'starfire_incident_id')}",
        source="fdny_fire",
        source_dataset_id=dataset_id,
        category=category,
        category_group=group,
        severity_hint=severity,
        created_at=parse_socrata_time(str(row.get("incident_datetime") or "")),
        borough=borough,
        community_area=community,
        geohash6=geohash,
        lat_rounded=lat_r,
        lon_rounded=lon_r,
        location_precision=precision,
    )


def dedupe(incidents: list[Incident]) -> tuple[list[Incident], int]:
    seen: set[str] = set()
    kept: list[Incident] = []
    dropped = 0
    for incident in incidents:
        if incident.id in seen:
            dropped += 1
            continue
        seen.add(incident.id)
        kept.append(incident)
    return kept, dropped


def normalize_rows(
    source: SourceName, rows: list[dict[str, Any]], rubric: Rubric, dataset_id: str
) -> tuple[list[Incident], int]:
    builders = {
        "nyc_311": incident_from_311,
        "nypd_complaint": incident_from_nypd,
        "fdny_fire": incident_from_fdny,
    }
    built: list[Incident] = []
    for row in rows:
        built.append(builders[source](row, rubric, dataset_id))
    return dedupe(built)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_id(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise NormalizeError(f"missing {key}")
    return value
