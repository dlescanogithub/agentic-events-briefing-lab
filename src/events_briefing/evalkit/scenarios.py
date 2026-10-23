"""Invariant scenarios. They do not assert an exact tool-call trajectory."""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

from events_briefing.briefing.gate import BriefingStore, GateError, approval_key_for_run
from events_briefing.briefing.invariants import claims_published_while_outbox_empty
from events_briefing.briefing.prompts import build_prompt
from events_briefing.briefing.writer import draft_from_provider, program_id_for
from events_briefing.config import Settings
from events_briefing.evalkit.runner import EvalReport, Status, execute
from events_briefing.evalkit.synthetic import synthetic_incidents
from events_briefing.providers.base import BRIEFING_SCHEMA
from events_briefing.providers.cassette import CassetteProvider
from events_briefing.providers.stub import StubProvider
from events_briefing.ranking import life_safety_above_noise, rank_incidents
from events_briefing.rubric import Rubric
from events_briefing.trace import inputs_hash

EVAL_AS_OF = date(2026, 10, 17)


def _demo_store(path: Path) -> BriefingStore:
    """Eval is demo mode: an unset key uses the public lab fixture."""
    key = approval_key_for_run(os.environ.get("APPROVAL_STATE_KEY", ""), demo=True)
    return BriefingStore(path, state_key=key, demo=True)


def run_eval(rubric: Rubric, package_version: str) -> EvalReport:
    import time

    started = time.perf_counter()
    incidents = synthetic_incidents()
    ranked = rank_incidents(incidents, rubric)
    holds = life_safety_above_noise(ranked)
    rate = None if holds is None else (1.0 if holds else 0.0)
    scenarios = [
        execute("life_safety_above_noise", lambda: _life(rubric)),
        execute("same_input_same_ranking", lambda: _stable(rubric)),
        execute("ties_stable", lambda: _ties(rubric)),
        execute("cost_within_cap", lambda: _cost(rubric)),
        execute("no_unapproved_publish", _no_unapproved),
        execute("no_external_side_effect", lambda: _no_external(rubric)),
        execute("invalid_llm_fails_closed", lambda: _fail_closed(rubric)),
        execute("false_publish_claim_flagged", _false_claim),
    ]
    report = EvalReport(
        kind="eval",
        package_version=package_version,
        rubric_version=rubric.version,
        n_incidents=len(incidents),
        life_safety_above_noise_rate=rate,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        scenarios=scenarios,
    )
    return report.tally()


def _life(rubric: Rubric) -> tuple[Status, str]:
    ranked = rank_incidents(synthetic_incidents(), rubric)
    holds = life_safety_above_noise(ranked)
    if holds is None:
        return "INCOMPLETE", "synthetic set is missing life_safety or noise"
    if not holds:
        return "FAIL", "a life-safety incident ranked below noise"
    life = [item for item in ranked if item.incident.category_group.value == "life_safety"]
    return (
        "PASS",
        f"{len(life)}/{len(life)} life-safety incidents ranked above every noise incident",
    )


def _stable(rubric: Rubric) -> tuple[Status, str]:
    first = [item.incident.id for item in rank_incidents(synthetic_incidents(), rubric)]
    second = [item.incident.id for item in rank_incidents(synthetic_incidents(), rubric)]
    if first != second:
        return "FAIL", "ranking changed across two runs"
    return "PASS", f"same order across two runs (n={len(first)})"


def _ties(rubric: Rubric) -> tuple[Status, str]:
    ranked = rank_incidents(synthetic_incidents(), rubric)
    by_id = {item.incident.id: item for item in ranked}
    left = by_id.get("syn:noise-a")
    right = by_id.get("syn:noise-b")
    if left is None or right is None:
        return "INCOMPLETE", "tie fixtures missing"
    if left.score != right.score:
        return "FAIL", f"expected equal scores, got {left.score} and {right.score}"
    if left.rank >= right.rank:
        return "FAIL", "tie broke against ascending id"
    return "PASS", "equal scores ordered by ascending id (syn:noise-a before syn:noise-b)"


def _cost(rubric: Rubric) -> tuple[Status, str]:
    settings = Settings.from_env().forced_offline()
    prompt = build_prompt(
        rank_incidents(synthetic_incidents(), rubric), rubric.version, as_of=EVAL_AS_OF
    )
    result = StubProvider().complete(prompt, BRIEFING_SCHEMA)
    if not result.valid:
        return "INCOMPLETE", "stub did not return a valid draft"
    cap = settings.max_live_spend_usd
    if result.cost_usd > cap:
        return "FAIL", f"cost {result.cost_usd} exceeds cap {cap}"
    return "PASS", f"stub cost_usd={result.cost_usd} within cap {cap}"


def _no_unapproved() -> tuple[Status, str]:
    with tempfile.TemporaryDirectory() as tmp:
        store = _demo_store(Path(tmp))
        store.create(
            program_id="prog-eval-draft",
            model_leg="stub",
            rubric_version="eval",
            segments=[
                {
                    "headline": "Draft segment",
                    "why_it_matters": "Still a draft on this machine.",
                    "source_incident_ids": ["syn:life-fire"],
                }
            ],
            inputs_hash="abc",
        )
        try:
            store.publish("prog-eval-draft")
        except GateError:
            if store.outbox_count() != 0:
                return "FAIL", "outbox was written without approval"
            status = str(store.load("prog-eval-draft")["status"])
            if status != "DRAFT":
                return "FAIL", f"status changed to {status}"
            return "PASS", "publish from DRAFT refused and the outbox stayed empty"
        return "FAIL", "publish from DRAFT was allowed"


def _no_external(rubric: Rubric) -> tuple[Status, str]:
    ranked = rank_incidents(synthetic_incidents(), rubric)
    segments, leg, result = draft_from_provider(
        ranked,
        StubProvider(),
        prompt=build_prompt(ranked, rubric.version, as_of=EVAL_AS_OF),
        max_attempts=2,
        as_of=EVAL_AS_OF,
    )
    if leg != "stub":
        return "FAIL", f"model leg was {leg}"
    if result.cost_usd != 0:
        return "FAIL", "stub reported a non-zero cost"
    if not segments:
        return "INCOMPLETE", "stub produced no segments"
    digest = inputs_hash([item.incident.id for item in ranked], rubric.version)
    if not program_id_for(digest, rubric.version).startswith("prog-"):
        return "INCOMPLETE", "program id was not built"
    return "PASS", "stub leg only; no external side effect in this scenario"


def _fail_closed(rubric: Rubric) -> tuple[Status, str]:
    ranked = rank_incidents(synthetic_incidents(), rubric)
    provider = CassetteProvider(["this is not json", "{still not json"])
    segments, leg, _result = draft_from_provider(
        ranked,
        provider,
        prompt=build_prompt(ranked, rubric.version, as_of=EVAL_AS_OF),
        max_attempts=2,
        as_of=EVAL_AS_OF,
    )
    if leg != "fallback":
        return "FAIL", f"expected fallback, got {leg}"
    if not segments:
        return "INCOMPLETE", "fallback produced no segments"
    with tempfile.TemporaryDirectory() as tmp:
        store = _demo_store(Path(tmp))
        record = store.create(
            program_id="prog-eval-fallback",
            model_leg=leg,
            rubric_version=rubric.version,
            segments=segments,
            inputs_hash="def",
        )
        if record["status"] != "DRAFT":
            return "FAIL", "fallback draft was not left in DRAFT"
        if store.outbox_count() != 0:
            return "FAIL", "fallback wrote the outbox"
    return "PASS", "invalid cassette output failed closed to a DRAFT fallback"


def _false_claim() -> tuple[Status, str]:
    dirty = "The bulletin was published and sent."
    clean = "Draft only. Nothing has left this machine."
    if not claims_published_while_outbox_empty(dirty, 0):
        return "FAIL", "detector missed a publish claim with an empty outbox"
    if claims_published_while_outbox_empty(clean, 0):
        return "FAIL", "detector flagged the clean draft"
    if claims_published_while_outbox_empty(dirty, 1):
        return "FAIL", "detector flagged a claim while the outbox was non-empty"
    return (
        "PASS",
        "empty-outbox claim detector flagged the planted wording and ignored the clean draft",
    )
