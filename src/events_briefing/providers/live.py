"""Optional OpenAI-compatible live provider. Off unless LIVE_LLM=1 and prices are set.

No price table is hardcoded. A missing price, model, URL, or key refuses the call.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from events_briefing.config import Settings
from events_briefing.providers.base import CostBasis, ModelLeg, ProviderResult
from events_briefing.providers.parse import parse_briefing


class LiveConfigError(RuntimeError):
    pass


@dataclass
class SpendLedger:
    cap_usd: float
    spent_usd: float = 0.0

    def reserve(self, amount: float) -> bool:
        if amount < 0:
            return False
        if self.spent_usd + amount > self.cap_usd + 1e-9:
            return False
        self.spent_usd += amount
        return True


# 1 tick = 1e-10 USD. Used only when the provider returns cost_in_usd_ticks.
USD_TICK = 1e-10


def estimate_tokens(text: str) -> int:
    """Character/4 heuristic. This is an estimate, not a vendor tokenizer.

    Cached tokens are ignored: the estimate does not know prompt_tokens_details
    and does not apply a cache discount. When the response includes
    cost_in_usd_ticks, that vendor figure replaces this estimate.
    """
    return max(1, (len(text) + 3) // 4)


def cost_from_usage(usage: dict[str, object] | None) -> float | None:
    """Return USD from cost_in_usd_ticks. Cached-token fields are not read."""
    if not isinstance(usage, dict):
        return None
    ticks = usage.get("cost_in_usd_ticks")
    if isinstance(ticks, bool) or not isinstance(ticks, int | float):
        return None
    return float(ticks) * USD_TICK


class LiveProvider:
    leg: ModelLeg = "live"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        ledger: SpendLedger | None = None,
        reserved_output_tokens: int = 800,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self.ledger = ledger or SpendLedger(cap_usd=settings.max_live_spend_usd)
        self.reserved_output_tokens = reserved_output_tokens

    def complete(self, prompt: str, schema: dict[str, object]) -> ProviderResult:
        del schema
        started = time.perf_counter()
        timeout_s = self.settings.llm_timeout_s
        refusal = self._refusal_reason(prompt)
        if refusal is not None:
            return ProviderResult(
                text="",
                valid=False,
                model_leg="live",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                timeout_s=timeout_s,
                cost_usd=0.0,
                error=refusal,
            )
        assert self.settings.llm_price_input_per_mtok is not None
        assert self.settings.llm_price_output_per_mtok is not None
        input_tokens = estimate_tokens(prompt)
        cost = _cost(
            input_tokens,
            self.reserved_output_tokens,
            self.settings.llm_price_input_per_mtok,
            self.settings.llm_price_output_per_mtok,
        )
        if not self.ledger.reserve(cost):
            return ProviderResult(
                text="",
                valid=False,
                model_leg="live",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                timeout_s=timeout_s,
                cost_usd=0.0,
                error="estimated cost exceeds MAX_LIVE_SPEND_USD",
            )
        try:
            text, usage = self._post(prompt)
        except httpx.TimeoutException as exc:
            return ProviderResult(
                text="",
                valid=False,
                model_leg="live",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                timeout_s=timeout_s,
                cost_usd=cost,
                error=f"timeout: {type(exc).__name__}",
                timed_out=True,
            )
        except httpx.HTTPError as exc:
            return ProviderResult(
                text="",
                valid=False,
                model_leg="live",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                timeout_s=timeout_s,
                cost_usd=cost,
                error=f"http error: {type(exc).__name__}",
            )
        cost, basis = self._reconcile(cost, usage)
        parsed = parse_briefing(text)
        return ProviderResult(
            text=text,
            valid=parsed is not None,
            model_leg="live",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            timeout_s=timeout_s,
            cost_usd=cost,
            cost_basis=basis,
            error=None if parsed is not None else "live output failed validation",
        )

    def _reconcile(
        self, reserved: float, usage: dict[str, object] | None
    ) -> tuple[float, CostBasis]:
        actual = cost_from_usage(usage)
        if actual is None:
            return reserved, "estimate"
        self.ledger.spent_usd = max(0.0, self.ledger.spent_usd + actual - reserved)
        return actual, "usage"

    def _refusal_reason(self, prompt: str) -> str | None:
        del prompt
        if not self.settings.live_llm:
            return "LIVE_LLM is off"
        if not self.settings.xai_api_key:
            return "XAI_API_KEY is empty"
        if not self.settings.llm_base_url:
            return "LLM_BASE_URL is empty"
        if not self.settings.llm_model:
            return "LLM_MODEL is empty"
        if (
            self.settings.llm_price_input_per_mtok is None
            or self.settings.llm_price_output_per_mtok is None
        ):
            return "model prices are not set in the environment"
        return None

    def _post(self, prompt: str) -> tuple[str, dict[str, object] | None]:
        url = f"{self.settings.llm_base_url}/chat/completions"
        body = {
            "model": self.settings.llm_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only JSON that matches the schema in the user message.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        timeout = httpx.Timeout(self.settings.llm_timeout_s)
        headers = {
            "Authorization": f"Bearer {self.settings.xai_api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(transport=self._transport, timeout=timeout) as client:
            response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return "", None
        usage = payload.get("usage")
        usage_dict = usage if isinstance(usage, dict) else None
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return "", usage_dict
        first = choices[0]
        if not isinstance(first, dict):
            return "", usage_dict
        message = first.get("message")
        if not isinstance(message, dict):
            return "", usage_dict
        content = message.get("content")
        text = content if isinstance(content, str) else ""
        return text, usage_dict


def _cost(input_tokens: int, output_tokens: int, price_in: float, price_out: float) -> float:
    return (input_tokens / 1_000_000) * price_in + (output_tokens / 1_000_000) * price_out


def live_requirement_errors(settings: Settings) -> list[str]:
    """Names of missing live switches. Empty means a live call is allowed to start."""
    missing: list[str] = []
    if not settings.live_llm:
        missing.append("LIVE_LLM=1")
    if not settings.xai_api_key:
        missing.append("XAI_API_KEY")
    if settings.max_live_spend_usd <= 0:
        missing.append("MAX_LIVE_SPEND_USD")
    if settings.llm_price_input_per_mtok is None or settings.llm_price_output_per_mtok is None:
        missing.append("LLM_PRICE_INPUT_PER_MTOK and LLM_PRICE_OUTPUT_PER_MTOK")
    if not settings.llm_base_url:
        missing.append("LLM_BASE_URL")
    if not settings.llm_model:
        missing.append("LLM_MODEL")
    return missing


def require_live_disabled(settings: Settings) -> None:
    if settings.live_llm:
        raise LiveConfigError("this path refuses LIVE_LLM=1")


SleepFn = Callable[[float], None]
