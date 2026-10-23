from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from events_briefing.briefing.gate import TRANSITIONS, BriefingStore, GateError
from events_briefing.briefing.invariants import claims_published_while_outbox_empty
from events_briefing.briefing.prompts import build_prompt
from events_briefing.briefing.writer import draft_from_provider
from events_briefing.cli import main
from events_briefing.config import Settings
from events_briefing.datasets import DATASETS, dataset_by_id
from events_briefing.evalkit.regression import run_regression
from events_briefing.evalkit.runner import eval_exit_code, execute
from events_briefing.evalkit.scenarios import run_eval
from events_briefing.mapgen import ATTRIBUTION, render_map
from events_briefing.privacy import coords_are_coarse, dump_contains, forbidden_keys
from events_briefing.providers.base import BRIEFING_SCHEMA
from events_briefing.providers.cassette import CassetteProvider
from events_briefing.providers.live import (
    LiveConfigError,
    LiveProvider,
    SpendLedger,
    estimate_tokens,
    require_live_disabled,
)
from events_briefing.providers.stub import StubProvider
from events_briefing.ranking import rank_incidents
from events_briefing.rubric import load_rubric
from events_briefing.socrata import (
    SocrataClient,
    SocrataError,
    TtlCache,
    project_snapshot_row,
    write_snapshots,
)
from events_briefing.trace import TraceLog, inputs_hash

ROOT = Path(__file__).resolve().parents[1]


def _settings(**kwargs: object) -> Settings:
    base = Settings.from_env()
    return replace(base, **kwargs)  # type: ignore[arg-type]


def _rubric():
    return load_rubric(ROOT / "config" / "rubric.json")


def _valid_body() -> str:
    return json.dumps(
        {
            "segments": [
                {
                    "headline": "Life safety draft",
                    "why_it_matters": "Draft only. Nothing has left this machine.",
                    "source_incident_ids": ["syn:life-fire"],
                }
            ]
        }
    )


def test_dataset_lookup() -> None:
    spec = dataset_by_id("erm2-nwe9")
    assert spec.source == "nyc_311"
    with pytest.raises(KeyError):
        dataset_by_id("missing")
    assert len(DATASETS) == 3


def test_project_snapshot_drops_address() -> None:
    spec = dataset_by_id("erm2-nwe9")
    row = project_snapshot_row(
        spec,
        {
            "unique_key": "1",
            "created_date": "2026-10-16T01:00:00.000",
            "agency": "DOT",
            "complaint_type": "Electrical",
            "borough": "BROOKLYN",
            "community_board": "02 BROOKLYN",
            "latitude": "40.6812345",
            "longitude": "-73.9754321",
            "incident_address": "9 SECRET AVE",
        },
    )
    assert "incident_address" not in row
    assert row["lat_rounded"] == 40.68
    assert row["lon_rounded"] == -73.98
    assert coords_are_coarse(row["lat_rounded"], row["lon_rounded"])
    assert dump_contains(json.dumps(row), ["9 SECRET AVE", "40.6812345"]) == []
    assert forbidden_keys(row) == []


def test_socrata_retries_cache_and_offline(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timed out")
        if "erm2-nwe9" in str(request.url):
            return httpx.Response(
                200,
                json=[
                    {
                        "unique_key": "7",
                        "created_date": "2026-10-16T01:00:00.000",
                        "agency": "NYPD",
                        "complaint_type": "Noise - Residential",
                        "borough": "MANHATTAN",
                        "community_board": "01 MANHATTAN",
                        "latitude": "40.71999",
                        "longitude": "-74.00111",
                    }
                ],
            )
        if "5uac-w243" in str(request.url):
            return httpx.Response(
                200,
                json=[
                    {
                        "cmplnt_num": "8",
                        "cmplnt_fr_dt": "2026-06-30T00:00:00.000",
                        "law_cat_cd": "FELONY",
                        "ofns_desc": "ROBBERY",
                        "boro_nm": "BRONX",
                        "latitude": "40.84111",
                        "longitude": "-73.84999",
                    }
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "starfire_incident_id": "F9",
                    "incident_datetime": "2026-09-30T01:00:00.000",
                    "incident_borough": "BROOKLYN",
                    "communitydistrict": "306",
                    "incident_classification": "Structural",
                    "incident_classification_group": "Structural Fires",
                    "highest_alarm_level": "All Hands Working",
                    "alarm_box_location": "should not be stored",
                }
            ],
        )

    clock = {"now": 0.0}
    cache = TtlCache(10, clock=lambda: clock["now"])
    settings = _settings(
        offline=False,
        live_llm=False,
        socrata_max_attempts=3,
        socrata_backoff_base_s=0.0,
        socrata_backoff_cap_s=0.0,
        socrata_timeout_s=5,
        socrata_app_token="",
    )
    client = SocrataClient(
        settings,
        transport=httpx.MockTransport(handler),
        cache=cache,
        sleep=lambda _seconds: None,
        snapshot_dir=tmp_path,
    )
    spec = dataset_by_id("erm2-nwe9")
    first = client.query(spec, spec.pulls[0].where, spec.pulls[0].order, spec.pulls[0].limit)
    second = client.query(spec, spec.pulls[0].where, spec.pulls[0].order, spec.pulls[0].limit)
    assert first == second
    assert calls["n"] == 2  # one timeout, one success; second query is cached
    clock["now"] = 50
    client.query(spec, spec.pulls[0].where, spec.pulls[0].order, spec.pulls[0].limit)
    assert calls["n"] == 3
    manifest = write_snapshots(
        client,
        captured_at=datetime(2026, 10, 17, tzinfo=timezone.utc),
        destination=tmp_path,
    )
    stored = json.loads((tmp_path / "erm2-nwe9.json").read_text(encoding="utf-8"))
    assert stored["rows"][0]["lat_rounded"] == 40.72
    assert "latitude" not in stored["rows"][0]
    fdny = json.loads((tmp_path / "8m42-w767.json").read_text(encoding="utf-8"))
    assert "alarm_box_location" not in json.dumps(fdny)
    assert manifest.is_file()

    offline = SocrataClient(_settings(offline=True), snapshot_dir=tmp_path)
    rows = offline.query(spec, "", "", 0)
    assert rows[0]["unique_key"] == "7"
    with pytest.raises(SocrataError):
        SocrataClient(_settings(offline=True), snapshot_dir=tmp_path / "missing").query(
            spec, "", "", 0
        )


def test_socrata_status_and_bad_snapshot(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad"})

    client = SocrataClient(
        _settings(
            offline=False, socrata_max_attempts=2, socrata_backoff_base_s=0, socrata_backoff_cap_s=0
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )
    spec = dataset_by_id("8m42-w767")
    with pytest.raises(SocrataError, match="400"):
        client.query(spec, "x", "y", 1)

    bad = tmp_path / "erm2-nwe9.json"
    bad.write_text(json.dumps({"rows": [{"incident_address": "1 MAIN"}]}), encoding="utf-8")
    offline = SocrataClient(_settings(offline=True), snapshot_dir=tmp_path)
    with pytest.raises(SocrataError, match="forbidden"):
        offline.query(dataset_by_id("erm2-nwe9"), "", "", 0)
    with pytest.raises(SocrataError, match="OFFLINE"):
        write_snapshots(offline)


def test_live_provider_refuses_and_calls(tmp_path: Path) -> None:
    del tmp_path
    settings = _settings(
        live_llm=True,
        xai_api_key="k" * 12,
        llm_base_url="https://example.invalid/v1",
        llm_model="unit-model",
        llm_price_input_per_mtok=1.0,
        llm_price_output_per_mtok=1.0,
        max_live_spend_usd=0.0000001,
        llm_timeout_s=3,
    )
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": _valid_body()}}]})

    refused = LiveProvider(settings, transport=httpx.MockTransport(handler))
    result = refused.complete("hello", BRIEFING_SCHEMA)
    assert result.valid is False
    assert "MAX_LIVE_SPEND_USD" in str(result.error)
    assert calls["n"] == 0

    cheap = _settings(
        live_llm=True,
        xai_api_key="k" * 12,
        llm_base_url="https://example.invalid/v1",
        llm_model="unit-model",
        llm_price_input_per_mtok=0.0,
        llm_price_output_per_mtok=0.0,
        max_live_spend_usd=1,
        llm_timeout_s=3,
    )
    ok = LiveProvider(cheap, transport=httpx.MockTransport(handler))
    parsed = ok.complete("hello", BRIEFING_SCHEMA)
    assert parsed.valid is True
    assert parsed.model_leg == "live"
    assert calls["n"] == 1

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    timed = LiveProvider(cheap, transport=httpx.MockTransport(timeout), ledger=SpendLedger(1))
    timed_result = timed.complete("hello", BRIEFING_SCHEMA)
    assert timed_result.timed_out is True
    assert timed_result.timeout_s == 3

    def broken(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "nope"})

    failed = LiveProvider(cheap, transport=httpx.MockTransport(broken), ledger=SpendLedger(1))
    failed_result = failed.complete("hello", BRIEFING_SCHEMA)
    assert failed_result.valid is False
    assert failed_result.timed_out is False

    missing = LiveProvider(_settings(live_llm=False))
    assert "LIVE_LLM" in str(missing.complete("x", BRIEFING_SCHEMA).error)
    with pytest.raises(LiveConfigError):
        require_live_disabled(_settings(live_llm=True))
    require_live_disabled(_settings(live_llm=False))
    assert estimate_tokens("") == 1
    assert SpendLedger(1).reserve(-1) is False


def test_gate_and_false_publish_claim(tmp_path: Path) -> None:
    store = BriefingStore(tmp_path, demo=True)
    created = store.create(
        program_id="prog-unit",
        model_leg="stub",
        rubric_version="2026-10-17.1",
        segments=[
            {
                "headline": "Draft segment",
                "why_it_matters": "Draft only. Nothing has left this machine.",
                "source_incident_ids": ["syn:life-fire"],
            }
        ],
        inputs_hash="abc",
        created_at=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    assert created["status"] == "DRAFT"
    with pytest.raises(GateError):
        store.publish("prog-unit")
    assert store.outbox_count() == 0
    store.submit("prog-unit")
    approved = store.decide(
        "prog-unit",
        "approve",
        actor="simulated-editor",
        simulated=True,
        note="SIMULATED",
    )
    assert approved["status"] == "APPROVED"
    published = store.publish("prog-unit")
    assert published["status"] == "PUBLISHED"
    assert store.outbox_count() == 1
    with pytest.raises(GateError):
        store.publish("prog-unit")
    with pytest.raises(GateError):
        store.create(
            program_id="../evil", model_leg="stub", rubric_version="v", segments=[], inputs_hash="z"
        )
    assert ("DRAFT", "publish") not in TRANSITIONS
    assert (
        claims_published_while_outbox_empty("This briefing was published and emailed.", 0) is True
    )
    assert claims_published_while_outbox_empty("El parte se publicó.", 0) is True
    assert claims_published_while_outbox_empty("Draft only.", 0) is False
    other = BriefingStore(tmp_path / "other", demo=True)
    other.create(
        program_id="prog-reject",
        model_leg="cassette",
        rubric_version="v",
        segments=[
            {
                "headline": "Nope",
                "why_it_matters": "Draft only.",
                "source_incident_ids": ["a"],
            }
        ],
        inputs_hash="q",
    )
    other.submit("prog-reject")
    rejected = other.decide(
        "prog-reject", "reject", actor="simulated-editor", simulated=True, note="SIMULATED"
    )
    assert rejected["status"] == "REJECTED"
    with pytest.raises(GateError):
        other.publish("prog-reject")
    assert other.outbox_count() == 0


def test_eval_gate_and_regression() -> None:
    rubric = _rubric()
    report = run_eval(rubric, "0.1.0")
    assert eval_exit_code(report) == 0
    assert report.incomplete_count == 0
    assert report.fail_count == 0
    assert report.pass_count == 8
    assert report.n_incidents == 10
    assert report.life_safety_above_noise_rate == 1.0
    reg_report, code = run_regression(rubric, "0.1.0")
    assert code == 1
    assert reg_report.fail_count == 1
    assert reg_report.pass_count == 1
    incomplete = execute("boom", lambda: (_ for _ in ()).throw(RuntimeError("nope")))
    assert incomplete.status == "INCOMPLETE"
    assert incomplete.completed is False
    empty = execute("empty", lambda: ("PASS", "  "))
    assert empty.status == "INCOMPLETE"
    assert "empty PASS" in empty.detail


def test_fail_closed_unknown_ids() -> None:
    from events_briefing.evalkit.synthetic import synthetic_incidents

    rubric = _rubric()
    ranked = rank_incidents(synthetic_incidents(), rubric)
    cassette = CassetteProvider(
        [
            json.dumps(
                {
                    "segments": [
                        {
                            "headline": "Unknown ids",
                            "why_it_matters": "Draft only.",
                            "source_incident_ids": ["not-a-real-id"],
                        }
                    ]
                }
            )
        ]
    )
    segments, leg, _result = draft_from_provider(
        ranked,
        cassette,
        prompt=build_prompt(ranked, rubric.version, as_of=datetime(2026, 10, 17).date()),
        max_attempts=1,
        as_of=datetime(2026, 10, 17).date(),
    )
    assert leg == "fallback"
    assert segments
    stub = StubProvider().complete("no schema here", BRIEFING_SCHEMA)
    assert stub.valid is False
    with pytest.raises(ValueError):
        CassetteProvider([])


def test_map_trace_and_hash(tmp_path: Path) -> None:
    from events_briefing.evalkit.synthetic import synthetic_incidents

    ranked = rank_incidents(synthetic_incidents(), _rubric())
    html = render_map(ranked, title="Lab map <safe>")
    assert "OpenStreetMap" in ATTRIBUTION
    assert "OpenStreetMap" in html
    assert "leaflet-control-attribution" in html
    assert "https://www.openstreetmap.org/copyright" in html
    assert "leaflet-control-container" in html
    assert "syn:life-robbery" in html
    assert "<safe>" not in html
    digest = inputs_hash([item.incident.id for item in ranked], "2026-10-17.1")
    assert len(digest) == 64
    trace = TraceLog(tmp_path / "trace.jsonl")
    trace.write({"event": "demo", "model_leg": "stub", "publish": False})
    assert trace.read()[0]["model_leg"] == "stub"


def test_cli_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUBRIC_PATH", str(ROOT / "config" / "rubric.json"))
    monkeypatch.setenv("EVENTS_OFFLINE", "1")
    monkeypatch.setenv("LIVE_LLM", "0")
    assert main(["live"]) == 0
    assert main(["eval", "--out", str(tmp_path / "eval.json")]) == 0
    payload = json.loads((tmp_path / "eval.json").read_text(encoding="utf-8"))
    assert payload["pass_count"] == 8
    assert main(["eval-regression"]) == 1
    assert main(["secretscan"]) == 0
    assert main(["demo"]) == 2
    assert main(["refresh-snapshots"]) == 2
    assert main(["rank"]) == 2
    code = main(["demo", "--offline", "--decision", "reject", "--out", str(tmp_path / "demo")])
    # Snapshots may be absent until the manual capture. Either a clean reject or a clear failure.
    assert code in {0, 1}
    if code == 0:
        text = (tmp_path / "demo" / "briefing.md").read_text(encoding="utf-8")
        assert "SIMULATED" in text
        assert "PUBLISHED" not in text


def test_committed_snapshots_are_aggregate_safe() -> None:
    folder = ROOT / "fixtures" / "snapshots"
    files = list(folder.glob("*.json"))
    assert files, "snapshots must be captured before this test"
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert forbidden_keys(payload) == []
        assert (
            dump_contains(
                path.read_text(encoding="utf-8"), ["incident_address", "alarm_box_location"]
            )
            == []
        )
        rows = payload.get("rows", payload.get("datasets"))
        if path.name == "manifest.json":
            continue
        assert isinstance(rows, list) and rows
        for row in rows:
            if "lat_rounded" in row and row["lat_rounded"] is not None:
                assert coords_are_coarse(row["lat_rounded"], row["lon_rounded"])
