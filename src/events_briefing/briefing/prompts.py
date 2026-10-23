from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date

from events_briefing.models import RankedIncident
from events_briefing.normalize import local_calendar_date
from events_briefing.providers.base import BRIEFING_SCHEMA
from events_briefing.providers.stub import INCIDENT_MARKER


def build_prompt(ranked: list[RankedIncident], rubric_version: str, *, as_of: date) -> str:
    rows = []
    for item in ranked[:8]:
        incident = item.incident
        rows.append(
            {
                "id": incident.id,
                "category_group": incident.category_group.value,
                "category": incident.category,
                "borough": incident.borough,
                "occurred_on": local_calendar_date(incident.created_at).isoformat(),
                "rank": item.rank,
                "score": item.score,
            }
        )
    schema = json.dumps(BRIEFING_SCHEMA, sort_keys=True)
    incidents = json.dumps(rows, sort_keys=True)
    return (
        "You are the rundown writer for a local briefing desk.\n"
        "Write a draft program. Do not say the item was published, sent, or emailed. "
        "The draft stays on this machine until an approval "
        "gate (simulated actor) runs. That gate is not an authenticated channel.\n"
        f"AS_OF: {as_of.isoformat()}\n"
        "Rules:\n"
        "- occurred_on is the America/New_York calendar date, not the UTC date. "
        "Repeat each cited incident's occurred_on as YYYY-MM-DD in that segment.\n"
        "- Copy BOROUGH_COUNTS. Those counts are already computed. "
        "Do not count incidents yourself.\n"
        "- If you give a count for a borough (for example '2 in Brooklyn'), it must "
        "match the cited incidents in that borough. Do not name a borough that none "
        "of the cited incidents are in.\n"
        "- Do not use relative-time words (today, yesterday, tonight, this morning, "
        "this evening, recently, right now) unless every cited "
        "incident supports that word against AS_OF. today only when occurred_on "
        "equals AS_OF. yesterday only when occurred_on is the previous calendar "
        "day. recently and right now are never supported.\n"
        "- Use a singular category word when that category has one cited incident, "
        "and a plural only when the count is greater than one. Any count you write "
        "must match the cited source ids.\n"
        "- Do not invent incident ids.\n"
        f"Rubric version: {rubric_version}\n"
        f"{_borough_count_block(rows)}\n"
        f"{INCIDENT_MARKER}\n{incidents}\n"
        f"SCHEMA_JSON:\n{schema}\n"
        "Return one JSON object matching SCHEMA_JSON. No markdown."
    )


def _borough_count_block(rows: Sequence[Mapping[str, object]]) -> str:
    totals: dict[str, int] = {}
    by_borough: dict[str, dict[str, int]] = {}
    for row in rows:
        category = str(row["category"])
        borough = str(row["borough"] or "")
        totals[category] = totals.get(category, 0) + 1
        if borough:
            bucket = by_borough.setdefault(category, {})
            bucket[borough] = bucket.get(borough, 0) + 1
    lines = [
        "BOROUGH_COUNTS:",
        "These counts are already computed. Copy them. Do not count incidents yourself.",
    ]
    for category in sorted(totals):
        parts = [f"{totals[category]} total"]
        for borough in sorted(by_borough.get(category, {})):
            parts.append(f"{by_borough[category][borough]} in {borough}")
        lines.append(f"- {category}: {'; '.join(parts)}")
    return "\n".join(lines)
