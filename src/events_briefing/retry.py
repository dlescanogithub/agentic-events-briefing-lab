"""Bounded retries. Backoff grows and then stops at a cap. Sleep is injectable."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from events_briefing.logging_setup import log_event

T = TypeVar("T")

logger = logging.getLogger("events_briefing.retry")


class RetryError(Exception):
    def __init__(self, message: str, *, attempts: int, timeout_s: float | None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.timeout_s = timeout_s


def backoff_seconds(attempt: int, base_s: float, cap_s: float) -> float:
    if attempt < 1:
        raise ValueError("attempt starts at 1")
    delay = base_s * (2.0 ** (attempt - 1))
    if delay < cap_s:
        return delay
    return cap_s


def run_with_retries(
    operation: Callable[[], T],
    *,
    max_attempts: int,
    base_s: float,
    cap_s: float,
    timeout_s: float | None,
    operation_name: str,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            log_event(
                logger,
                logging.INFO,
                "attempt_start",
                operation=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                timeout_s=timeout_s,
            )
            return operation()
        except retry_on as exc:
            last_error = exc
            log_event(
                logger,
                logging.WARNING,
                "attempt_failed",
                operation=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                timeout_s=timeout_s,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            if attempt >= max_attempts:
                break
            delay = backoff_seconds(attempt, base_s, cap_s)
            log_event(
                logger,
                logging.INFO,
                "backoff",
                operation=operation_name,
                attempt=attempt,
                delay_s=delay,
                cap_s=cap_s,
            )
            sleep(delay)
    raise RetryError(
        f"{operation_name} failed after {max_attempts} attempts",
        attempts=max_attempts,
        timeout_s=timeout_s,
    ) from last_error
