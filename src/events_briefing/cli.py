"""Command line. `python -m events_briefing` works when make is absent."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from events_briefing import __version__
from events_briefing.briefing.gate import GateError
from events_briefing.config import Settings
from events_briefing.evalkit.regression import run_regression
from events_briefing.evalkit.runner import eval_exit_code
from events_briefing.evalkit.scenarios import run_eval
from events_briefing.logging_setup import configure_logging
from events_briefing.pipeline import load_snapshot_incidents, run_briefing, run_offline_demo
from events_briefing.providers.live import LiveConfigError, live_requirement_errors
from events_briefing.ranking import rank_incidents
from events_briefing.rubric import RubricError, load_rubric
from events_briefing.secretscan import main_scan
from events_briefing.socrata import SocrataClient, SocrataError, write_snapshots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="events_briefing")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="rank, draft, simulate approval, write a local map")
    demo.add_argument("--offline", action="store_true", help="force snapshots and the stub model")
    demo.add_argument("--out", default="out", help="output directory (gitignored)")
    demo.add_argument("--decision", choices=("approve", "reject"), default="approve")
    demo.set_defaults(func=cmd_demo)

    refresh = sub.add_parser("refresh-snapshots", help="manual SODA pull; not for CI")
    refresh.add_argument("--online", action="store_true", help="required to hit the network")
    refresh.set_defaults(func=cmd_refresh)

    evaluate = sub.add_parser("eval", help="run invariant scenarios")
    evaluate.add_argument("--out", default="", help="optional JSON report path")
    evaluate.set_defaults(func=cmd_eval)

    regression = sub.add_parser(
        "eval-regression", help="forced red gate; exits 1 when the bug is caught"
    )
    regression.add_argument("--out", default="", help="optional JSON report path")
    regression.set_defaults(func=cmd_regression)

    live = sub.add_parser("live", help="print expect_failures; does not call a vendor")
    live.set_defaults(func=cmd_live)

    briefing = sub.add_parser(
        "briefing",
        help="draft from snapshots, or refresh then rank when --online is set",
    )
    briefing.add_argument(
        "--live",
        action="store_true",
        help=(
            "call the live model; requires LIVE_LLM=1, XAI_API_KEY, LLM_BASE_URL, "
            "LLM_MODEL, prices, and MAX_LIVE_SPEND_USD"
        ),
    )
    briefing.add_argument(
        "--online",
        action="store_true",
        help="labeled online mode: SODA refresh then rank for this run; does not rewrite snapshots",
    )
    briefing.add_argument("--out", default="out", help="output directory (gitignored)")
    briefing.add_argument("--decision", choices=("approve", "reject"), default="approve")
    briefing.set_defaults(func=cmd_briefing)

    scan = sub.add_parser("secretscan", help="scan the worktree for secret patterns")
    scan.set_defaults(func=cmd_scan)

    rank = sub.add_parser("rank", help="print the offline ranking")
    rank.add_argument("--offline", action="store_true")
    rank.set_defaults(func=cmd_rank)

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    configure_logging(settings.secret_values())
    return int(args.func(args, settings))


def cmd_demo(args: argparse.Namespace, settings: Settings) -> int:
    if not args.offline:
        print("demo requires --offline in this lab", file=sys.stderr)
        return 2
    try:
        summary = run_offline_demo(Path(args.out), settings, decision=args.decision)
    except (OSError, SocrataError, RubricError, GateError) as exc:
        print(f"demo failed: {exc}", file=sys.stderr)
        return 1
    print(
        "approval gate (simulated actor): simulated-editor. "
        "Production needs an authenticated channel; this lab does not have one."
    )
    print(f"mode={summary['mode']}")
    leg = summary["model_leg"]
    cost = summary["cost_usd"]
    status = summary["status"]
    print(f"model_leg={leg} cost_usd={cost} status={status}")
    count = summary["incident_count"]
    withheld = summary["withheld_sensitive"]
    version = summary["rubric_version"]
    print(f"incidents={count} withheld_sensitive={withheld} rubric={version}")
    print(f"out={summary['out_dir']}")
    top = summary.get("top")
    if isinstance(top, list):
        for item in top:
            if isinstance(item, dict):
                print(f"  {item['rank']:>2} {item['group']} {item['score']} {item['id']}")
    return 0


def cmd_refresh(args: argparse.Namespace, settings: Settings) -> int:
    if not args.online:
        print("refresh-snapshots refuses to run without --online", file=sys.stderr)
        return 2
    online = replace(settings, offline=False, live_llm=False)
    client = SocrataClient(online)
    try:
        path = write_snapshots(client)
    except (SocrataError, OSError) as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


def cmd_eval(args: argparse.Namespace, settings: Settings) -> int:
    try:
        rubric = load_rubric(settings.rubric_path)
    except RubricError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    report = run_eval(rubric, __version__)
    _emit(report.model_dump(mode="json"), args.out)
    print(
        f"eval pass={report.pass_count} fail={report.fail_count} "
        f"incomplete={report.incomplete_count} n={report.n_incidents} "
        f"life_safety_above_noise_rate={report.life_safety_above_noise_rate}"
    )
    return eval_exit_code(report)


def cmd_regression(args: argparse.Namespace, settings: Settings) -> int:
    try:
        rubric = load_rubric(settings.rubric_path)
    except RubricError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    report, code = run_regression(rubric, __version__)
    _emit(report.model_dump(mode="json"), args.out)
    print(
        f"eval-regression exit_planned={code} "
        f"pass={report.pass_count} fail={report.fail_count} incomplete={report.incomplete_count}"
    )
    return code


def cmd_briefing(args: argparse.Namespace, settings: Settings) -> int:
    online = bool(args.online)
    live = bool(args.live)
    print(_mode_line(online, live))
    if live:
        missing = live_requirement_errors(settings)
        if missing:
            print("briefing --live refused: " + ", ".join(missing), file=sys.stderr)
            print("live_llm_called=false", file=sys.stderr)
            return 2
    try:
        summary = run_briefing(
            Path(args.out),
            settings,
            live=live,
            online=online,
            decision=args.decision,
        )
    except (OSError, SocrataError, RubricError, GateError, LiveConfigError, RuntimeError) as exc:
        print(f"briefing failed: {exc}", file=sys.stderr)
        return 1
    print(f"mode={summary['mode']}")
    print(
        "approval gate (simulated actor): simulated-editor. "
        "Production needs an authenticated channel; this lab does not have one."
    )
    print(
        f"model_leg={summary['model_leg']} cost_usd={summary['cost_usd']} "
        f"cost_basis={summary['cost_basis']} status={summary['status']}"
    )
    print(
        f"incidents={summary['incident_count']} withheld_sensitive={summary['withheld_sensitive']} "
        f"as_of={summary['as_of']} rubric={summary['rubric_version']}"
    )
    print(f"out={summary['out_dir']}")
    return 0


def _mode_line(online: bool, live: bool) -> str:
    """Requested path only. The mode line after the run is the refresh that happened."""
    if online and live:
        return "requested=online + live model (mode is labeled after the refresh)"
    if online:
        return "requested=online (mode is labeled after the refresh)"
    if live:
        return "requested=snapshots + live model"
    return "requested=snapshots"


def cmd_live(args: argparse.Namespace, settings: Settings) -> int:
    del args
    print("expect_failures")
    print("live_llm_called=false")
    print("This command does not contact a model vendor.")
    print(f"LIVE_LLM={1 if settings.live_llm else 0}")
    print("not measured in this command:")
    print("- real-provider latency")
    print("- real-provider quality")
    print("- regex invariant recall")
    print("- production approval channel (not implemented)")
    return 0


def cmd_scan(args: argparse.Namespace, settings: Settings) -> int:
    del args, settings
    return main_scan()


def cmd_rank(args: argparse.Namespace, settings: Settings) -> int:
    if not args.offline:
        print("rank requires --offline in this lab", file=sys.stderr)
        return 2
    try:
        incidents, rubric = load_snapshot_incidents(settings)
    except (OSError, SocrataError, RubricError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for item in rank_incidents(incidents, rubric)[:20]:
        print(
            f"{item.rank:>2} {item.score:.4f} {item.incident.category_group.value} "
            f"{item.incident.id} {item.incident.category}"
        )
    return 0


def _emit(payload: dict[str, object], out: str) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    print(text)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
