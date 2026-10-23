# Changelog

## Unreleased

- Dropped repository-visibility lines from the README, `SECURITY.md`, `docs/ADAPT_TO_A_REAL_CLIENT.md`, `docs/PROVENANCE.md`, `docs/SCOPE.md`, and the 0.1.0 note. `SECURITY.md` tells reporters to use GitHub private vulnerability reporting ("Report a vulnerability" on the Security tab).
- Reworded the README use-case row, the docs index entry for `docs/HOW_IT_WORKS.md`, and the discovery paragraph so they read as a walkthrough for engineers and buyers.
- Checked Markdown for Spanish. `docs/HOW_IT_WORKS.md` is already English, and no other Markdown file was still in Spanish. Numbers, commands, links, and the labels `[EST]`, `[SYN]`, MEASURED, SIMULATED, and UNVERIFIED are unchanged.
- Tests remeasured on this docs change, Python 3.12.3, pytest 9.1.1, package 0.1.0, `APPROVAL_STATE_KEY` unset: 56 passed. Statement coverage 91.83% (2068/2252). pytest-cov total with branch coverage on: 88.51% (floor 80%). `ruff check`, `ruff format --check`, and `mypy` reported no issues.
- Translated `docs/HOW_IT_WORKS.md` from Spanish to English. Commands, numbers, `[EST]`, and links are unchanged. The README docs index no longer calls that walkthrough rioplatense Spanish.
- README is English, with a three-line Start here, a business-value section, a Proof section, and "What this does NOT prove".
- Added `docs/BUSINESS_VALUE.md`. Money figures are the existing [EST] lines from `docs/BUSINESS_CASE.md`. No new volume was added.
- Tests remeasured 2026-10-22, Python 3.12.3, pytest 9.1.1, package 0.1.0, `APPROVAL_STATE_KEY` unset: 56 passed (55 on 2026-10-17, plus one docs-contract test). Statement coverage 91.83% (2068/2252). pytest-cov total with branch coverage on: 88.51%, the same total recorded on 2026-10-17.
- `LICENSE` is the standard MIT text, copyright Diego Lescano. The note that NYC Open Data snapshots are not relicensed moved to `NOTICE`.
- Briefing text now gets each incident date and an as-of date, and retries when counts, plurals, dates, or relative time do not match.
- The publish step is an approval gate (simulated actor): HMAC state, approver allowlist, tamper rejection. It is not an authenticated channel.
- Publish-claim check is a weak verb-plus-object heuristic with a negation window. Previous regex, 2026-10-17, n=20, small: 0/20 paraphrases and 3/20 negation false positives. External verification VERIFY_REPORT_9, same day, n=20, small, not conclusive: 7/20 recall and 3/20 false positives. This lab has not re-run that corpus.
- Sensitive categories are excluded from the public briefing and map.
- The offline map includes an OpenStreetMap tile attribution control. Tiles are still not requested.
- `briefing --live` and `briefing --online` are explicit. The default briefing reads snapshots only.
- Live cost uses `cost_in_usd_ticks` (1 tick = 1e-10 USD) when the provider returns it. The pre-call estimate ignores cached tokens.
- SODA has a per-fetch budget and a refresh budget. A partial snapshot fallback is labeled mixed, not online.
- Incident dates in the prompt and the checker use the America/New_York calendar day.
- Live `cost_usd` sums `cost_in_usd_ticks` across retries, including a rejected attempt.
- The approval gate (simulated actor) binds the HMAC to the program id and a one-time nonce. The public lab key is refused outside demo mode.
- Borough counts in the briefing text are checked. A category count scoped to a borough is only partially checked.
- The prompt includes borough counts computed by the code. The model is told to copy them and not to count. A category count scoped to a borough is only partially checked against that borough. False positives remain, and the form "Brooklyn saw 4…" is not covered.
- The text checker is not a reliable control. External verification VERIFY_REPORT_10, 2026-10-17, n=19 incorrect texts, small sample, not conclusive: 13/19 detected and 1/10 false positives. External verification VERIFY_REPORT_11, 2026-10-17, a different set (24 incorrect texts and 15 correct texts), small sample, not conclusive: 13/24 detected and 3/15 false positives. The two sets are not comparable. This lab did not re-run either set (not measured yet). The checker does not cover "Brooklyn saw 4…", invented casualties, or invented superlatives.
- `briefing --live` also requires `LLM_BASE_URL` and `LLM_MODEL`. If either is missing, the command exits 2 and names it. It does not call a model.
- External verification VERIFY_REPORT_11, 2026-10-17, model grok-4.20-0309-non-reasoning: 5 of 6 `briefing --live` runs accepted model text, and 0 were rejected for a borough count (n=6, small sample, not a rate). This lab did not re-run that.
- `SOCRATA_RUN_BUDGET_S` bounds only the SODA refresh. `MAX_LIVE_SPEND_USD` is the money cap for the model. There is no single wall-clock cap for `briefing --online --live`.
- The approval gate (simulated actor) binds the state HMAC to the nonce-ledger head. Deleting the ledger fails closed. Restoring the ledger together with an old APPROVED file still republishes. It is not an authenticated channel.

## 0.1.0 - 2026-10-17

Initial lab: offline NYC Open Data snapshots, explicit ranking rubric, stub briefing writer, local approval gate, invariant evals, and a forced-regression check.

No live-provider quality number is claimed in this version.
