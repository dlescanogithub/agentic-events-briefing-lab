# Runbook

This lab has no production process. The notes below are how to operate the repo and how a future handoff would look.

## Operate

- Default: `python3 -m events_briefing demo --offline`
- Gate: `python3 -m events_briefing eval` (exit 0 only when every scenario is PASS)
- Prove the gate can go red: `python3 -m events_briefing eval-regression` (exit 1 is the expected failure)
- Live check that does not call a vendor: `python3 -m events_briefing live` (prints `expect_failures`)
- New public snapshot, manual, uses the network: `EVENTS_OFFLINE=0 python3 -m events_briefing refresh-snapshots --online`
- After a refresh, re-run the privacy test and read the diff before committing. Coordinates must already be rounded.

## Monitor

- JSON logs on stderr include `timeout_s` on SODA attempts. A timeout is a warning, not a silent skip.
- `out/trace.jsonl` records model leg, cost, approval label, and whether a publish happened.
- `fixtures/snapshots/manifest.json` has `captured_at`. If that date is old, say so. Do not call the file live.

## Incidents

| Symptom | What to do |
| --- | --- |
| Eval exits non-zero | Read the scenario `detail`. Do not relax the invariant to get a green run |
| Regression exits 0 or 2 | The broken ranker no longer fails the floor, or the real ranker failed. The gate is not proving anything. Fix the check |
| Forbidden key in a snapshot | Do not commit. Fix the allowlist and recapture |
| Suspected secret in the tree | `python3 -m events_briefing secretscan`. Rotate anything that was real. The scanner's recall is not measured |
| Demo printed a live model leg | Stop. `demo --offline` forces the stub. A live leg means that force failed |

## Ownership

| Piece | Role |
| --- | --- |
| Rubric floors and category map | Rubric owner |
| Field allowlist and snapshot review | Data steward |
| Approval decision | Briefing editor. In this lab the actor is `simulated-editor` |
| Spend cap, CI, rollback of the repo | Platform owner / repository owner |

## Rollback

- Demo outputs live under `out/` (gitignored). Delete that directory to drop a local publish.
- A bad snapshot is rolled back by restoring the previous file in git. Do not "fix" it by editing coordinates by hand without a note.
- There is no external system to undo.

## Handoff

Give the next person this README, `docs/RUBRIC.md`, `docs/DATA_SOURCES.md`, and `docs/RISKS.md`. Tell them the approval in the demo is simulated, the live provider is off, and the synthetic rate is not a production metric. Point them at `docs/ADAPT_TO_A_REAL_CLIENT.md` before any real desk.
