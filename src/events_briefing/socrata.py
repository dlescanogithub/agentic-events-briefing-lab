"""SODA client: timeouts, bounded retries, TTL cache, and offline snapshots."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from events_briefing.config import Settings
from events_briefing.datasets import DATASETS, DatasetSpec
from events_briefing.logging_setup import log_event
from events_briefing.privacy import as_float, forbidden_keys, round_coord
from events_briefing.retry import RetryError, run_with_retries

logger = logging.getLogger("events_briefing.socrata")

SNAPSHOT_ALLOW = {
    "nyc_311": (
        "unique_key",
        "created_date",
        "agency",
        "complaint_type",
        "borough",
        "community_board",
        "lat_rounded",
        "lon_rounded",
    ),
    "nypd_complaint": (
        "cmplnt_num",
        "cmplnt_fr_dt",
        "law_cat_cd",
        "ofns_desc",
        "boro_nm",
        "lat_rounded",
        "lon_rounded",
    ),
    "fdny_fire": (
        "starfire_incident_id",
        "incident_datetime",
        "incident_borough",
        "communitydistrict",
        "incident_classification",
        "incident_classification_group",
        "highest_alarm_level",
    ),
}


class SocrataError(RuntimeError):
    def __init__(self, message: str, *, timeout_s: float | None, attempts: int) -> None:
        super().__init__(message)
        self.timeout_s = timeout_s
        self.attempts = attempts


@dataclass
class CacheEntry:
    stored_at: float
    payload: list[dict[str, Any]]


class TtlCache:
    def __init__(self, ttl_s: float, clock: Callable[[], float] | None = None) -> None:
        self.ttl_s = ttl_s
        self._clock = clock or time.monotonic
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> list[dict[str, Any]] | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if self._clock() - entry.stored_at > self.ttl_s:
            del self._items[key]
            return None
        return entry.payload

    def put(self, key: str, payload: list[dict[str, Any]]) -> None:
        self._items[key] = CacheEntry(stored_at=self._clock(), payload=payload)


class _BudgetExceeded(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SocrataClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        cache: TtlCache | None = None,
        sleep: Callable[[float], None] | None = None,
        snapshot_dir: Path | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self.cache = cache or TtlCache(settings.socrata_cache_ttl_s)
        self._sleep = sleep
        self.snapshot_dir = snapshot_dir or (settings.fixture_dir / "snapshots")
        self._clock = clock or time.monotonic
        self._run_started: float | None = None
        self.live_pulls = 0
        self.fallback_pulls = 0

    def query(
        self,
        spec: DatasetSpec,
        pull_where: str,
        pull_order: str,
        pull_limit: int,
    ) -> list[dict[str, Any]]:
        if self.settings.offline:
            return self._read_snapshot(spec.dataset_id)
        return self._query_online(spec, pull_where, pull_order, pull_limit)

    def _read_snapshot(self, dataset_id: str) -> list[dict[str, Any]]:
        path = self.snapshot_dir / f"{dataset_id}.json"
        if not path.is_file():
            raise SocrataError(
                f"offline snapshot missing: {path}",
                timeout_s=None,
                attempts=0,
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise SocrataError(
                f"snapshot {path} has no rows list",
                timeout_s=None,
                attempts=0,
            )
        leaked = forbidden_keys(rows)
        if leaked:
            raise SocrataError(
                f"snapshot {path} contains forbidden keys: {leaked}",
                timeout_s=None,
                attempts=0,
            )
        return rows

    def _query_online(
        self,
        spec: DatasetSpec,
        pull_where: str,
        pull_order: str,
        pull_limit: int,
    ) -> list[dict[str, Any]]:
        params = {
            "$select": ",".join(spec.select_fields),
            "$where": pull_where,
            "$order": pull_order,
            "$limit": str(pull_limit),
        }
        url = (
            f"{self.settings.socrata_base_url}/resource/{spec.dataset_id}.json?{urlencode(params)}"
        )
        cached = self.cache.get(url)
        if cached is not None:
            self._touch_run()
            self.live_pulls += 1
            log_event(
                logger,
                logging.INFO,
                "socrata_cache_hit",
                dataset_id=spec.dataset_id,
                timeout_s=self.settings.socrata_timeout_s,
            )
            return cached

        self._touch_run()
        started = self._clock()

        def operation() -> list[dict[str, Any]]:
            left, scope = self._budget_left(started)
            if left < self.settings.socrata_timeout_s:
                raise _BudgetExceeded(self._budget_reason(scope, left, "before the next attempt"))
            call_timeout = min(self.settings.socrata_timeout_s, left)
            return self._once(url, spec.dataset_id, timeout_s=call_timeout)

        def budget_sleep(delay: float) -> None:
            left, scope = self._budget_left(started)
            if left <= delay or left < self.settings.socrata_timeout_s:
                raise _BudgetExceeded(self._budget_reason(scope, left, "during backoff"))
            (self._sleep or _default_sleep)(delay)

        try:
            rows = run_with_retries(
                operation,
                max_attempts=self.settings.socrata_max_attempts,
                base_s=self.settings.socrata_backoff_base_s,
                cap_s=self.settings.socrata_backoff_cap_s,
                timeout_s=self.settings.socrata_timeout_s,
                operation_name=f"socrata:{spec.dataset_id}",
                retry_on=(httpx.TimeoutException, httpx.TransportError, _RetryableStatus),
                sleep=budget_sleep,
            )
        except _BudgetExceeded as exc:
            self.fallback_pulls += 1
            log_event(
                logger,
                logging.WARNING,
                "socrata_budget_fallback",
                dataset_id=spec.dataset_id,
                reason=exc.reason,
                fetch_budget_s=self.settings.socrata_fetch_budget_s,
                run_budget_s=self.settings.socrata_run_budget_s,
                elapsed_s=round(self._clock() - started, 3),
            )
            return self._read_snapshot(spec.dataset_id)
        except RetryError as exc:
            raise SocrataError(str(exc), timeout_s=exc.timeout_s, attempts=exc.attempts) from exc
        self.cache.put(url, rows)
        self.live_pulls += 1
        return rows

    def _touch_run(self) -> None:
        if self._run_started is None:
            self._run_started = self._clock()

    def _budget_left(self, fetch_started: float) -> tuple[float, str]:
        self._touch_run()
        assert self._run_started is not None
        fetch_left = self.settings.socrata_fetch_budget_s - (self._clock() - fetch_started)
        run_left = self.settings.socrata_run_budget_s - (self._clock() - self._run_started)
        if run_left <= fetch_left:
            return run_left, "run"
        return fetch_left, "fetch"

    def _budget_reason(self, scope: str, left: float, when: str) -> str:
        if scope == "run":
            cap = self.settings.socrata_run_budget_s
            label = "SODA refresh budget"
        else:
            cap = self.settings.socrata_fetch_budget_s
            label = "total fetch budget"
        return f"{label} exhausted {when}; {left:.3f}s left of {cap:.3f}s"

    def _once(
        self, url: str, dataset_id: str, timeout_s: float | None = None
    ) -> list[dict[str, Any]]:
        limit = self.settings.socrata_timeout_s if timeout_s is None else timeout_s
        timeout = httpx.Timeout(limit)
        headers = {"Accept": "application/json"}
        if self.settings.socrata_app_token:
            headers["X-App-Token"] = self.settings.socrata_app_token
        started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "socrata_request",
            dataset_id=dataset_id,
            timeout_s=self.settings.socrata_timeout_s,
            host=self.settings.socrata_base_url,
        )
        try:
            with httpx.Client(transport=self._transport, timeout=timeout) as client:
                response = client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            log_event(
                logger,
                logging.WARNING,
                "socrata_timeout",
                dataset_id=dataset_id,
                timeout_s=self.settings.socrata_timeout_s,
                elapsed_ms=elapsed_ms,
                error_type=type(exc).__name__,
            )
            raise
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        log_event(
            logger,
            logging.INFO,
            "socrata_response",
            dataset_id=dataset_id,
            status_code=response.status_code,
            timeout_s=self.settings.socrata_timeout_s,
            elapsed_ms=elapsed_ms,
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            raise _RetryableStatus(f"status {response.status_code}")
        if response.status_code >= 400:
            raise SocrataError(
                f"socrata status {response.status_code} for {dataset_id}",
                timeout_s=self.settings.socrata_timeout_s,
                attempts=1,
            )
        body = response.json()
        if not isinstance(body, list):
            raise SocrataError(
                f"socrata payload for {dataset_id} was not a list",
                timeout_s=self.settings.socrata_timeout_s,
                attempts=1,
            )
        return body


class _RetryableStatus(Exception):
    pass


def _default_sleep(seconds: float) -> None:
    time.sleep(seconds)


def project_snapshot_row(spec: DatasetSpec, row: dict[str, Any]) -> dict[str, Any]:
    """Keep an allowlist and replace raw coordinates with 2-decimal values."""
    projected: dict[str, Any] = {}
    allowed = SNAPSHOT_ALLOW[spec.source]
    lat = as_float(row.get("latitude"))
    lon = as_float(row.get("longitude"))
    for field in allowed:
        if field == "lat_rounded":
            projected[field] = None if lat is None else round_coord(lat)
        elif field == "lon_rounded":
            projected[field] = None if lon is None else round_coord(lon)
        elif field in row:
            projected[field] = row[field]
    leaked = forbidden_keys(projected)
    if leaked:
        raise SocrataError(
            f"projection still has forbidden keys: {leaked}",
            timeout_s=None,
            attempts=0,
        )
    return projected


def write_snapshots(
    client: SocrataClient,
    *,
    captured_at: datetime | None = None,
    destination: Path | None = None,
) -> Path:
    """Pull each configured query, coarsen, and write snapshot files. Manual only."""
    if client.settings.offline:
        raise SocrataError(
            "refresh-snapshots refuses to run while EVENTS_OFFLINE is on",
            timeout_s=None,
            attempts=0,
        )
    moment = captured_at or datetime.now(timezone.utc)
    dest = destination or client.snapshot_dir
    dest.mkdir(parents=True, exist_ok=True)
    manifest_sets: list[dict[str, Any]] = []
    for spec in DATASETS:
        merged: dict[str, dict[str, Any]] = {}
        pull_notes: list[dict[str, Any]] = []
        for pull in spec.pulls:
            rows = client.query(spec, pull.where, pull.order, pull.limit)
            pull_notes.append(
                {
                    "where": pull.where,
                    "order": pull.order,
                    "limit": pull.limit,
                    "returned": len(rows),
                }
            )
            for row in rows:
                projected = project_snapshot_row(spec, row)
                row_id = str(projected.get(spec.id_field) or "")
                if row_id and row_id not in merged:
                    merged[row_id] = projected
        document = {
            "dataset_id": spec.dataset_id,
            "source": spec.source,
            "title": spec.title,
            "page_url": spec.page_url,
            "captured_at": moment.isoformat(),
            "select_fields_requested": list(spec.select_fields),
            "precision": (
                "latitude/longitude rounded to 2 decimal degrees before write "
                "(about 1.1 km). Raw coordinates are not stored. "
                "FDNY rows have no point coordinates in the source; none are invented here."
            ),
            "pulls": pull_notes,
            "rows": list(merged.values()),
        }
        (dest / f"{spec.dataset_id}.json").write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_sets.append(
            {
                "dataset_id": spec.dataset_id,
                "source": spec.source,
                "row_count": len(merged),
                "page_url": spec.page_url,
            }
        )
    manifest = {
        "captured_at": moment.isoformat(),
        "access_date": moment.date().isoformat(),
        "note": (
            "Aggregate-safe fields only. Capture command: "
            "python -m events_briefing refresh-snapshots --online"
        ),
        "datasets": manifest_sets,
    }
    manifest_path = dest / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path
