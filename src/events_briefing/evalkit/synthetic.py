"""Fictional labeled incidents. These are not NYC Open Data rows."""

from __future__ import annotations

from datetime import datetime, timezone

from events_briefing.geohash import encode
from events_briefing.models import CategoryGroup, Incident, LocationPrecision, SourceName


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _point(
    *,
    incident_id: str,
    source: SourceName,
    category: str,
    group: CategoryGroup,
    severity: float,
    created_at: str,
    borough: str,
    lat: float,
    lon: float,
) -> Incident:
    return Incident(
        id=incident_id,
        source=source,
        source_dataset_id="synthetic",
        category=category,
        category_group=group,
        severity_hint=severity,
        created_at=_at(created_at),
        borough=borough,
        community_area=None,
        geohash6=encode(lat, lon, precision=6),
        lat_rounded=lat,
        lon_rounded=lon,
        location_precision=LocationPrecision.ROUNDED_2DP,
    )


def synthetic_incidents() -> list[Incident]:
    """Ten labeled rows. Life-safety, property, quality-of-life, other, and a tie in noise."""
    return [
        _point(
            incident_id="syn:life-robbery",
            source="nypd_complaint",
            category="ROBBERY",
            group=CategoryGroup.LIFE_SAFETY,
            severity=0.9,
            created_at="2026-10-16T18:00:00",
            borough="Bronx",
            lat=40.84,
            lon=-73.90,
        ),
        _point(
            incident_id="syn:life-fire",
            source="fdny_fire",
            category="Structural Fires",
            group=CategoryGroup.LIFE_SAFETY,
            severity=0.8,
            created_at="2026-10-16T17:00:00",
            borough="Brooklyn",
            lat=40.65,
            lon=-73.95,
        ),
        _point(
            incident_id="syn:life-medical",
            source="fdny_fire",
            category="Medical Emergencies",
            group=CategoryGroup.LIFE_SAFETY,
            severity=0.6,
            created_at="2026-10-15T12:00:00",
            borough="Queens",
            lat=40.73,
            lon=-73.79,
        ),
        _point(
            incident_id="syn:property-burg",
            source="nypd_complaint",
            category="BURGLARY",
            group=CategoryGroup.PROPERTY,
            severity=0.55,
            created_at="2026-10-16T16:00:00",
            borough="Manhattan",
            lat=40.78,
            lon=-73.97,
        ),
        _point(
            incident_id="syn:property-theft",
            source="nypd_complaint",
            category="PETIT LARCENY",
            group=CategoryGroup.PROPERTY,
            severity=0.55,
            created_at="2026-10-14T12:00:00",
            borough="Queens",
            lat=40.74,
            lon=-73.85,
        ),
        _point(
            incident_id="syn:qol-harass",
            source="nypd_complaint",
            category="HARRASSMENT 2",
            group=CategoryGroup.QUALITY_OF_LIFE,
            severity=0.4,
            created_at="2026-10-16T15:00:00",
            borough="Brooklyn",
            lat=40.66,
            lon=-73.96,
        ),
        _point(
            incident_id="syn:other-drugs",
            source="nypd_complaint",
            category="DANGEROUS DRUGS",
            group=CategoryGroup.OTHER,
            severity=0.4,
            created_at="2026-10-16T15:00:00",
            borough="Bronx",
            lat=40.85,
            lon=-73.87,
        ),
        _point(
            incident_id="syn:noise-a",
            source="nyc_311",
            category="Noise - Residential",
            group=CategoryGroup.NOISE,
            severity=0.15,
            created_at="2026-10-16T18:30:00",
            borough="Manhattan",
            lat=40.71,
            lon=-74.00,
        ),
        _point(
            incident_id="syn:noise-b",
            source="nyc_311",
            category="Noise - Residential",
            group=CategoryGroup.NOISE,
            severity=0.15,
            created_at="2026-10-16T18:30:00",
            borough="Manhattan",
            lat=40.71,
            lon=-74.00,
        ),
        _point(
            incident_id="syn:noise-old",
            source="nyc_311",
            category="Noise - Street/Sidewalk",
            group=CategoryGroup.NOISE,
            severity=0.99,
            created_at="2026-10-10T00:00:00",
            borough="Bronx",
            lat=40.86,
            lon=-73.86,
        ),
    ]
