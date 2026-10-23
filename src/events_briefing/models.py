from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CategoryGroup(str, Enum):
    LIFE_SAFETY = "life_safety"
    PROPERTY = "property"
    QUALITY_OF_LIFE = "quality_of_life"
    OTHER = "other"
    NOISE = "noise"


class LocationPrecision(str, Enum):
    ROUNDED_2DP = "rounded_2dp"
    BOROUGH_CENTROID = "borough_centroid"
    UNKNOWN = "unknown"


SourceName = Literal["nyc_311", "nypd_complaint", "fdny_fire"]


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: SourceName
    source_dataset_id: str
    category: str
    category_group: CategoryGroup
    severity_hint: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    borough: str | None
    community_area: str | None
    geohash6: str | None
    lat_rounded: float | None
    lon_rounded: float | None
    location_precision: LocationPrecision


class ScoreParts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: float
    recency: float
    density: float
    category: float
    within_band: float
    floor: float


class RankedIncident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    score: float
    parts: ScoreParts
    incident: Incident
