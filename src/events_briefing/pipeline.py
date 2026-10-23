"""Briefing pipeline. Snapshots are the default. Online and live are explicit."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from events_briefing.briefing.gate import BriefingStore, approval_key_for_run, load_approvers
from events_briefing.briefing.prompts import build_prompt
from events_briefing.briefing.writer import draft_from_provider, program_id_for, render_markdown
from events_briefing.config import Settings
from events_briefing.datasets import DATASETS
from events_briefing.mapgen import render_map
from events_briefing.models import Incident, RankedIncident
from events_briefing.normalize import dedupe, local_calendar_date, normalize_rows
from events_briefing.providers.base import Provider
from events_briefing.providers.live import (
    LiveProvider,
    live_requirement_errors,
    require_live_disabled,
)
from events_briefing.providers.stub import StubProvider
from events_briefing.ranking import rank_incidents
from events_briefing.rubric import Rubric, load_rubric
from events_briefing.sensitive import load_sensitive_terms, split_public
from events_briefing.socrata import SocrataClient
from events_briefing.trace import TraceLog, inputs_hash


def load_snapshot_incidents(settings: Settings) -> tuple[list[Incident], Rubric]:
    rubric = load_rubric(settings.rubric_path)
    client = SocrataClient(settings.forced_offline())
    return _from_client(client, rubric, online=False), rubric


def load_online_incidents(
    settings: Settings, client: SocrataClient | None = None
) -> tuple[list[Incident], Rubric, SocrataClient]:
    """SODA refresh for this run, then normalize. Does not overwrite snapshot files."""
    rubric = load_rubric(settings.rubric_path)
    online = replace(settings, offline=False)
    soda = client or SocrataClient(online)
    return _from_client(soda, rubric, online=True), rubric, soda


def _from_client(client: SocrataClient, rubric: Rubric, *, online: bool) -> list[Incident]:
    collected: list[Incident] = []
    for spec in DATASETS:
        if not online:
            rows = client.query(spec, pull_where="", pull_order="", pull_limit=0)
        else:
            merged: dict[str, dict[str, Any]] = {}
            for pull in spec.pulls:
                for row in client.query(spec, pull.where, pull.order, pull.limit):
                    row_id = str(row.get(spec.id_field) or "")
                    if row_id and row_id not in merged:
                        merged[row_id] = row
            rows = list(merged.values())
        built, _dropped = normalize_rows(spec.source, rows, rubric, spec.dataset_id)
        collected.extend(built)
    unique, _dropped_again = dedupe(collected)
    return unique


def run_offline_demo(
    out_dir: Path,
    settings: Settings | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    decision: str = "approve",
) -> dict[str, object]:
    active = (settings or Settings.from_env()).forced_offline()
    return run_briefing(
        out_dir,
        active,
        live=False,
        online=False,
        decision=decision,
        clock=clock,
        demo=True,
    )


def run_briefing(
    out_dir: Path,
    settings: Settings | None = None,
    *,
    live: bool = False,
    online: bool = False,
    decision: str = "approve",
    clock: Callable[[], datetime] | None = None,
    provider: Provider | None = None,
    client: SocrataClient | None = None,
    demo: bool = False,
) -> dict[str, object]:
    """Rank and draft.

    Without ``online``, incidents come from snapshot files only.
    ``online`` refreshes SODA and then ranks. The mode label is the refresh that
    happened: full online, mixed when some pulls fell back to snapshots, or
    snapshots when every pull fell back. A partial fallback is not labeled online.
    ``live`` calls the model only after the live env switches are present.
    """
    active = settings or Settings.from_env()
    active = replace(active, offline=not online)
    if live:
        missing = live_requirement_errors(active)
        if missing and provider is None:
            raise RuntimeError("briefing --live refused: " + ", ".join(missing))
    else:
        active = replace(active, live_llm=False)
        require_live_disabled(active)
    active = replace(
        active, approval_state_key=approval_key_for_run(active.approval_state_key, demo=demo)
    )
    now = clock or (lambda: datetime.now(timezone.utc))
    fallback_pulls = 0
    live_pulls = 0
    if online:
        incidents, rubric, soda = load_online_incidents(active, client)
        mode = _refresh_mode(soda)
        fallback_pulls = soda.fallback_pulls
        live_pulls = soda.live_pulls
    else:
        incidents, rubric = load_snapshot_incidents(active)
        mode = "snapshots"
    if live:
        mode = f"{mode} + live model"
    terms = load_sensitive_terms(active.sensitive_path)
    public, withheld = split_public(incidents, terms)
    ranked = rank_incidents(public, rubric)
    created_at = now()
    as_of = local_calendar_date(created_at)
    if provider is None:
        provider = LiveProvider(active) if live else StubProvider()
    prompt = build_prompt(ranked, rubric.version, as_of=as_of)
    segments, model_leg, provider_result = draft_from_provider(
        ranked,
        provider,
        prompt=prompt,
        max_attempts=active.llm_max_attempts,
        as_of=as_of,
    )
    digest = inputs_hash([item.incident.id for item in ranked], rubric.version)
    program_id = program_id_for(digest, rubric.version)
    store = BriefingStore(
        out_dir,
        state_key=active.approval_state_key,
        approvers=load_approvers(active.approvers_path),
        demo=demo,
    )
    store.create(
        program_id=program_id,
        model_leg=model_leg,
        rubric_version=rubric.version,
        segments=segments,
        inputs_hash=digest,
        created_at=created_at,
    )
    store.submit(program_id)
    note = (
        "SIMULATED approval for the approval gate (simulated actor). "
        "Production needs an authenticated channel; this lab does not have one."
    )
    record = store.decide(
        program_id,
        decision,
        actor="simulated-editor",
        simulated=True,
        note=note,
    )
    published = False
    if decision == "approve":
        record = store.publish(program_id)
        published = True
    trace = TraceLog(out_dir / "trace.jsonl")
    trace.write(
        {
            "event": "briefing",
            "mode": mode,
            "inputs_hash": digest,
            "rubric_version": rubric.version,
            "model_leg": model_leg,
            "provider_reported_leg": provider_result.model_leg,
            "approval": "simulated_approved" if decision == "approve" else "simulated_rejected",
            "approval_gate": "approval gate (simulated actor)",
            "simulated": True,
            "publish": published,
            "cost_usd": provider_result.cost_usd,
            "cost_basis": provider_result.cost_basis,
            "timeout_s": provider_result.timeout_s,
            "timed_out": provider_result.timed_out,
            "external_side_effect": False,
            "withheld_sensitive": len(withheld),
            "snapshot_fallbacks": fallback_pulls,
            "live_pulls": live_pulls,
        }
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ranking.json").write_text(_ranking_json(ranked), encoding="utf-8")
    (out_dir / "withheld_sensitive.json").write_text(
        _withheld_json(withheld),
        encoding="utf-8",
    )
    (out_dir / "briefing.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    simulated_note = (
        "Approval gate (simulated actor): SIMULATED by simulated-editor. "
        "Production needs an authenticated channel; this lab does not have one."
    )
    (out_dir / "briefing.md").write_text(
        render_markdown(
            program_id=program_id,
            status=str(record["status"]),
            model_leg=model_leg,
            rubric_version=rubric.version,
            segments=segments,
            simulated_note=simulated_note,
        ),
        encoding="utf-8",
    )
    (out_dir / "map.html").write_text(
        render_map(ranked, title=f"NYC incidents ({mode})"),
        encoding="utf-8",
    )
    top = [
        {
            "rank": item.rank,
            "id": item.incident.id,
            "group": item.incident.category_group.value,
            "score": item.score,
        }
        for item in ranked[:5]
    ]
    return {
        "program_id": program_id,
        "status": record["status"],
        "mode": mode,
        "model_leg": model_leg,
        "cost_usd": provider_result.cost_usd,
        "cost_basis": provider_result.cost_basis,
        "incident_count": len(ranked),
        "withheld_sensitive": len(withheld),
        "rubric_version": rubric.version,
        "simulated": True,
        "published": published,
        "out_dir": str(out_dir),
        "as_of": as_of.isoformat(),
        "top": top,
    }


def _refresh_mode(client: SocrataClient) -> str:
    """Label the refresh that actually happened. A partial snapshot fallback is not online."""
    live = client.live_pulls
    fallback = client.fallback_pulls
    total = live + fallback
    if fallback == 0 and live > 0:
        return "online (SODA refresh then rank)"
    if live == 0:
        return "snapshots (SODA refresh fell back to snapshots)"
    return f"mixed (SODA refresh with snapshot fallback on {fallback} of {total} pulls)"


def _ranking_json(ranked: list[RankedIncident]) -> str:
    payload = [item.model_dump(mode="json") for item in ranked]
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _withheld_json(withheld: list[Incident]) -> str:
    payload = [
        {
            "id": item.id,
            "category": item.category,
            "borough": item.borough,
            "occurred_on": local_calendar_date(item.created_at).isoformat(),
            "reason": "sensitive category excluded from the public briefing and map",
        }
        for item in withheld
    ]
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
