"""Replay recorded model text. Used by tests and the invalid-output eval."""

from __future__ import annotations

import time

from events_briefing.providers.base import ModelLeg, ProviderResult
from events_briefing.providers.parse import parse_briefing


class CassetteProvider:
    leg: ModelLeg = "cassette"

    def __init__(self, responses: list[str]) -> None:
        if not responses:
            raise ValueError("cassette has no responses")
        self._responses = list(responses)
        self._index = 0

    def complete(self, prompt: str, schema: dict[str, object]) -> ProviderResult:
        del prompt, schema
        started = time.perf_counter()
        text = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        parsed = parse_briefing(text)
        return ProviderResult(
            text=text,
            valid=parsed is not None,
            model_leg="cassette",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            timeout_s=None,
            cost_usd=0.0,
            error=None if parsed is not None else "cassette response failed validation",
        )
