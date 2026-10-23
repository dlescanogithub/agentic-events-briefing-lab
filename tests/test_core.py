from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from events_briefing.config import Settings
from events_briefing.geohash import encode
from events_briefing.logging_setup import JsonFormatter, configure_logging
from events_briefing.models import CategoryGroup, Incident, LocationPrecision
from events_briefing.normalize import (
    NormalizeError,
    dedupe,
    incident_from_311,
    incident_from_fdny,
    incident_from_nypd,
    parse_socrata_time,
)
from events_briefing.privacy import forbidden_keys, sensitive_strings
from events_briefing.ranking import life_safety_above_noise, rank_incidents
from events_briefing.retry import RetryError, backoff_seconds, run_with_retries
from events_briefing.rubric import RubricError, load_rubric

ROOT = Path(__file__).resolve().parents[1]


def rubric():
    return load_rubric(ROOT / "config" / "rubric.json")


def test_geohash_known_vector() -> None:
    assert encode(57.64911, 10.40744, precision=6) == "u4pruy"
    assert len(encode(40.71, -74.00)) == 6
    with pytest.raises(ValueError):
        encode(0, 0, precision=0)


def test_backoff_is_capped() -> None:
    assert backoff_seconds(1, 0.25, 2) == 0.25
    assert backoff_seconds(2, 0.25, 2) == 0.5
    assert backoff_seconds(8, 0.25, 2) == 2
    with pytest.raises(ValueError):
        backoff_seconds(0, 0.25, 2)


def test_retry_succeeds_then_stops(caplog: pytest.LogCaptureFixture) -> None:
    calls = {"n": 0}

    def operation() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("slow")
        return "ok"

    slept: list[float] = []
    with caplog.at_level(logging.INFO):
        result = run_with_retries(
            operation,
            max_attempts=3,
            base_s=0.5,
            cap_s=1,
            timeout_s=15,
            operation_name="unit",
            retry_on=(TimeoutError,),
            sleep=slept.append,
        )
    assert result == "ok"
    assert slept == [0.5]


def test_retry_exhausted() -> None:
    with pytest.raises(RetryError) as caught:
        run_with_retries(
            lambda: (_ for _ in ()).throw(TimeoutError("nope")),
            max_attempts=2,
            base_s=0,
            cap_s=0,
            timeout_s=3,
            operation_name="unit",
            retry_on=(TimeoutError,),
            sleep=lambda _seconds: None,
        )
    assert caught.value.attempts == 2
    assert caught.value.timeout_s == 3
    with pytest.raises(ValueError):
        run_with_retries(
            lambda: "x", max_attempts=0, base_s=0, cap_s=0, timeout_s=None, operation_name="bad"
        )


def test_logging_redacts_and_includes_exception() -> None:
    configure_logging(["supersecretvalue"])
    formatter = JsonFormatter()
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "saw supersecretvalue", (), None)
    line = formatter.format(record)
    assert "supersecretvalue" not in line
    assert "[REDACTED]" in line
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord(
            "t", logging.ERROR, __file__, 1, "failed", (), __import__("sys").exc_info()
        )
    payload = json.loads(formatter.format(record))
    assert "boom" in payload["exc"]


def test_settings_defaults_are_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "EVENTS_OFFLINE",
        "LIVE_LLM",
        "SOCRATA_APP_TOKEN",
        "XAI_API_KEY",
        "LLM_PRICE_INPUT_PER_MTOK",
        "MAX_LIVE_SPEND_USD",
        "SOCRATA_MAX_ATTEMPTS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EVENTS_OFFLINE", "0")
    monkeypatch.setenv("LIVE_LLM", "yes")
    monkeypatch.setenv("SOCRATA_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("MAX_LIVE_SPEND_USD", "1.25")
    monkeypatch.setenv("LLM_PRICE_INPUT_PER_MTOK", "2")
    settings = Settings.from_env()
    assert settings.offline is False
    assert settings.live_llm is True
    assert settings.socrata_max_attempts == 4
    assert settings.max_live_spend_usd == 1.25
    assert settings.llm_price_input_per_mtok == 2
    forced = settings.forced_offline()
    assert forced.offline is True
    assert forced.live_llm is False


def test_rubric_rejects_bad_weights(tmp_path: Path) -> None:
    payload = json.loads((ROOT / "config" / "rubric.json").read_text(encoding="utf-8"))
    payload["weights"]["severity"] = 0.9
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RubricError):
        load_rubric(path)
    with pytest.raises(RubricError):
        load_rubric(tmp_path / "missing.json")


def test_normalize_drops_address_and_rounds() -> None:
    row = {
        "unique_key": "99",
        "created_date": "2026-10-16T01:51:34.000",
        "agency": "NYPD",
        "complaint_type": "Noise - Residential",
        "borough": "Unspecified",
        "community_board": "0 Unspecified",
        "latitude": "40.729714955424235",
        "longitude": "-73.98032524762165",
        "incident_address": "123 SECRET ST",
        "descriptor": "caller Jane 212-555-1212 said hello@example.com",
    }
    incident = incident_from_311(row, rubric(), "erm2-nwe9")
    dumped = incident.model_dump_json()
    assert "123 SECRET ST" not in dumped
    assert "40.729714955424235" not in dumped
    assert incident.lat_rounded == 40.73
    assert incident.lon_rounded == -73.98
    assert incident.borough is None
    assert incident.community_area is None
    assert incident.category_group is CategoryGroup.NOISE
    assert incident.location_precision is LocationPrecision.ROUNDED_2DP
    assert forbidden_keys(incident.model_dump()) == []


def test_normalize_classifiers_and_dedupe() -> None:
    rules = rubric()
    hazmat = incident_from_311(
        {
            "unique_key": "1",
            "created_date": "2026-10-15T12:00:00.000Z",
            "complaint_type": "Hazardous Materials",
            "borough": "QUEENS",
            "community_board": "07 QUEENS",
            "latitude": 40.731,
            "longitude": -73.794,
        },
        rules,
        "erm2-nwe9",
    )
    assert hazmat.category_group is CategoryGroup.LIFE_SAFETY
    assert hazmat.community_area == "07 QUEENS"
    signal = incident_from_311(
        {
            "unique_key": "2",
            "created_date": "2026-10-15T12:00:00.000",
            "complaint_type": "Traffic Signal Condition",
            "borough": "BRONX",
            "latitude": 40.864,
            "longitude": -73.814,
        },
        rules,
        "erm2-nwe9",
    )
    assert signal.severity_hint == 0.55
    other = incident_from_311(
        {
            "unique_key": "3",
            "created_date": "2026-10-15T12:00:00.000",
            "complaint_type": "Mystery",
            "borough": "MANHATTAN",
            "lat_rounded": 40.78,
            "lon_rounded": -73.97,
        },
        rules,
        "erm2-nwe9",
    )
    assert other.category_group is CategoryGroup.OTHER
    assault = incident_from_nypd(
        {
            "cmplnt_num": "10",
            "cmplnt_fr_dt": "2026-06-30T00:00:00.000",
            "law_cat_cd": "FELONY",
            "ofns_desc": "FELONY ASSAULT",
            "boro_nm": "BRONX",
            "latitude": "40.840373",
            "longitude": "-73.844986",
            "susp_sex": "M",
            "prem_typ_desc": "RESIDENCE",
        },
        rules,
        "5uac-w243",
    )
    assert assault.category_group is CategoryGroup.LIFE_SAFETY
    assert assault.severity_hint == 0.9
    assert "RESIDENCE" not in assault.model_dump_json()
    drugs = incident_from_nypd(
        {
            "cmplnt_num": "11",
            "cmplnt_fr_dt": "2026-06-30T00:00:00.000",
            "law_cat_cd": "MISDEMEANOR",
            "ofns_desc": "DANGEROUS DRUGS",
            "boro_nm": "BROOKLYN",
            "latitude": 40.65,
            "longitude": -73.95,
        },
        rules,
        "5uac-w243",
    )
    assert drugs.category_group is CategoryGroup.OTHER
    harass = incident_from_nypd(
        {
            "cmplnt_num": "12",
            "cmplnt_fr_dt": "2026-06-30T00:00:00.000",
            "law_cat_cd": "VIOLATION",
            "ofns_desc": "HARRASSMENT 2",
            "boro_nm": "STATEN ISLAND",
            "latitude": 40.58,
            "longitude": -74.15,
        },
        rules,
        "5uac-w243",
    )
    assert harass.category_group is CategoryGroup.QUALITY_OF_LIFE
    fire = incident_from_fdny(
        {
            "starfire_incident_id": "F1",
            "incident_datetime": "2026-09-30T23:51:59.000",
            "incident_borough": "RICHMOND / STATEN ISLAND",
            "communitydistrict": "503",
            "incident_classification": "Structural",
            "incident_classification_group": "Structural Fires",
            "highest_alarm_level": "All Hands Working",
            "alarm_box_location": "123 MAIN ST",
        },
        rules,
        "8m42-w767",
    )
    assert fire.borough == "Staten Island"
    assert fire.location_precision is LocationPrecision.BOROUGH_CENTROID
    assert fire.category_group is CategoryGroup.LIFE_SAFETY
    assert "123 MAIN ST" not in fire.model_dump_json()
    assert fire.severity_hint >= 0.7
    kept, dropped = dedupe([assault, assault])
    assert dropped == 1
    assert len(kept) == 1
    with pytest.raises(NormalizeError):
        incident_from_311({"complaint_type": "Noise - Residential"}, rules, "erm2-nwe9")
    aware = parse_socrata_time("2026-10-16T01:51:34.000Z")
    assert aware.tzinfo is not None


def test_ranking_floor_and_density_ignore_centroids() -> None:
    rules = rubric()
    base = {
        "source_dataset_id": "synthetic",
        "community_area": None,
        "borough": "Manhattan",
    }
    from datetime import datetime, timezone

    def make(**kwargs: object) -> Incident:
        payload = {
            "id": "x",
            "source": "nyc_311",
            "category": "Noise - Residential",
            "category_group": CategoryGroup.NOISE,
            "severity_hint": 0.15,
            "created_at": datetime(2026, 10, 16, tzinfo=timezone.utc),
            "geohash6": "dr5reg",
            "lat_rounded": 40.71,
            "lon_rounded": -74.00,
            "location_precision": LocationPrecision.ROUNDED_2DP,
            **base,
        }
        payload.update(kwargs)
        return Incident.model_validate(payload)

    noise_a = make(id="n-a")
    noise_b = make(id="n-b")
    centroid = make(
        id="c",
        source="fdny_fire",
        category="Structural Fires",
        category_group=CategoryGroup.LIFE_SAFETY,
        severity_hint=0.01,
        location_precision=LocationPrecision.BOROUGH_CENTROID,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    loud = make(
        id="loud", severity_hint=0.99, lat_rounded=40.86, lon_rounded=-73.86, geohash6="dr5ryy"
    )
    ranked = rank_incidents([noise_a, noise_b, centroid, loud], rules)
    assert life_safety_above_noise(ranked) is True
    by_id = {item.incident.id: item for item in ranked}
    assert by_id["c"].score >= 4
    assert by_id["loud"].score < 1
    assert by_id["n-a"].score == by_id["n-b"].score
    assert by_id["n-a"].rank < by_id["n-b"].rank
    assert by_id["n-a"].parts.density == by_id["n-b"].parts.density
    assert by_id["c"].parts.density == 0
    assert rank_incidents([], rules) == []
    assert life_safety_above_noise(rank_incidents([noise_a], rules)) is None


def test_sensitive_string_scan() -> None:
    assert sensitive_strings({"note": "call 212-555-0100 or a@b.co"})
    assert sensitive_strings({"note": "coarse"}) == []
    assert forbidden_keys({"rows": [{"incident_address": "x"}]})
