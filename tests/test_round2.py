"""Round-2 checks: prose, gate, claims, sensitive rows, attribution, live CLI, SODA budget."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from events_briefing.briefing.gate import BriefingStore, GateError
from events_briefing.briefing.invariants import (
    EXTERNAL_FP_EXAMPLES,
    LAB_REQUERY,
    MEASURED_NEGATION_FALSE_POSITIVES,
    MEASURED_PARAPHRASE_RECALL,
    POST_CHANGE_FALSE_POSITIVES,
    POST_CHANGE_RECALL,
    POST_CHANGE_SOURCE,
    claim_hits,
    claims_published_while_outbox_empty,
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
from events_briefing.pipeline import run_briefing, run_offline_demo
from events_briefing.providers.base import BRIEFING_SCHEMA
from events_briefing.providers.cassette import CassetteProvider
from events_briefing.providers.live import USD_TICK, LiveProvider, SpendLedger, estimate_tokens
from events_briefing.providers.stub import StubProvider
from events_briefing.ranking import rank_incidents
from events_briefing.rubric import load_rubric
from events_briefing.sensitive import is_sensitive
from events_briefing.socrata import SocrataClient, SocrataError

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 10, 17)

# The 2026-10-17 check did not store its 20 paraphrase strings or its 20 negation
# strings. These three are the false-positive class that check measured (3/20):
# a publish/send verb inside a negation. They are not a new recall corpus.
NEGATION_LITERALS = (
    "The briefing was not published.",
    "The note was not emailed.",
    "The bulletin was never sent.",
)
PARAPHRASE_NOTE = (
    "The rundown is already in the inbox.",
    "Readers can see the item.",
    "We walked the copy to the desk.",
)


def _rubric():
    return load_rubric(ROOT / "config" / "rubric.json")


def _parts() -> ScoreParts:
    return ScoreParts(severity=1, recency=1, density=0, category=1, within_band=0.5, floor=4)


def _one(category: str, when: str, incident_id: str = "nypd_complaint:1") -> list[RankedIncident]:
    moment = datetime.fromisoformat(when).replace(tzinfo=timezone.utc)
    incident = Incident(
        id=incident_id,
        source="nypd_complaint",
        source_dataset_id="synthetic",
        category=category,
        category_group=CategoryGroup.LIFE_SAFETY,
        severity_hint=0.9,
        created_at=moment,
        borough="Bronx",
        community_area=None,
        geohash6="dr5reg",
        lat_rounded=40.84,
        lon_rounded=-73.9,
        location_precision=LocationPrecision.ROUNDED_2DP,
    )
    return [RankedIncident(rank=1, score=4.5, parts=_parts(), incident=incident)]


def _segment(headline: str, why: str, ids: list[str]) -> list[dict[str, object]]:
    return [
        {
            "headline": headline,
            "why_it_matters": why,
            "source_incident_ids": ids,
        }
    ]


def test_briefing_text_rejects_today_and_plural_then_retries() -> None:
    rubric = _rubric()
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
    segments, leg, result = draft_from_provider(
        ranked,
        CassetteProvider([bad, good]),
        prompt=prompt,
        max_attempts=2,
        as_of=AS_OF,
    )
    assert leg == "cassette"
    assert result.attempts == 2
    assert "robbery" in str(segments[0]["headline"])
    assert "today" not in json.dumps(segments).lower()

    fallback_segments, fallback_leg, _fallback = draft_from_provider(
        ranked,
        CassetteProvider([bad, bad]),
        prompt=prompt,
        max_attempts=2,
        as_of=AS_OF,
    )
    assert fallback_leg == "fallback"
    assert fallback_segments
    assert "AS_OF" in prompt
    assert "occurred_on" in prompt


def test_relative_time_and_counts() -> None:
    june = _one("ROBBERY", "2026-06-30T16:00:00")
    stale = _segment(
        "Robberies today",
        "These robberies happened today.",
        ["nypd_complaint:1"],
    )
    assert validate_briefing_text(stale, june, AS_OF)

    singular = _segment(
        "1 robbery on 2026-06-30",
        "As of 2026-10-17. One robbery incident dated 2026-06-30.",
        ["nypd_complaint:1"],
    )
    assert validate_briefing_text(singular, june, AS_OF) == []

    same_day = _one("ROBBERY", "2026-10-17T15:00:00")
    supported = _segment(
        "1 robbery today",
        "As of 2026-10-17. One robbery incident dated 2026-10-17.",
        ["nypd_complaint:1"],
    )
    assert validate_briefing_text(supported, same_day, AS_OF) == []

    yesterday = AS_OF - timedelta(days=1)
    prior = _one("ROBBERY", f"{yesterday.isoformat()}T12:00:00")
    yesterday_text = _segment(
        "1 robbery yesterday",
        f"As of {AS_OF.isoformat()}. One robbery incident dated {yesterday.isoformat()}.",
        ["nypd_complaint:1"],
    )
    assert validate_briefing_text(yesterday_text, prior, AS_OF) == []


def test_gate_rejects_tamper_empty_actor_and_unlisted_actor(tmp_path: Path) -> None:
    store = BriefingStore(tmp_path, demo=True)
    store.create(
        program_id="prog-gate",
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
    store.submit("prog-gate")
    with pytest.raises(GateError, match="empty"):
        store.decide("prog-gate", "approve", actor="  ", simulated=True, note="no")
    with pytest.raises(GateError, match="allowlist"):
        store.decide("prog-gate", "approve", actor="stranger", simulated=True, note="no")
    with pytest.raises(GateError, match="authenticated channel"):
        store.decide(
            "prog-gate",
            "approve",
            actor="simulated-editor",
            simulated=False,
            note="no",
        )
    assert store.load("prog-gate")["status"] == "PENDING_APPROVAL"
    assert store.outbox_count() == 0

    path = tmp_path / "state" / "prog-gate.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "APPROVED"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GateError, match="tampered state"):
        store.publish("prog-gate")
    assert store.outbox_count() == 0

    bare = BriefingStore(tmp_path / "bare", state_key="")
    with pytest.raises(GateError, match="APPROVAL_STATE_KEY"):
        bare.create(
            program_id="prog-bare",
            model_leg="stub",
            rubric_version="v",
            segments=[],
            inputs_hash="z",
        )


def test_claim_heuristic_negation_window_and_measured_limits() -> None:
    assert MEASURED_PARAPHRASE_RECALL == "0/20"
    assert MEASURED_NEGATION_FALSE_POSITIVES == "3/20"
    assert POST_CHANGE_RECALL == "7/20"
    assert POST_CHANGE_FALSE_POSITIVES == "3/20"
    assert "VERIFY_REPORT_9" in POST_CHANGE_SOURCE
    assert "not conclusive" in POST_CHANGE_SOURCE
    assert LAB_REQUERY == "not measured yet"
    for text in NEGATION_LITERALS:
        assert claim_hits(text) == []
        assert claims_published_while_outbox_empty(text, 0) is False
    assert claim_hits("The report was sent.")
    assert claim_hits("The bulletin was published and sent.")
    for text in PARAPHRASE_NOTE:
        assert claim_hits(text) == []
    for text in EXTERNAL_FP_EXAMPLES:
        assert claim_hits(text), text
    metrics = (ROOT / "docs/METRICS.md").read_text(encoding="utf-8")
    assert "0/20" in metrics
    assert "7/20" in metrics
    assert "3/20" in metrics
    assert "not conclusive" in metrics
    assert "weak heuristic" in metrics
    assert "not measured yet" in metrics
    assert "2026-10-17" in metrics
    assert "VERIFY_REPORT_9" in metrics


def test_sensitive_categories_leave_the_public_map_and_briefing(tmp_path: Path) -> None:
    assert is_sensitive("SEX CRIMES", ("sex crime",))
    assert is_sensitive("CHILD ABUSE", ("child",))
    assert is_sensitive("DOMESTIC VIOLENCE", ("domestic",))
    assert is_sensitive("RAPE", ("rape",))
    assert not is_sensitive("ROBBERY", ("sex crime", "child", "domestic"))

    summary = run_offline_demo(tmp_path)
    assert summary["withheld_sensitive"] == 1
    assert summary["incident_count"] == 67
    assert summary["mode"] == "snapshots"
    withheld = json.loads((tmp_path / "withheld_sensitive.json").read_text(encoding="utf-8"))
    assert withheld[0]["id"] == "nypd_complaint:327653221"
    assert withheld[0]["category"] == "SEX CRIMES"
    dumped = json.dumps(withheld)
    assert "lat_rounded" not in dumped
    assert "40.87" not in dumped
    html = (tmp_path / "map.html").read_text(encoding="utf-8")
    briefing = (tmp_path / "briefing.md").read_text(encoding="utf-8")
    ranking = (tmp_path / "ranking.json").read_text(encoding="utf-8")
    assert "327653221" not in html
    assert "327653221" not in briefing
    assert "327653221" not in ranking
    assert "SEX CRIMES" not in html
    assert "SEX CRIMES" not in briefing
    assert "nypd_complaint:327350219" in html
    assert "leaflet-control-attribution" in html
    assert "https://www.openstreetmap.org/copyright" in html
    assert "approval gate (simulated actor)" in briefing


def test_live_cost_uses_ticks_and_cli_refuses_without_a_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "segments": [
                                    {
                                        "headline": "Draft",
                                        "why_it_matters": "Draft only.",
                                        "source_incident_ids": ["syn:life-fire"],
                                    }
                                ]
                            }
                        )
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 8},
                "cost_in_usd_ticks": 40000,
            },
        }
        return httpx.Response(200, json=body)

    prompt = "hello " * 40
    from dataclasses import replace

    from events_briefing.config import Settings

    priced = replace(
        Settings.from_env(),
        live_llm=True,
        xai_api_key="k" * 12,
        llm_base_url="https://example.invalid/v1",
        llm_model="unit-model",
        llm_price_input_per_mtok=5.0,
        llm_price_output_per_mtok=5.0,
        max_live_spend_usd=1.0,
        llm_timeout_s=3,
    )
    provider = LiveProvider(priced, transport=httpx.MockTransport(handler), ledger=SpendLedger(1))
    result = provider.complete(prompt, BRIEFING_SCHEMA)
    estimate = (estimate_tokens(prompt) / 1_000_000) * 5 + (800 / 1_000_000) * 5
    assert calls["n"] == 1
    assert result.cost_basis == "usage"
    assert result.cost_usd == pytest.approx(40000 * USD_TICK)
    assert result.cost_usd < estimate / 2
    assert provider.ledger.spent_usd == pytest.approx(result.cost_usd)

    monkeypatch.setenv("LIVE_LLM", "0")
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    def boom(self: LiveProvider, prompt_text: str) -> tuple[str, None]:
        del self, prompt_text
        raise AssertionError("live post")

    monkeypatch.setattr(LiveProvider, "_post", boom)
    assert main(["briefing", "--live", "--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "LIVE_LLM=1" in err
    assert "XAI_API_KEY" in err
    assert "LLM_BASE_URL" in err
    assert "LLM_MODEL" in err
    assert "live_llm_called=false" in err

    monkeypatch.setenv("LIVE_LLM", "1")
    monkeypatch.setenv("XAI_API_KEY", "unit-fake-key")
    monkeypatch.setenv("LLM_PRICE_INPUT_PER_MTOK", "1.25")
    monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_MTOK", "2.5")
    monkeypatch.setenv("MAX_LIVE_SPEND_USD", "0.50")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert main(["briefing", "--live", "--out", str(tmp_path / "missing-url")]) == 2
    named = capsys.readouterr().err
    assert "briefing --live refused" in named
    assert "LLM_BASE_URL" in named
    assert "LLM_MODEL" in named
    assert "LIVE_LLM=1" not in named
    assert "live_llm_called=false" in named


def test_briefing_online_is_labeled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake(*_args: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["online"] is True
        assert kwargs["live"] is False
        return {
            "mode": "online (SODA refresh then rank)",
            "model_leg": "stub",
            "cost_usd": 0.0,
            "cost_basis": "none",
            "status": "PUBLISHED",
            "incident_count": 1,
            "withheld_sensitive": 0,
            "as_of": "2026-10-17",
            "rubric_version": "2026-10-17.1",
            "out_dir": str(tmp_path),
        }

    monkeypatch.setattr("events_briefing.cli.run_briefing", fake)
    assert main(["briefing", "--online", "--out", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "mode=online (SODA refresh then rank)" in printed
    assert "live model" not in printed


def test_socrata_budget_falls_back_with_a_fake_clock(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    clock = FakeClock()
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        clock.advance(15)
        raise httpx.ReadTimeout("timed out")

    snapshot = {
        "rows": [
            {
                "unique_key": "snap",
                "created_date": "2026-10-16T00:00:00.000",
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
    from dataclasses import replace

    from events_briefing.config import Settings

    settings = replace(
        Settings.from_env(),
        offline=False,
        live_llm=False,
        socrata_fetch_budget_s=20,
        socrata_timeout_s=15,
        socrata_max_attempts=3,
        socrata_backoff_base_s=0.25,
        socrata_backoff_cap_s=2,
    )
    client = SocrataClient(
        settings,
        transport=httpx.MockTransport(handler),
        snapshot_dir=tmp_path,
        clock=clock,
        sleep=clock.advance,
    )
    caplog.set_level(logging.WARNING, logger="events_briefing.socrata")
    rows = client.query(dataset_by_id("erm2-nwe9"), "x", "created_date DESC", 1)
    assert calls["n"] == 1
    assert rows[0]["unique_key"] == "snap"
    assert "socrata_budget_fallback" in caplog.text
    assert "budget" in caplog.text

    fresh = FakeClock()

    def slow_fresh(_request: httpx.Request) -> httpx.Response:
        fresh.advance(15)
        raise httpx.ReadTimeout("timed out")

    bare = SocrataClient(
        settings,
        transport=httpx.MockTransport(slow_fresh),
        snapshot_dir=tmp_path / "absent",
        clock=fresh,
        sleep=fresh.advance,
    )
    with pytest.raises(SocrataError):
        bare.query(dataset_by_id("erm2-nwe9"), "x", "created_date DESC", 1)


def test_online_briefing_refreshes_then_ranks_and_live_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "erm2-nwe9" in url:
            row = {
                "unique_key": "7",
                "created_date": "2026-10-16T01:00:00.000",
                "agency": "NYPD",
                "complaint_type": "Noise - Residential",
                "borough": "MANHATTAN",
                "community_board": "01 MANHATTAN",
                "latitude": "40.72",
                "longitude": "-74.00",
            }
        elif "5uac-w243" in url:
            row = {
                "cmplnt_num": "8",
                "cmplnt_fr_dt": "2026-06-30T00:00:00.000",
                "law_cat_cd": "FELONY",
                "ofns_desc": "ROBBERY",
                "boro_nm": "BRONX",
                "latitude": "40.84",
                "longitude": "-73.90",
            }
        else:
            row = {
                "starfire_incident_id": "F9",
                "incident_datetime": "2026-09-30T01:00:00.000",
                "incident_borough": "BROOKLYN",
                "communitydistrict": "306",
                "incident_classification": "Structural",
                "incident_classification_group": "Structural Fires",
                "highest_alarm_level": "All Hands Working",
            }
        return httpx.Response(200, json=[row])

    settings = replace(
        Settings.from_env(),
        offline=False,
        live_llm=False,
        approval_state_key="unit-rotated-gate-key",
    )
    client = SocrataClient(settings, transport=httpx.MockTransport(handler), sleep=lambda _s: None)
    summary = run_briefing(
        tmp_path / "online",
        settings,
        online=True,
        live=False,
        decision="reject",
        client=client,
        provider=StubProvider(),
    )
    assert summary["mode"] == "online (SODA refresh then rank)"
    assert summary["incident_count"] == 3
    assert summary["withheld_sensitive"] == 0

    with pytest.raises(RuntimeError, match="briefing --live refused"):
        run_briefing(tmp_path / "live-off", settings, live=True, online=False)

    class FakeLive:
        leg = "live"

        def __init__(self, _settings: object) -> None:
            self.leg = "live"

        def complete(self, prompt: str, schema: dict[str, object]) -> object:
            result = StubProvider().complete(prompt, schema)
            return result.model_copy(update={"model_leg": "live", "cost_basis": "usage"})

    live_settings = replace(
        settings,
        live_llm=True,
        offline=True,
        approval_state_key="unit-rotated-gate-key",
        xai_api_key="k" * 12,
        llm_base_url="https://example.invalid/v1",
        llm_model="unit-model",
        llm_price_input_per_mtok=1.0,
        llm_price_output_per_mtok=1.0,
        max_live_spend_usd=1.0,
    )
    monkeypatch.setattr("events_briefing.pipeline.LiveProvider", FakeLive)
    live_summary = run_briefing(
        tmp_path / "live",
        live_settings,
        live=True,
        online=False,
        decision="reject",
    )
    assert live_summary["mode"] == "snapshots + live model"
    assert live_summary["model_leg"] == "live"
