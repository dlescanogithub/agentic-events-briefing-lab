# Business value

Fictional desk only. Editorial Muelle is a name already used in [BUSINESS_CASE.md](BUSINESS_CASE.md) for a made-up civic newsroom. It is not a client and not an employer. This note does not add a second company, and it does not add money figures that are not already in this repository.

Labels:

- **MEASURED**: a command in this lab produced the number, with the date.
- **[EST]**: an illustrative assumption this repository already marks as [EST]. Not a wage, a quote, or a fee.
- **not measured**: this repository does not have the number. External checks cited elsewhere were not re-run here.

No new **[SYN]** volume is introduced below. Where a sibling-style value plan would invent a monthly caseload or an integration budget, this note leaves the cell empty and says not measured.

## Buyer and problem

The buyer in these docs is a morning briefing desk that reads public incident feeds. The problem, from [BUSINESS_CASE.md](BUSINESS_CASE.md): volume alone is a bad sort, because noise complaints can bury a smaller set of life-safety items, and a draft can read as if it had already been sent.

This repository is the offline lab for that pattern (phase 0 in [SCOPE.md](SCOPE.md)). It is not a desk's system of record. Publish here writes a local outbox file after an approval gate (simulated actor). It does not send mail, chat, or dispatch.

## Value levers

Four levers, each tied to something the lab actually contains:

1. **Attention.** An explicit rubric with hard floors ranks life-safety above noise. On the synthetic labeled set that is MEASURED (see the KPI table). A newsroom's own definition of life-safety is not measured.
2. **Control.** The state machine refuses to publish from `DRAFT`. The eval scenario `no_unapproved_publish` is MEASURED. The gate is an approval gate (simulated actor), not an authenticated channel.
3. **Cost of the default path.** `demo --offline`, the eval, and CI do not call a paid model. Stub cost is 0 USD MEASURED. A live invoice from this lab is not measured.
4. **Trace.** Each run can record inputs hash, rubric version, model leg, approval, and publish (`src/events_briefing/trace.py`). That is a lab trace, not an audit opinion.

The model does not own the rank floors, the allowlist, or the publish decision. [DISCOVERY.md](DISCOVERY.md) is the question list for a real desk. [SCOPE.md](SCOPE.md) keeps shadow (phase 1) and a real channel (phase 2) as design only.

## Baseline and target KPIs

Baselines that this repository never collected from a desk are marked not measured. Targets that are only the lab gate are not newsroom targets.

| KPI | Baseline | Target | How | Label |
| --- | --- | --- | --- | --- |
| Life-safety incidents above every noise incident | No desk baseline in this repo | 3/3, rate 1.0, on synthetic n=10 | `python3 -m events_briefing eval` | MEASURED 2026-10-17. Not nDCG. Not a newsroom precision number |
| Invariant scenarios | — | 8 PASS, 0 FAIL, 0 INCOMPLETE. One run, elapsed 6.996 ms | Same command. `APPROVAL_STATE_KEY` unset. Package 0.1.0, Python 3.12.3 | MEASURED 2026-10-17 |
| Unapproved local publish | A draft can be mistaken for something already sent (problem statement) | 0 in that eval (publish from `DRAFT` refused) | Scenario `no_unapproved_publish` | MEASURED 2026-10-17 |
| Forced regression | The gate must be able to go red | Exit 1; pass=1 fail=1 incomplete=0 | `python3 -m events_briefing eval-regression` | MEASURED 2026-10-17 |
| Items in a morning sitting | On the order of 30 | — | [BUSINESS_CASE.md](BUSINESS_CASE.md) | **[EST]**. Not measured |
| Time a ranked draft might avoid | Not measured | About 20 minutes of that sitting | Same note | **[EST]** |
| Illustrative loaded cost | Not a wage in this repo | 45 USD/hour | Same note | **[EST]** |
| Illustrative saving | Not measured | 15 USD per morning; 300 USD per month | 20/60 * 45 = 15; 15 * 20 mornings = 300 | **[EST]** |
| Editor acceptance | — | Not set in this repo | [METRICS.md](METRICS.md) | not measured |
| Live model quality or latency in this lab | — | Not set | `python3 -m events_briefing live` does not call a vendor | not measured here. External samples are cited in [METRICS.md](METRICS.md) and were not re-run |
| Publish-claim heuristic | Weak verb-plus-object check | Not a target. It is not a control | [METRICS.md](METRICS.md) | External 2026-10-17 sample. This lab has not re-run it (not measured yet) |
| Tests and coverage | See [Proof in the README](../README.md#proof) | Floor 80% on the pytest-cov total | `pytest --cov` | MEASURED 2026-10-22 |

Do not quote the rate 1.0 outside the synthetic set. [METRICS.md](METRICS.md) says the same.

## ROI model

All four inputs are the **[EST]** assumptions already written in [BUSINESS_CASE.md](BUSINESS_CASE.md). This note does not change them.

- A person scans on the order of 30 items in a morning sitting. **[EST]**
- A ranked draft might avoid about 20 minutes of that sitting. **[EST]**. Not measured here.
- An illustrative loaded cost of 45 USD/hour. **[EST]**. Not a wage, not a quote, not a fee.
- 20/60 * 45 = 15 USD per morning. **[EST]**
- 15 USD * 20 mornings = 300 USD per month. **[EST]**

A ratio (benefit − cost) / cost is **not reported**. An adoption cost (integration, an authenticated channel, staff time to run shadow) is not in this repository, so a payback in months would be an invented denominator. The measured software cost of the default path is 0 USD. Using 0 as the only cost would not be a meaningful ROI. If the assumption of 20 minutes is wrong, the 15 USD and 300 USD figures are wrong. City data terms are not in that arithmetic. This repository does not charge a fee.

What would have to be true, copied from the business case: the desk agrees the rubric floors match their definition of life-safety; a human still approves; "publish" stays a local file until an authenticated channel exists. That channel is not in this repo.

## Cost table

| Item | Figure | Label |
| --- | --- | --- |
| Offline stub eval | 0 USD | MEASURED 2026-10-17, `python3 -m events_briefing eval`, package 0.1.0, Python 3.12.3. Gate elapsed 6.996 ms on that one run. p50/p95 not measured |
| Offline stub demo | 0 USD | MEASURED 2026-10-17. Five runs around `run_offline_demo`: min 5.418 ms, median 5.789 ms, max 7.803 ms. p95 not measured |
| SODA refresh at the public endpoint | 0 USD, no invoice | Capture 2026-10-17. App token optional and empty. Six HTTP pulls in the committed capture |
| Live model invoice from this lab | Not measured | Prices, if set, come from the environment. `MAX_LIVE_SPEND_USD` is the money cap. External dollar figures are quoted in [COST.md](COST.md). This lab did not repeat those calls |
| Pre-call size estimate | Input characters divided by 4, plus a reserved 800 output tokens. Cached tokens are ignored | **[EST]** method in [COST.md](COST.md). Not an invoice |
| Illustrative desk time | 15 USD per morning; 300 USD per month | **[EST]** from the ROI model above. Not measured |
| Integration, channel, or staffing to adopt the pattern | Not in this repository | not measured |

`SOCRATA_RUN_BUDGET_S` (default 45 s) bounds only the SODA refresh. It does not bound the model. Six pulls times 20 s is 120 s of arithmetic, not a measured latency. Detail and the external live rows stay in [COST.md](COST.md).

## Measurement plan

Phase 0 is this repository. The commands that produce the MEASURED rows are:

- `python3 -m events_briefing eval` for the invariant gate.
- `python3 -m events_briefing eval-regression` for a forced red run (exit 1).
- `python3 -m pytest` with coverage for the suite. The 2026-10-22 remeasure is in the README Proof section. The 80% floor applies to the pytest-cov total (lines and branches), which was 88.51% that day.
- `python3 -m events_briefing demo --offline` for the snapshot path (67 public incidents, 1 sensitive row withheld, on the 2026-10-17 run).
- `python3 -m events_briefing secretscan` for the pattern scan. A clean scan is not a proof that no secret exists. Recall is not measured.

Phase 1 (shadow) is design only. [SCOPE.md](SCOPE.md) names the exit that is not measured: a written disagreement log, zero external effects, and a rubric version the editor accepts. Time saved and editor acceptance would be collected there, by the desk, not by this eval.

Phase 2 (one authenticated channel the desk owns) is design only. Exit criteria in SCOPE are not measured: every publish has an authenticated approver in the trace, unapproved publish count stays 0, and a rollback drill is written down.

[METRICS.md](METRICS.md) is the metric list. This plan does not replace it.

## Risks

Owners below are roles. In this lab the owner of record is the repository owner. Probability and impact words in [RISKS.md](RISKS.md) are qualitative judgments, not measured frequencies. The rows that most directly touch the value story:

| Risk | Why it matters to the value story | Where |
| --- | --- | --- |
| Floors removed, so life-safety can rank under noise | The attention lever depends on the floors. The forced regression is there to show the gate can go red | [RISKS.md](RISKS.md), `config/rubric.json` |
| A draft reads as already sent | The control lever is the state machine. The publish-claim checker is a weak heuristic, not a control | [RISKS.md](RISKS.md), [METRICS.md](METRICS.md) |
| The simulated gate is treated as authenticated approval | HMAC plus an allowlist is not an authenticated channel. Restoring the nonce ledger together with an old APPROVED file still republishes | [RISKS.md](RISKS.md), `src/events_briefing/briefing/gate.py` |
| The 20 minute assumption is wrong | The 15 USD and 300 USD figures move with it | [BUSINESS_CASE.md](BUSINESS_CASE.md) |
| City data terms read as MIT | Code is MIT. Snapshots are not | `NOTICE`, [DATA_SOURCES.md](DATA_SOURCES.md) |
| Live spend | `LIVE_LLM` defaults off. The pre-call estimate is **[EST]** (characters divided by 4) | [COST.md](COST.md) |

## Measured and not measured

**MEASURED in this lab**

- Invariant eval on 2026-10-17: 8 PASS, 0 FAIL, 0 INCOMPLETE, synthetic n=10, life-safety-above-noise rate 1.0, elapsed 6.996 ms on that one run, `APPROVAL_STATE_KEY` unset, package 0.1.0, Python 3.12.3.
- Forced regression the same day: exit 1.
- Stub cost 0 USD. SODA public endpoint 0 USD with no invoice on the 2026-10-17 capture.
- Offline demo the same day: 67 public incidents, 1 sensitive row withheld, mode snapshots, briefing text had 2026-09-30 and did not have 2026-10-01. Five timing runs: min 5.418 ms, median 5.789 ms, max 7.803 ms.
- Tests remeasured 2026-10-22: 56 passed, statement coverage 91.83% (2068/2252), pytest-cov total 88.51% with branch coverage on. Python 3.12.3, pytest 9.1.1, package 0.1.0, `APPROVAL_STATE_KEY` unset. The 2026-10-17 note recorded 55 passed and the same 88.51% total. The extra pass is one docs-contract test. It does not change the statement counts.

**Not measured here**

- Minutes saved, editor acceptance, and any newsroom baseline.
- An ROI percentage or a payback period.
- Live model quality, latency, or a paid invoice from this lab. External samples from 2026-10-17 are quoted in [COST.md](COST.md) and [METRICS.md](METRICS.md). They are small, and this lab did not re-run them.
- Recall of the publish-claim heuristic and of the briefing text checker, as a lab re-run. Both are not a reliable control. The text checker misses the form "Brooklyn saw 4…", invented casualties, and invented superlatives.
- nDCG, a precision number from a desk, multi-user auth, and any external send.
