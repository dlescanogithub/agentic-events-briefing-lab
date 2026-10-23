"""Deterministic ranker. Life-safety sits on a higher floor than noise."""

from __future__ import annotations

import math
from datetime import datetime

from events_briefing.models import (
    CategoryGroup,
    Incident,
    LocationPrecision,
    RankedIncident,
    ScoreParts,
)
from events_briefing.rubric import Rubric


def rank_incidents(incidents: list[Incident], rubric: Rubric) -> list[RankedIncident]:
    if not incidents:
        return []
    reference = max(item.created_at for item in incidents)
    density_lookup = _density_counts(incidents)
    scored: list[tuple[float, Incident, ScoreParts]] = []
    for incident in incidents:
        parts, score = _score(incident, rubric, reference, density_lookup)
        scored.append((score, incident, parts))
    ordered = sorted(
        scored,
        key=lambda item: (-item[0], -item[1].created_at.timestamp(), item[1].id),
    )
    return [
        RankedIncident(rank=index, score=round(score, 6), parts=parts, incident=incident)
        for index, (score, incident, parts) in enumerate(ordered, start=1)
    ]


def _density_counts(incidents: list[Incident]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for incident in incidents:
        if incident.location_precision is not LocationPrecision.ROUNDED_2DP:
            continue
        if not incident.geohash6:
            continue
        key = (incident.geohash6, incident.category_group.value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _score(
    incident: Incident,
    rubric: Rubric,
    reference: datetime,
    density_lookup: dict[tuple[str, str], int],
) -> tuple[ScoreParts, float]:
    age_hours = max(0.0, (reference - incident.created_at).total_seconds() / 3600)
    recency = math.exp(-age_hours / rubric.recency_half_life_hours)
    cluster_key = (incident.geohash6 or "", incident.category_group.value)
    neighbors = 0
    if incident.location_precision is LocationPrecision.ROUNDED_2DP and incident.geohash6:
        neighbors = max(0, density_lookup.get(cluster_key, 1) - 1)
    density = min(1.0, math.log1p(neighbors) / math.log1p(rubric.density_cap))
    severity = min(1.0, max(0.0, incident.severity_hint))
    category = rubric.category_weight(incident.category_group)
    within = (
        rubric.weight("severity") * severity
        + rubric.weight("recency") * recency
        + rubric.weight("density") * density
        + rubric.weight("category") * category
    )
    within = min(within, 0.999)
    floor = rubric.floor_for(incident.category_group)
    parts = ScoreParts(
        severity=round(severity, 6),
        recency=round(recency, 6),
        density=round(density, 6),
        category=round(category, 6),
        within_band=round(within, 6),
        floor=floor,
    )
    return parts, floor + within


def life_safety_above_noise(ranked: list[RankedIncident]) -> bool | None:
    """True/False when both groups exist. None when the check cannot be completed."""
    life = [
        item.rank for item in ranked if item.incident.category_group is CategoryGroup.LIFE_SAFETY
    ]
    noise = [item.rank for item in ranked if item.incident.category_group is CategoryGroup.NOISE]
    if not life or not noise:
        return None
    return max(life) < min(noise)
