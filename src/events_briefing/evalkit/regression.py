"""Forced regression. The broken ranker must make the life-safety invariant fail."""

from __future__ import annotations

import time

from events_briefing.evalkit.runner import EvalReport, Status, execute, regression_exit_code
from events_briefing.evalkit.synthetic import synthetic_incidents
from events_briefing.models import Incident, RankedIncident
from events_briefing.ranking import life_safety_above_noise, rank_incidents
from events_briefing.rubric import Rubric


def broken_rank(incidents: list[Incident], rubric: Rubric) -> list[RankedIncident]:
    """Sort by floor ascending so noise outranks life-safety. This is the bug."""
    real = rank_incidents(incidents, rubric)
    ordered = sorted(real, key=lambda item: (item.parts.floor, item.incident.id))
    return [item.model_copy(update={"rank": index}) for index, item in enumerate(ordered, start=1)]


def run_regression(rubric: Rubric, package_version: str) -> tuple[EvalReport, int]:
    started = time.perf_counter()
    incidents = synthetic_incidents()
    holds = life_safety_above_noise(rank_incidents(incidents, rubric))
    rate = None if holds is None else (1.0 if holds else 0.0)
    scenarios = [
        execute(
            "broken_ranker_violates_life_safety_floor",
            lambda: _broken(rubric),
        ),
        execute(
            "real_ranker_keeps_life_safety_above_noise",
            lambda: _real(rubric),
        ),
    ]
    report = EvalReport(
        kind="regression",
        package_version=package_version,
        rubric_version=rubric.version,
        n_incidents=len(incidents),
        life_safety_above_noise_rate=rate,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        scenarios=scenarios,
    ).tally()
    return report, regression_exit_code(report)


def _broken(rubric: Rubric) -> tuple[Status, str]:
    ranked = broken_rank(synthetic_incidents(), rubric)
    holds = life_safety_above_noise(ranked)
    if holds is None:
        return "INCOMPLETE", "synthetic set is missing a group"
    if holds:
        return "PASS", "broken ranker unexpectedly kept life-safety above noise"
    return "FAIL", "life-safety ranked below noise under the broken ranker"


def _real(rubric: Rubric) -> tuple[Status, str]:
    holds = life_safety_above_noise(rank_incidents(synthetic_incidents(), rubric))
    if holds is None:
        return "INCOMPLETE", "synthetic set is missing a group"
    if not holds:
        return "FAIL", "real ranker failed the floor"
    return "PASS", "real ranker kept life-safety above noise"
