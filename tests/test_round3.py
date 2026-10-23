"""Round-3 checks: New York dates, retry cost, nonce, boroughs, run budget."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from events_briefing.briefing.gate import (
    PUBLIC_LAB_APPROVAL_KEY,
    BriefingStore,
    GateError,
)
from events_briefing.briefing.prompts import build_prompt
from events_briefing.briefing.textcheck import validate_briefing_text
from events_briefing.briefing.writer import draft_from_provider
from events_briefing.cli import main
from events_briefing.config import Settings
from events_briefing.datasets import dataset_by_id
from events_briefing.evalkit.synthetic import synthetic_incidents
from events_briefing.models import (
    CategoryGroup,
    Incident,
    LocationPrecision,
    RankedIncident,
    ScoreParts,
)
from events_briefing.normalize import local_calendar_date, parse_socrata_time
from events_briefing.pipeline import run_briefing, run_offline_demo
from events_briefing.providers.base import ProviderResult
from events_briefing.providers.live import USD_TICK
from events_briefing.providers.stub import StubProvider
from events_briefing.ranking import rank_incidents
from events_briefing.rubric import load_rubric
from events_briefing.socrata import SocrataClient

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 10, 17)
# External verification run 2, 2026-10-17: two attempts, 9798000 and 19581000 ticks.
FIRST_TICKS = 9_798_000
SECOND_TICKS = 19_581_000


def _parts() -> ScoreParts:
    return ScoreParts(severity=1, recency=1, density=0, category=1, within_band=0.5, floor=4)


def _incident(
    incident_id: str,
    when: datetime,
    borough: str,
    category: str = "ROBBERY",
) -> RankedIncident:
    incident = Incident(
        id=incident_id,
        source="nypd_complaint",
        source_dataset_id="synthetic",
        category=category,
        category_group=CategoryGroup.LIFE_SAFETY,
        severity_hint=0.9,
        created_at=when,
        borough=borough,
        community_area=None,
        geohash6="dr5reg",
        lat_rounded=40.84,
        lon_rounded=-73.9,
        location_precision=LocationPrecision.ROUNDED_2DP,
    )
    return RankedIncident(rank=1, score=4.5, parts=_parts(), incident=incident)


def _segment(headline: str, why: str, ids: list[str]) -> list[dict[str, object]]:
    return [
        {
            "headline": headline,
            "why_it_matters": why,
            "source_incident_ids": ids,
        }
    ]


def test_utc_evening_uses_new_york_date_not_utc_date() -> None:
    # 2026-10-01 03:51 UTC is 2026-09-30 23:51 in America/New_York (EDT, UTC-4).
    utc_evening = datetime(2026, 10, 1, 3, 51, tzinfo=timezone.utc)
    assert utc_evening.date().isoformat() == "2026-10-01"
    assert local_calendar_date(utc_evening).isoformat() == "2026-09-30"

    parsed = parse_socrata_time("2026-09-30T23:51:47.000")
    assert parsed.astimezone(timezone.utc).date().isoformat() == "2026-10-01"
    assert local_calendar_date(parsed).isoformat() == "2026-09-30"

    ranked = [_incident("nypd_complaint:1", utc_evening, "Bronx")]
    rubric = load_rubric(ROOT / "config" / "rubric.json")
    prompt = build_prompt(ranked, rubric.version, as_of=AS_OF)
    assert '"occurred_on": "2026-09-30"' in prompt
    assert '"occurred_on": "2026-10-01"' not in prompt

    local = _segment(
        "1 robbery on 2026-09-30",
        "As of 2026-10-17. One robbery incident dated 2026-09-30.",
        ["nypd_complaint:1"],
    )
    assert validate_briefing_text(local, ranked, AS_OF) == []

    utc_day = _segment(
        "1 robbery on 2026-10-01",
        "As of 2026-10-17. One robbery incident dated 2026-10-01.",
        ["nypd_complaint:1"],
    )
    errors = validate_briefing_text(utc_day, ranked, AS_OF)
    assert errors
    assert any("2026-09-30" in item for item in errors)


def test_as_of_uses_new_york_calendar_date(tmp_path: Path) -> None:
    moment = datetime(2026, 10, 1, 3, 30, tzinfo=timezone.utc)
    summary = run_offline_demo(tmp_path, clock=lambda: moment)
    assert summary["as_of"] == "2026-09-30"


def test_retry_cost_sums_every_attempt() -> None:
    rubric = load_rubric(ROOT / "config" / "rubric.json")
    ranked = rank_incidents(synthetic_incidents(), rubric)
    prompt = build_prompt(ranked, rubric.version, as_of=AS_OF)
    bad = json.dumps(
        {
            "segments": [
                {
                    "headline": "Robberies today",
                    "why_it_matters": "These robberies happened today.",
                    "source_incident_ids": ["syn:life-robbery"],
                }
            ]
        }
    )
    good = json.dumps(
        {
            "segments": [
                {
                    "headline": "1 robbery on 2026-10-16",
                    "why_it_matters": (
                        "As of 2026-10-17. One robbery incident dated 2026-10-16. Draft only."
                    ),
                    "source_incident_ids": ["syn:life-robbery"],
                }
            ]
        }
    )

    class Priced:
        leg = "live"

        def __init__(self) -> None:
            self.n = 0

        def complete(self, prompt_text: str, schema: dict[str, object]) -> ProviderResult:
            del prompt_text, schema
            self.n += 1
            ticks = FIRST_TICKS if self.n == 1 else SECOND_TICKS
            text = bad if self.n == 1 else good
            return ProviderResult(
                text=text,
                valid=True,
                model_leg="live",
                cost_usd=ticks * USD_TICK,
                cost_basis="usage",
            )

    _segments, leg, result = draft_from_provider(
        ranked,
        Priced(),
        prompt=prompt,
        max_attempts=2,
        as_of=AS_OF,
    )
    assert leg == "live"
    assert result.attempts == 2
    assert result.cost_basis == "usage"
    assert result.cost_usd == pytest.approx((FIRST_TICKS + SECOND_TICKS) * USD_TICK)
    assert result.cost_usd == pytest.approx(0.0029379)


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


def test_replay_and_cross_id_are_rejected(tmp_path: Path) -> None:
    store = BriefingStore(tmp_path, demo=True)
    _draft(store, "prog-x")
    approved = (tmp_path / "state" / "prog-x.json").read_bytes()
    (tmp_path / "state" / "prog-y.json").write_bytes(approved)
    with pytest.raises(GateError, match="program id"):
        store.publish("prog-y")
    assert not (tmp_path / "outbox" / "prog-y.json").exists()

    store.publish("prog-x")
    outbox = (tmp_path / "outbox" / "prog-x.json").read_bytes()
    (tmp_path / "state" / "prog-x.json").write_bytes(approved)
    with pytest.raises(GateError, match="nonce"):
        store.publish("prog-x")
    assert (tmp_path / "outbox" / "prog-x.json").read_bytes() == outbox

    ledger = tmp_path / "state" / "nonce-ledger.json"
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["consumed"] = []
    ledger.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "state" / "prog-x.json").write_bytes(approved)
    with pytest.raises(GateError, match="tampered"):
        store.publish("prog-x")


def test_public_lab_key_is_refused_outside_demo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(GateError, match="rotate"):
        BriefingStore(tmp_path / "locked", state_key=PUBLIC_LAB_APPROVAL_KEY, demo=False)
    BriefingStore(tmp_path / "demo", state_key=PUBLIC_LAB_APPROVAL_KEY, demo=True)

    monkeypatch.setenv("APPROVAL_STATE_KEY", PUBLIC_LAB_APPROVAL_KEY)
    assert main(["briefing", "--out", str(tmp_path / "brief")]) == 1
    assert "rotate" in capsys.readouterr().err

    monkeypatch.delenv("APPROVAL_STATE_KEY", raising=False)
    assert main(["demo", "--offline", "--out", str(tmp_path / "clean")]) == 0
    assert main(["eval"]) == 0
    assert main(["briefing", "--out", str(tmp_path / "empty")]) == 1
    assert "APPROVAL_STATE_KEY" in capsys.readouterr().err


def test_borough_breakdown_must_match_cited_incidents() -> None:
    when = datetime(2026, 6, 30, 16, 0, tzinfo=timezone.utc)
    ranked = [
        _incident("nypd_complaint:1", when, "Brooklyn"),
        _incident("nypd_complaint:2", when, "Brooklyn"),
        _incident("nypd_complaint:3", when, "Bronx"),
        _incident("nypd_complaint:4", when, "Bronx"),
        _incident("nypd_complaint:5", when, "Bronx"),
    ]
    for index, item in enumerate(ranked, start=1):
        ranked[index - 1] = item.model_copy(update={"rank": index})
    ids = [item.incident.id for item in ranked]
    wrong = _segment(
        "5 robberies on 2026-06-30",
        "As of 2026-10-17. one in Brooklyn and four in the Bronx.",
        ids,
    )
    errors = validate_briefing_text(wrong, ranked, AS_OF)
    assert any("Brooklyn" in item for item in errors)
    assert any("Bronx" in item for item in errors)

    right = _segment(
        "5 robberies on 2026-06-30",
        "As of 2026-10-17. two in Brooklyn and three in the Bronx.",
        ids,
    )
    assert validate_briefing_text(right, ranked, AS_OF) == []

    invented = _segment(
        "5 robberies on 2026-06-30",
        "As of 2026-10-17. two in Brooklyn and three in Queens.",
        ids,
    )
    queens = validate_briefing_text(invented, ranked, AS_OF)
    assert any("Queens" in item for item in queens)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_run_budget_stops_later_pulls(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = _Clock()
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        clock.advance(12)
        raise httpx.ReadTimeout("timed out")

    snapshot = {
        "rows": [
            {
                "unique_key": "snap",
                "created_date": "2026-10-16T12:00:00.000",
                "agency": "NYPD",
                "complaint_type": "Noise",
                "borough": "MANHATTAN",
                "community_board": "01 MANHATTAN",
                "lat_rounded": 40.71,
                "lon_rounded": -74.0,
            }
        ]
    }
    (tmp_path / "erm2-nwe9.json").write_text(json.dumps(snapshot), encoding="utf-8")
    settings = replace(
        Settings.from_env(),
        offline=False,
        live_llm=False,
        socrata_fetch_budget_s=30,
        socrata_run_budget_s=12,
        socrata_timeout_s=10,
        socrata_max_attempts=3,
        socrata_backoff_base_s=0.25,
        socrata_backoff_cap_s=2,
        approval_state_key="unit-rotated-gate-key",
    )
    client = SocrataClient(
        settings,
        transport=httpx.MockTransport(handler),
        snapshot_dir=tmp_path,
        clock=clock,
        sleep=clock.advance,
    )
    caplog.set_level(logging.WARNING, logger="events_briefing.socrata")
    spec = dataset_by_id("erm2-nwe9")
    first = client.query(spec, "x", "created_date DESC", 1)
    second = client.query(spec, "y", "created_date DESC", 1)
    assert calls["n"] == 1
    assert first[0]["unique_key"] == "snap"
    assert second[0]["unique_key"] == "snap"
    assert client.fallback_pulls == 2
    assert client.live_pulls == 0
    reasons = [
        str(record.fields.get("reason", ""))
        for record in caplog.records
        if getattr(record, "fields", None) and record.getMessage() == "socrata_budget_fallback"
    ]
    assert any("SODA refresh budget" in reason for reason in reasons)


def test_partial_snapshot_fallback_is_not_labeled_online(tmp_path: Path) -> None:
    clock = _Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "erm2-nwe9" in url:
            clock.advance(15)
            raise httpx.ReadTimeout("timed out")
        if "5uac-w243" in url:
            row: dict[str, object] = {
                "cmplnt_num": "8",
                "cmplnt_fr_dt": "2026-06-30T16:00:00.000",
                "law_cat_cd": "FELONY",
                "ofns_desc": "ROBBERY",
                "boro_nm": "BRONX",
                "latitude": "40.84",
                "longitude": "-73.90",
            }
        else:
            row = {
                "starfire_incident_id": "F9",
                "incident_datetime": "2026-09-30T12:00:00.000",
                "incident_borough": "BROOKLYN",
                "communitydistrict": "306",
                "incident_classification": "Structural",
                "incident_classification_group": "Structural Fires",
                "highest_alarm_level": "All Hands Working",
            }
        return httpx.Response(200, json=[row])

    snapshot = {
        "rows": [
            {
                "unique_key": "snap",
                "created_date": "2026-10-16T12:00:00.000",
                "agency": "NYPD",
                "complaint_type": "Noise",
                "borough": "MANHATTAN",
                "community_board": "01 MANHATTAN",
                "lat_rounded": 40.71,
                "lon_rounded": -74.0,
            }
        ]
    }
    (tmp_path / "snaps").mkdir()
    (tmp_path / "snaps" / "erm2-nwe9.json").write_text(json.dumps(snapshot), encoding="utf-8")
    settings = replace(
        Settings.from_env(),
        offline=False,
        live_llm=False,
        socrata_fetch_budget_s=20,
        socrata_run_budget_s=120,
        socrata_timeout_s=15,
        socrata_max_attempts=3,
        socrata_backoff_base_s=0.25,
        socrata_backoff_cap_s=2,
        approval_state_key="unit-rotated-gate-key",
    )
    client = SocrataClient(
        settings,
        transport=httpx.MockTransport(handler),
        snapshot_dir=tmp_path / "snaps",
        clock=clock,
        sleep=lambda _seconds: None,
    )
    summary = run_briefing(
        tmp_path / "out",
        settings,
        online=True,
        live=False,
        decision="reject",
        client=client,
        provider=StubProvider(),
    )
    assert summary["mode"].startswith("mixed")
    assert summary["mode"] != "online (SODA refresh then rank)"
    assert "snapshot fallback" in str(summary["mode"])
    trace = [
        json.loads(line)
        for line in (tmp_path / "out" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert trace[-1]["mode"] == summary["mode"]
    assert trace[-1]["snapshot_fallbacks"] > 0
    assert trace[-1]["live_pulls"] > 0
