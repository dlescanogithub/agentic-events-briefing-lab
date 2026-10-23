"""Environment-only settings. This module does not read a .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from events_briefing.paths import find_repo_root


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _optional_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return float(raw)


@dataclass(frozen=True)
class Settings:
    offline: bool
    socrata_base_url: str
    socrata_app_token: str
    socrata_timeout_s: float
    socrata_max_attempts: int
    socrata_backoff_cap_s: float
    socrata_backoff_base_s: float
    socrata_cache_ttl_s: float
    socrata_fetch_budget_s: float
    socrata_run_budget_s: float
    live_llm: bool
    xai_api_key: str
    llm_base_url: str
    llm_model: str
    llm_price_input_per_mtok: float | None
    llm_price_output_per_mtok: float | None
    max_live_spend_usd: float
    llm_timeout_s: float
    llm_max_attempts: int
    approval_state_key: str
    rubric_path: Path
    approvers_path: Path
    sensitive_path: Path
    fixture_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        root = find_repo_root()
        rubric = os.environ.get("RUBRIC_PATH", "").strip()
        fixture = os.environ.get("FIXTURE_DIR", "").strip()
        approvers = os.environ.get("APPROVERS_PATH", "").strip()
        sensitive = os.environ.get("SENSITIVE_CATEGORIES_PATH", "").strip()
        return cls(
            offline=_flag("EVENTS_OFFLINE", "1"),
            socrata_base_url=os.environ.get(
                "SOCRATA_BASE_URL", "https://data.cityofnewyork.us"
            ).strip(),
            socrata_app_token=os.environ.get("SOCRATA_APP_TOKEN", "").strip(),
            socrata_timeout_s=_float("SOCRATA_TIMEOUT_S", 15.0),
            socrata_max_attempts=_int("SOCRATA_MAX_ATTEMPTS", 3),
            socrata_backoff_cap_s=_float("SOCRATA_BACKOFF_CAP_S", 2.0),
            socrata_backoff_base_s=_float("SOCRATA_BACKOFF_BASE_S", 0.25),
            socrata_cache_ttl_s=_float("SOCRATA_CACHE_TTL_S", 300.0),
            socrata_fetch_budget_s=_float("SOCRATA_FETCH_BUDGET_S", 20.0),
            socrata_run_budget_s=_float("SOCRATA_RUN_BUDGET_S", 45.0),
            live_llm=_flag("LIVE_LLM", "0"),
            xai_api_key=os.environ.get("XAI_API_KEY", "").strip(),
            llm_base_url=os.environ.get("LLM_BASE_URL", "").strip().rstrip("/"),
            llm_model=os.environ.get("LLM_MODEL", "").strip(),
            llm_price_input_per_mtok=_optional_float("LLM_PRICE_INPUT_PER_MTOK"),
            llm_price_output_per_mtok=_optional_float("LLM_PRICE_OUTPUT_PER_MTOK"),
            max_live_spend_usd=_float("MAX_LIVE_SPEND_USD", 0.50),
            llm_timeout_s=_float("LLM_TIMEOUT_S", 20.0),
            llm_max_attempts=_int("LLM_MAX_ATTEMPTS", 2),
            approval_state_key=os.environ.get("APPROVAL_STATE_KEY", "").strip(),
            rubric_path=Path(rubric) if rubric else root / "config" / "rubric.json",
            approvers_path=Path(approvers) if approvers else root / "config" / "approvers.json",
            sensitive_path=(
                Path(sensitive) if sensitive else root / "config" / "sensitive_categories.json"
            ),
            fixture_dir=Path(fixture) if fixture else root / "fixtures",
        )

    def forced_offline(self) -> Settings:
        return replace(self, offline=True, live_llm=False)

    def secret_values(self) -> list[str]:
        return [
            value
            for value in (self.socrata_app_token, self.xai_api_key, self.approval_state_key)
            if value
        ]
