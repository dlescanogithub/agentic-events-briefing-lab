"""Explicit rubric loaded from config/rubric.json. Weights are data, not a hidden prompt."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from events_briefing.models import CategoryGroup


class RubricError(ValueError):
    pass


class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    weights: dict[str, float]
    recency_half_life_hours: float = Field(gt=0)
    density_cap: int = Field(ge=1)
    group_floors: dict[str, float]
    category_weights: dict[str, float]
    nyc_311: dict[str, object]
    nypd: dict[str, object]
    fdny: dict[str, object]

    @model_validator(mode="after")
    def _check_weights(self) -> Rubric:
        required = ("severity", "recency", "density", "category")
        if set(self.weights) != set(required):
            raise ValueError("weights must be severity, recency, density, category")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1, got {total}")
        for name, value in self.weights.items():
            if value < 0:
                raise ValueError(f"weight {name} is negative")
        groups = {item.value for item in CategoryGroup}
        if set(self.group_floors) != groups or set(self.category_weights) != groups:
            raise ValueError("floors and category weights must cover every category group")
        floors = [self.group_floors[group.value] for group in CategoryGroup]
        if floors != sorted(floors, reverse=True):
            raise ValueError(
                "group floors must stay in life_safety > property > qol > other > noise"
            )
        gap_ok = self.group_floors["life_safety"] >= self.group_floors["noise"] + 1.0
        if not gap_ok:
            raise ValueError("life_safety floor must be at least 1 above noise")
        return self

    def weight(self, name: str) -> float:
        return self.weights[name]

    def floor_for(self, group: CategoryGroup) -> float:
        return self.group_floors[group.value]

    def category_weight(self, group: CategoryGroup) -> float:
        return self.category_weights[group.value]


def load_rubric(path: Path) -> Rubric:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RubricError(f"rubric file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RubricError(f"rubric file is not json: {path}") from exc
    try:
        return Rubric.model_validate(payload)
    except ValueError as exc:
        raise RubricError(str(exc)) from exc
