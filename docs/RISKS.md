# Risks

Owners are roles for a future desk, not named people. In this lab the owner of record is the repository owner.

| Risk | Probability | Impact | Mitigation | Owner |
| --- | --- | --- | --- | --- |
| Exact address or free text lands in a snapshot or output | Low if the allowlist holds; refresh is manual so a bad `$select` is possible | High | Allowlist, round-before-write, test that forbidden keys fail the load | Data steward |
| Life-safety item ranked under noise because weights drift | Medium if floors are removed | High | Hard floors in `config/rubric.json`; eval invariant; forced regression proves the gate can go red | Rubric owner |
| Draft text says the item was already sent | Medium | High | State machine; weak verb-plus-object heuristic with a negation window. Previous regex, 2026-10-17, n=20, small: paraphrase recall 0/20, negation false positives 3/20. External verification VERIFY_REPORT_9, same day, n=20, small, not conclusive: post-change recall 7/20, false positives 3/20. This lab has not re-run that corpus. Not a control. Outbox write only from `APPROVED` | Briefing editor |
| Live model spend runs away | Low while `LIVE_LLM` defaults off | Medium | Env prices, `MAX_LIVE_SPEND_USD`, refuse before the call when the estimate exceeds the cap. Estimate is chars/4, **[EST]** | Platform owner |
| Snapshot goes stale | High, because refresh is manual | Low for a lab; medium for a desk | Manifest has `captured_at` (2026-10-17). Do not describe the file as live | Data steward |
| FDNY borough centroid read as a real point | Medium | Medium | `location_precision=borough_centroid`. Centroids do not enter density | Data steward |
| Claim heuristic misses a paraphrase or flags a negation | High | Medium | Weak heuristic. External verification VERIFY_REPORT_9, 2026-10-17, n=20, small, not conclusive: recall 7/20, false positives 3/20. A lab re-run is not measured yet. Not a control | Platform owner |
| Secret committed | Low | High | `.env` gitignored, CI secret scan, no keys in `.env.example` | Platform owner |
| Someone treats the approval gate (simulated actor) as authenticated approval | Medium | High | HMAC covers the program id, the approved text, a one-time nonce, and the nonce-ledger head. Copy onto another id is rejected. Deleting the nonce ledger and restoring an old APPROVED file is rejected. Restoring the ledger together with that file is not stopped here. The public lab fixture is refused outside demo mode and must be rotated. This is still not an authenticated channel. Production needs one | Briefing editor |
| Briefing dates use the UTC day | Medium before the New York conversion | Medium | `created_at` is converted to America/New_York before `.date()`. Measured 2026-10-17, `demo --offline`: briefing text had 2026-09-30 and not 2026-10-01 | Data steward |
| A partial SODA fallback is described as a full online refresh | Medium | Low | Mode is `mixed` or `snapshots` when any pull falls back. `mode=online` is only a full refresh. `SOCRATA_RUN_BUDGET_S` (default 45 s) bounds only the SODA refresh. It does not bound the model. `MAX_LIVE_SPEND_USD` is the money cap for the model. Per-fetch default remains 20 s. Worst case of 6 times 20 s is arithmetic, not a measured latency | Platform owner |
| A sensitive category is plotted at about 1.1 km | Medium if the list is incomplete | High | `config/sensitive_categories.json` drops sexual, domestic, and child-related terms from the public briefing and the map. Withheld rows keep no coordinates | Data steward |
| City terms misunderstood as MIT | Medium | Medium | README, NOTICE, and docs/DATA_SOURCES.md say code is MIT and the snapshots are not. LICENSE is the MIT text only | Repository owner |

Probability and impact words are qualitative judgments for this lab, not measured frequencies.
