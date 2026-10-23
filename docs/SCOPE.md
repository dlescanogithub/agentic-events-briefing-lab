# Scope

No fees. Effort in person-days is not estimated.

## Phase 0 — this repo (implemented)

Offline snapshots, explicit rank, stub briefing, simulated approval, local outbox, static map, invariant evals, forced regression.

Exit criteria, measured 2026-10-17 with `python3 -m events_briefing eval` (`APPROVAL_STATE_KEY` unset) and `python3 -m pytest` on commit `61618ad9d63e78ab9fac014db52375fe4888b305`: eval 8 PASS / 0 FAIL / 0 INCOMPLETE; tests 55 passed; pytest-cov total 88.51%. Remeasured 2026-10-22, Python 3.12.3, pytest 9.1.1, package 0.1.0, `APPROVAL_STATE_KEY` unset: 56 passed and the same 88.51% total. The extra pass is one docs-contract test added with this change. Statement coverage that day was 91.83% (2068/2252). The eval elapsed time was not remeasured on 2026-10-22.

Assumptions: public NYC SODA fields listed in `docs/DATA_SOURCES.md`; floating timestamps interpreted as America/New_York; FDNY has no point location.

## Phase 1 — shadow (design only)

A person runs a live SODA read on a schedule they own and compares the rank to their current routine. Nothing is sent. Disagreements update `config/rubric.json`. The synthetic eval still has to pass.

Exit criteria (not measured): a written disagreement log, zero external effects, a rubric version the editor accepts.

Out of this phase: authenticated approval, chat bots, dispatch.

## Phase 2 — gate on one owned channel (design only)

Replace simulated approval with an authenticated decision. The single effect is a post into a channel the desk already controls. Spend cap stays on. Rollback is "stop the job and delete the local outbox", plus whatever undo that channel supports. That undo is not built here.

Exit criteria (not measured): every publish has an authenticated approver in the trace; unapproved publish count stays 0; a rollback drill is written down.

## Out of scope

- Auto-dispatch to field crews.
- Exact addresses or free-text narratives.
- Training a model.
- Relicensing City data under MIT.
- Claiming production metrics this repo did not measure.

## Assumptions that can invalidate the lab

- The City changes field names. The allowlist would fail closed or drop rows; refresh is manual.
- A desk defines life-safety differently. The floors must change and the eval must be re-run.
- A regulator requires coarser location than 2 decimal degrees. Drop coordinates rather than "almost" complying.
