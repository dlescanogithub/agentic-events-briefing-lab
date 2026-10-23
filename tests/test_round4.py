"""Round-4 checks: scoped category counts, prompt counts, ledger delete."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from events_briefing.briefing.gate import BriefingStore, GateError, _mac
from events_briefing.briefing.prompts import build_prompt
from events_briefing.briefing.textcheck import (
    EXTERNAL_FALSE_POSITIVES,
    EXTERNAL_INCORRECT_DETECTED,
    EXTERNAL_SOURCE,
    POST_CHANGE_RECALL,
    validate_briefing_text,
)
from events_briefing.models import (
    CategoryGroup,
    Incident,
    LocationPrecision,
    RankedIncident,
    ScoreParts,
)
from events_briefing.providers.base import BRIEFING_SCHEMA
from events_briefing.providers.stub import StubProvider
from events_briefing.rubric import load_rubric

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 10, 17)
WHEN = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)


def _parts() -> ScoreParts:
    return ScoreParts(severity=1, recency=1, density=0, category=1, within_band=0.5, floor=4)


def _fire(incident_id: str, borough: str) -> RankedIncident:
    incident = Incident(
        id=incident_id,
        source="fdny_fire",
        source_dataset_id="synthetic",
        category="Structural Fires",
        category_group=CategoryGroup.LIFE_SAFETY,
        severity_hint=0.9,
        created_at=WHEN,
        borough=borough,
        community_area=None,
        geohash6="dr5reg",
        lat_rounded=40.84,
        lon_rounded=-73.9,
        location_precision=LocationPrecision.BOROUGH_CENTROID,
    )
    return RankedIncident(rank=1, score=4.5, parts=_parts(), incident=incident)


def _fires() -> list[RankedIncident]:
    ranked = [
        _fire("fdny:1", "Brooklyn"),
        _fire("fdny:2", "Brooklyn"),
        _fire("fdny:3", "Bronx"),
        _fire("fdny:4", "Bronx"),
        _fire("fdny:5", "Bronx"),
    ]
    for index, item in enumerate(ranked, start=1):
        ranked[index - 1] = item.model_copy(update={"rank": index})
    return ranked


def _segment(headline: str, why: str, ids: list[str]) -> list[dict[str, object]]:
    return [
        {
            "headline": headline,
            "why_it_matters": why,
            "source_incident_ids": ids,
        }
    ]


def _dated(headline: str) -> list[dict[str, object]]:
    return _segment(
        headline,
        "As of 2026-10-17. Dated 2026-09-30.",
        [item.incident.id for item in _fires()],
    )


def test_borough_scoped_category_count_is_not_a_false_positive() -> None:
    ranked = _fires()
    short = _dated("Two structural fires in Brooklyn and three in the Bronx")
    assert validate_briefing_text(short, ranked, AS_OF) == []

    longer = _dated(
        "Two structural fires occurred in Brooklyn and three in the Bronx on 2026-09-30"
    )
    assert validate_briefing_text(longer, ranked, AS_OF) == []


def test_wrong_scoped_and_unscoped_category_counts_still_fail() -> None:
    ranked = _fires()
    scoped = _dated("Four structural fires in Brooklyn and three in the Bronx")
    scoped_errors = validate_briefing_text(scoped, ranked, AS_OF)
    assert any("Brooklyn" in item and "cites 2" in item for item in scoped_errors)

    unscoped = _dated("2 structural fires")
    unscoped_errors = validate_briefing_text(unscoped, ranked, AS_OF)
    assert any("cites 5" in item for item in unscoped_errors)


def test_checker_misses_saw_counts_casualties_and_superlatives() -> None:
    """Known gaps. A clean result here is not evidence the checker works."""
    ranked = _fires()
    saw = _dated("Brooklyn saw 4 fires and the Bronx saw 1")
    casualties = _dated("Structural fires on 2026-09-30, killing 3 people")
    superlative = _dated("The worst structural fires of the year were on 2026-09-30")
    assert validate_briefing_text(saw, ranked, AS_OF) == []
    assert validate_briefing_text(casualties, ranked, AS_OF) == []
    assert validate_briefing_text(superlative, ranked, AS_OF) == []


def test_textcheck_external_limits_are_cited_not_a_control() -> None:
    assert EXTERNAL_INCORRECT_DETECTED == "13/19"
    assert EXTERNAL_FALSE_POSITIVES == "1/10"
    assert "VERIFY_REPORT_10" in EXTERNAL_SOURCE
    assert "not conclusive" in EXTERNAL_SOURCE
    assert POST_CHANGE_RECALL == "not measured yet"
    metrics = (ROOT / "docs" / "METRICS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for text in (metrics, readme):
        assert "13/19" in text
        assert "1/10" in text
        assert "VERIFY_REPORT_10" in text
        assert "not measured yet" in text
        assert "Brooklyn saw 4" in text
        assert "not a reliable control" in text


def test_prompt_carries_precomputed_borough_counts() -> None:
    rubric = load_rubric(ROOT / "config" / "rubric.json")
    ranked = _fires()
    prompt = build_prompt(ranked, rubric.version, as_of=AS_OF)
    assert "BOROUGH_COUNTS:" in prompt
    assert "Do not count incidents yourself." in prompt
    assert "Structural Fires: 5 total; 3 in Bronx; 2 in Brooklyn" in prompt
    assert prompt.index("BOROUGH_COUNTS:") < prompt.index("INCIDENT_JSON:")
    result = StubProvider().complete(prompt, BRIEFING_SCHEMA)
    assert result.valid is True


def _draft(store: BriefingStore, program_id: str) -> None:
    store.create(
        program_id=program_id,
        model_leg="stub",
        rubric_version="v",
        segments=[
            {
                "headline": "Draft",
                "why_it_matters": "Draft only.",
                "source_incident_ids": ["syn:life-fire"],
            }
        ],
        inputs_hash="abc",
    )
    store.submit(program_id)
    store.decide(
        program_id,
        "approve",
        actor="simulated-editor",
        simulated=True,
        note="SIMULATED",
    )


def test_deleting_the_nonce_ledger_does_not_reopen_replay(tmp_path: Path) -> None:
    store = BriefingStore(tmp_path, demo=True)
    _draft(store, "prog-x")
    approved = (tmp_path / "state" / "prog-x.json").read_bytes()
    store.publish("prog-x")
    outbox = (tmp_path / "outbox" / "prog-x.json").read_bytes()
    (tmp_path / "state" / "nonce-ledger.json").unlink()
    (tmp_path / "state" / "prog-x.json").write_bytes(approved)
    with pytest.raises(GateError, match="ledger"):
        store.publish("prog-x")
    assert (tmp_path / "outbox" / "prog-x.json").read_bytes() == outbox
    with pytest.raises(GateError, match="ledger"):
        store.create(
            program_id="prog-new",
            model_leg="stub",
            rubric_version="v",
            segments=[],
            inputs_hash="z",
        )


def test_substituted_ledger_does_not_match_the_signed_head(tmp_path: Path) -> None:
    store = BriefingStore(tmp_path, demo=True)
    _draft(store, "prog-x")
    approved = (tmp_path / "state" / "prog-x.json").read_bytes()
    store.publish("prog-x")
    outbox = (tmp_path / "outbox" / "prog-x.json").read_bytes()
    other: dict[str, object] = {"consumed": [{"nonce": "other-nonce", "program_id": "other"}]}
    other["ledger_mac"] = _mac(other, store.state_key, exclude="ledger_mac")
    (tmp_path / "state" / "nonce-ledger.json").write_text(json.dumps(other), encoding="utf-8")
    (tmp_path / "state" / "prog-x.json").write_bytes(approved)
    with pytest.raises(GateError, match="ledger"):
        store.publish("prog-x")
    assert (tmp_path / "outbox" / "prog-x.json").read_bytes() == outbox


def test_restoring_ledger_and_state_together_still_replays(tmp_path: Path) -> None:
    """Possession of the signing key can restore both files. Not an authenticated channel."""
    store = BriefingStore(tmp_path, demo=True)
    _draft(store, "prog-x")
    approved = (tmp_path / "state" / "prog-x.json").read_bytes()
    ledger = (tmp_path / "state" / "nonce-ledger.json").read_bytes()
    store.publish("prog-x")
    (tmp_path / "state" / "prog-x.json").write_bytes(approved)
    (tmp_path / "state" / "nonce-ledger.json").write_bytes(ledger)
    again = store.publish("prog-x")
    assert again["status"] == "PUBLISHED"


def test_soda_budget_wording_is_refresh_only_not_the_whole_command() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    how = (ROOT / "docs" / "HOW_IT_WORKS.md").read_text(encoding="utf-8")
    risks = (ROOT / "docs" / "RISKS.md").read_text(encoding="utf-8")
    cost = (ROOT / "docs" / "COST.md").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    blob = "\n".join((readme, how, risks, cost, example))
    assert "total run cap" not in blob.lower()
    assert "total run budget" not in blob.lower()
    assert "caps the whole" not in blob.lower()
    for text in (readme, how, risks, cost, example):
        assert "SOCRATA_RUN_BUDGET_S" in text
        assert "MAX_LIVE_SPEND_USD" in text
    assert "only the SODA refresh" in readme
    assert "only the SODA refresh" in risks
    assert "only the SODA refresh" in how
