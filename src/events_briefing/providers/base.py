from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ModelLeg = Literal["stub", "cassette", "live", "fallback"]
CostBasis = Literal["usage", "estimate", "none"]


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    valid: bool
    model_leg: ModelLeg
    latency_ms: float = 0.0
    timeout_s: float | None = None
    cost_usd: float = 0.0
    cost_basis: CostBasis = "none"
    attempts: int = 1
    error: str | None = None
    timed_out: bool = False


class Provider(Protocol):
    leg: ModelLeg

    def complete(self, prompt: str, schema: dict[str, object]) -> ProviderResult:
        """Return one model attempt. Validation of JSON happens in the caller wrapper."""


class SegmentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1, max_length=200)
    why_it_matters: str = Field(min_length=1, max_length=600)
    source_incident_ids: list[str] = Field(min_length=1)


class BriefingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[SegmentDraft] = Field(min_length=1)


BRIEFING_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["segments"],
    "properties": {
        "segments": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["headline", "why_it_matters", "source_incident_ids"],
                "properties": {
                    "headline": {"type": "string", "minLength": 1, "maxLength": 200},
                    "why_it_matters": {"type": "string", "minLength": 1, "maxLength": 600},
                    "source_incident_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}
