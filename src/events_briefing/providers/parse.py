from __future__ import annotations

import json

from events_briefing.providers.base import BriefingDraft


def parse_briefing(text: str) -> BriefingDraft | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    try:
        return BriefingDraft.model_validate(payload)
    except ValueError:
        return None
