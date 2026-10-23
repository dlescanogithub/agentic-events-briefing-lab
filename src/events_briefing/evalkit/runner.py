"""Eval runner. PASS requires a completed check with a non-empty detail."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["PASS", "FAIL", "INCOMPLETE"]


class ScenarioReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    status: Status
    completed: bool
    detail: str
    duration_ms: float


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["eval", "regression"]
    package_version: str
    rubric_version: str
    n_incidents: int
    life_safety_above_noise_rate: float | None
    elapsed_ms: float
    scenarios: list[ScenarioReport]
    pass_count: int = 0
    fail_count: int = 0
    incomplete_count: int = 0

    def tally(self) -> EvalReport:
        return self.model_copy(
            update={
                "pass_count": sum(1 for item in self.scenarios if item.status == "PASS"),
                "fail_count": sum(1 for item in self.scenarios if item.status == "FAIL"),
                "incomplete_count": sum(
                    1 for item in self.scenarios if item.status == "INCOMPLETE"
                ),
            }
        )


ScenarioFn = Callable[[], tuple[Status, str]]


def execute(scenario_id: str, fn: ScenarioFn) -> ScenarioReport:
    started = time.perf_counter()
    try:
        status, detail = fn()
    except Exception as exc:
        return ScenarioReport(
            scenario_id=scenario_id,
            status="INCOMPLETE",
            completed=False,
            detail=f"{type(exc).__name__}: {exc}",
            duration_ms=_ms(started),
        )
    if status not in {"PASS", "FAIL", "INCOMPLETE"}:
        status = "INCOMPLETE"
        detail = f"invalid status token: {detail}"
    if status == "PASS" and not detail.strip():
        return ScenarioReport(
            scenario_id=scenario_id,
            status="INCOMPLETE",
            completed=False,
            detail="empty PASS is not allowed",
            duration_ms=_ms(started),
        )
    completed = status != "INCOMPLETE"
    return ScenarioReport(
        scenario_id=scenario_id,
        status=status,
        completed=completed,
        detail=detail,
        duration_ms=_ms(started),
    )


def eval_exit_code(report: EvalReport) -> int:
    if report.incomplete_count or report.fail_count or report.pass_count != len(report.scenarios):
        return 1
    if not report.scenarios:
        return 1
    return 0


def regression_exit_code(report: EvalReport) -> int:
    by_id = {item.scenario_id: item for item in report.scenarios}
    broken = by_id.get("broken_ranker_violates_life_safety_floor")
    control = by_id.get("real_ranker_keeps_life_safety_above_noise")
    if broken is None or control is None:
        return 3
    if broken.status == "INCOMPLETE" or control.status == "INCOMPLETE":
        return 3
    if broken.status == "FAIL" and control.status == "PASS":
        return 1
    if broken.status == "PASS":
        return 2
    return 3


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
