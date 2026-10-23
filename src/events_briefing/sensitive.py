"""Sensitive categories stay out of the public briefing and the map."""

from __future__ import annotations

import json
from pathlib import Path

from events_briefing.models import Incident


def load_sensitive_terms(path: Path) -> tuple[str, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("terms")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"sensitive category list is empty: {path}")
    terms = tuple(str(item).strip().casefold() for item in raw if str(item).strip())
    if not terms:
        raise ValueError(f"sensitive category list is empty: {path}")
    return terms


def is_sensitive(category: str, terms: tuple[str, ...]) -> bool:
    text = category.casefold()
    return any(term in text for term in terms)


def split_public(
    incidents: list[Incident], terms: tuple[str, ...]
) -> tuple[list[Incident], list[Incident]]:
    public: list[Incident] = []
    withheld: list[Incident] = []
    for incident in incidents:
        if is_sensitive(incident.category, terms):
            withheld.append(incident)
        else:
            public.append(incident)
    return public, withheld
