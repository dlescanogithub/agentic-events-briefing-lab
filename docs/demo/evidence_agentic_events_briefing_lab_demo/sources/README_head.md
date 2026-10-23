# Agentic events briefing lab

**Start here**

- Proves an explicit rubric ranks every life-safety incident above noise on a synthetic set, and a local outbox stays empty until an approval gate (simulated actor) is APPROVED.
- One command: `python3 -m events_briefing demo --offline`
- Docs: [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)

Recreated scenario with public data, not a client deliverable.

Architecture inspired by a team project; this is a personal recreation with public data, not a client deliverable.

`demo --offline` and `briefing` read snapshot files only. They do not call SODA or a model. `briefing --online` refreshes SODA for that run without rewriting the committed snapshots. The mode line is the refresh that happened: `online (SODA refresh then rank)` only when every pull succeeded. A partial snapshot fallback is labeled `mixed`, and a full fallback is labeled `snapshots`. `briefing --live` calls a model only when `LIVE_LLM=1`, `XAI_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, both prices, and `MAX_LIVE_SPEND_USD` are set. If any of those are missing, the command exits 2, names each missing one, and does not call a model. The command `live` does not call a vendor.

`SOCRATA_RUN_BUDGET_S` (default 45 s) bounds only the SODA refresh. It does not bound the model, and it is not a cap on the whole `briefing --online --live` command. `MAX_LIVE_SPEND_USD` is the money cap for the model. `LLM_TIMEOUT_S` and `LLM_MAX_ATTEMPTS` bound model time. There is no single wall-clock cap for `--online --live`. The prompt includes borough counts the code already computed. The model copies them and does not count.

## Problem

A public incident feed mixes life-safety events with noise. A draft can also be mistaken for something that already left the building. This lab ranks a trimmed snapshot and refuses to publish unless the state machine is in `APPROVED`.

The fictional desk in the business notes is Editorial Muelle. It is not a client. The only measured rank result is the synthetic gate from 2026-10-17: 8 PASS, 0 FAIL, 0 INCOMPLETE, n=10, life-safety-above-noise rate 1.0. That is not a newsroom precision number and it is not nDCG. The time-saving arithmetic is **[EST]** and is not measured. Both are spelled out under Proof, Business value, and [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md).

## Architecture

```mermaid
flowchart LR
  subgraph inputs [Inputs]
    soda[SODA live pull]
    snap[Offline snapshots]
  end
  soda -->|manual refresh only| snap
  snap --> norm[Allowlist, coarsen, dedupe]
  norm --> rank[Explicit rubric with floors]
  rank --> writer[Briefing writer]
  writer --> stub[Stub or cassette]
  writer --> live[Live provider off by default]
  stub --> gate[State machine]
  live --> gate
  gate -->|APPROVED only| outbox[Local outbox]
  rank --> map[Static HTML map]
