"""Scriptwriter: ask a provider, validate ids and prose, retry, then fail closed."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, datetime

from events_briefing.briefing.prompts import build_prompt
from events_briefing.briefing.textcheck import validate_briefing_text
from events_briefing.logging_setup import log_event
from events_briefing.models import RankedIncident
from events_briefing.providers.base import (
    BRIEFING_SCHEMA,
    CostBasis,
    ModelLeg,
    Provider,
    ProviderResult,
)
from events_briefing.providers.parse import parse_briefing
from events_briefing.providers.stub import StubProvider

logger = logging.getLogger("events_briefing.briefing")


def complete_with_validation(
    provider: Provider,
    prompt: str,
    *,
    max_attempts: int,
    accept: Callable[[ProviderResult], bool] | None = None,
) -> ProviderResult:
    """Bounded retries. Invalid JSON or rejected prose does not become a silent success."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last: ProviderResult | None = None
    spent = 0.0
    basis: CostBasis = "none"
    for attempt in range(1, max_attempts + 1):
        result = provider.complete(prompt, BRIEFING_SCHEMA)
        attempt_cost = result.cost_usd
        spent += attempt_cost
        basis = _merge_basis(basis, result.cost_basis)
        result = result.model_copy(
            update={"attempts": attempt, "cost_usd": spent, "cost_basis": basis}
        )
        last = result
        accepted = result.valid and (accept is None or accept(result))
        log_event(
            logger,
            logging.INFO,
            "llm_attempt",
            model_leg=result.model_leg,
            attempt=attempt,
            max_attempts=max_attempts,
            valid=result.valid,
            accepted=accepted,
            timeout_s=result.timeout_s,
            timed_out=result.timed_out,
            attempt_cost_usd=attempt_cost,
            cost_usd=spent,
        )
        if accepted:
            return result
    if last is None:
        return ProviderResult(
            text="",
            valid=False,
            model_leg=provider.leg,
            attempts=max_attempts,
            error="no provider result",
        )
    return last


def _merge_basis(current: CostBasis, new: CostBasis) -> CostBasis:
    """Summed cost is usage only when every priced attempt was usage."""
    if new == "none":
        return current
    if current in {"none", "usage"} and new == "usage":
        return "usage"
    return "estimate"


def deterministic_segments(ranked: list[RankedIncident], *, as_of: date) -> list[dict[str, object]]:
    provider = StubProvider()
    prompt = build_prompt(ranked, rubric_version="fallback", as_of=as_of)
    result = provider.complete(prompt, BRIEFING_SCHEMA)
    parsed = parse_briefing(result.text)
    if parsed is None:
        return []
    return [segment.model_dump() for segment in parsed.segments]


def render_markdown(
    *,
    program_id: str,
    status: str,
    model_leg: str,
    rubric_version: str,
    segments: list[dict[str, object]],
    simulated_note: str,
) -> str:
    lines = [
        f"# Program briefing ({status})",
        "",
        f"Program id: {program_id}",
        f"Status: {status}",
        f"Model leg: {model_leg}",
        f"Rubric version: {rubric_version}",
        simulated_note,
        "",
        "This file is a draft rundown. An approval gate (simulated actor) must run "
        "before the local outbox step. Production needs an authenticated channel.",
        "",
    ]
    for index, segment in enumerate(segments, start=1):
        ids = segment.get("source_incident_ids", [])
        id_text = ", ".join(str(item) for item in ids) if isinstance(ids, list) else ""
        lines.extend(
            [
                f"## {index}. {segment.get('headline', '')}",
                "",
                f"Why it matters: {segment.get('why_it_matters', '')}",
                "",
                f"Source incident ids: {id_text}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def usable_segments(
    ranked: list[RankedIncident], raw_segments: list[dict[str, object]]
) -> list[dict[str, object]]:
    known = {item.incident.id for item in ranked}
    kept: list[dict[str, object]] = []
    for segment in raw_segments:
        ids = segment.get("source_incident_ids")
        if not isinstance(ids, list):
            continue
        filtered = [str(item) for item in ids if str(item) in known]
        if not filtered:
            continue
        kept.append(
            {
                "headline": str(segment.get("headline") or ""),
                "why_it_matters": str(segment.get("why_it_matters") or ""),
                "source_incident_ids": filtered,
            }
        )
    return kept


def draft_from_provider(
    ranked: list[RankedIncident],
    provider: Provider,
    *,
    prompt: str,
    max_attempts: int,
    as_of: date,
) -> tuple[list[dict[str, object]], ModelLeg, ProviderResult]:
    held: dict[str, object] = {}

    def accept(result: ProviderResult) -> bool:
        parsed = parse_briefing(result.text) if result.valid else None
        if parsed is None:
            return False
        raw = [segment.model_dump() for segment in parsed.segments]
        usable = usable_segments(ranked, raw)
        if not usable:
            held["reason"] = "ids rejected"
            log_event(logger, logging.WARNING, "llm_ids_rejected", model_leg=result.model_leg)
            return False
        errors = validate_briefing_text(usable, ranked, as_of)
        if errors:
            held["reason"] = "; ".join(errors)
            log_event(
                logger,
                logging.WARNING,
                "briefing_text_rejected",
                model_leg=result.model_leg,
                reason=held["reason"],
            )
            return False
        held["usable"] = usable
        return True

    result = complete_with_validation(provider, prompt, max_attempts=max_attempts, accept=accept)
    usable = held.get("usable")
    if isinstance(usable, list) and usable:
        return usable, result.model_leg, result
    log_event(
        logger,
        logging.WARNING,
        "llm_fail_closed",
        model_leg=result.model_leg,
        attempts=result.attempts,
        timeout_s=result.timeout_s,
        timed_out=result.timed_out,
        error=result.error or held.get("reason"),
    )
    fallback = deterministic_segments(ranked, as_of=as_of)
    fallback_result = result.model_copy(
        update={"model_leg": "fallback", "valid": True, "cost_usd": result.cost_usd}
    )
    return fallback, "fallback", fallback_result


def program_id_for(inputs_hash: str, rubric_version: str) -> str:
    slug = rubric_version.replace(".", "-")
    return f"prog-{inputs_hash[:12]}-{slug}"


def briefing_document(
    *,
    program_id: str,
    status: str,
    model_leg: str,
    rubric_version: str,
    segments: list[dict[str, object]],
    inputs_hash: str,
    created_at: datetime,
    simulated: bool,
    approver: str | None,
) -> dict[str, object]:
    return {
        "program_id": program_id,
        "status": status,
        "model_leg": model_leg,
        "rubric_version": rubric_version,
        "inputs_hash": inputs_hash,
        "created_at": created_at.isoformat(),
        "approval_gate": "approval gate (simulated actor)",
        "simulated_approval": simulated,
        "approver": approver,
        "segments": segments,
    }


def dumps(document: dict[str, object]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"
