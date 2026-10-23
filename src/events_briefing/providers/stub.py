"""Deterministic briefing drafts. No network. Cost is zero."""

from __future__ import annotations

import json
import re
import time

from events_briefing.providers.base import BRIEFING_SCHEMA, ModelLeg, ProviderResult
from events_briefing.providers.parse import parse_briefing

INCIDENT_MARKER = "INCIDENT_JSON:"


class StubProvider:
    leg: ModelLeg = "stub"

    def complete(self, prompt: str, schema: dict[str, object]) -> ProviderResult:
        started = time.perf_counter()
        del schema  # The stub follows BRIEFING_SCHEMA, which the writer also sends.
        if schema_mismatch(prompt):
            return ProviderResult(
                text="",
                valid=False,
                model_leg="stub",
                latency_ms=_elapsed(started),
                timeout_s=None,
                cost_usd=0.0,
                error="prompt is missing the output schema",
            )
        incidents = _incidents_from_prompt(prompt)
        as_of = _as_of(prompt)
        if incidents is None:
            return ProviderResult(
                text="",
                valid=False,
                model_leg="stub",
                latency_ms=_elapsed(started),
                timeout_s=None,
                cost_usd=0.0,
                error="prompt is missing INCIDENT_JSON",
            )
        segments = _segments(incidents, as_of)
        text = json.dumps({"segments": segments}, sort_keys=True)
        valid = parse_briefing(text) is not None
        return ProviderResult(
            text=text,
            valid=valid,
            model_leg="stub",
            latency_ms=_elapsed(started),
            timeout_s=None,
            cost_usd=0.0,
            error=None if valid else "stub emitted invalid json",
        )


def schema_mismatch(prompt: str) -> bool:
    return json.dumps(BRIEFING_SCHEMA, sort_keys=True) not in prompt


def _incidents_from_prompt(prompt: str) -> list[dict[str, object]] | None:
    if INCIDENT_MARKER not in prompt:
        return None
    raw = prompt.split(INCIDENT_MARKER, 1)[1].split("SCHEMA_JSON:", 1)[0].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    rows: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _as_of(prompt: str) -> str:
    match = re.search(r"AS_OF:\s*(\d{4}-\d{2}-\d{2})", prompt)
    if match is None:
        return "1970-01-01"
    return match.group(1)


def _segments(incidents: list[dict[str, object]], as_of: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    order: list[str] = []
    for item in incidents[:8]:
        group = str(item.get("category_group") or "other")
        incident_id = str(item.get("id") or "")
        if not incident_id:
            continue
        if group not in grouped:
            order.append(group)
            grouped[group] = []
        grouped[group].append(item)
    segments: list[dict[str, object]] = []
    for group in order[:5]:
        rows = grouped[group]
        ids = [str(item.get("id") or "") for item in rows]
        dates = sorted(
            {str(item.get("occurred_on") or "") for item in rows if item.get("occurred_on")}
        )
        date_text = ", ".join(dates)
        count = len(ids)
        noun = "incident" if count == 1 else "incidents"
        label = group.replace("_", " ")
        segments.append(
            {
                "headline": f"{label}: {count} {noun} on {date_text}",
                "why_it_matters": (
                    f"As of {as_of}. Draft only. These source ids sit in this band under the "
                    "explicit rubric. Nothing has left this machine."
                ),
                "source_incident_ids": ids,
            }
        )
    return segments


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
