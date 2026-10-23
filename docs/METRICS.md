# Metrics

| Metric | Value | Status | How |
| --- | --- | --- | --- |
| Invariant scenarios PASS | 8 | MEASURED 2026-10-17, package 0.1.0, Python 3.12.3, `APPROVAL_STATE_KEY` unset, elapsed 6.996 ms (one run) | `python3 -m events_briefing eval` |
| FAIL / INCOMPLETE on that gate | 0 / 0 | MEASURED, same command | A scenario that throws is INCOMPLETE, never PASS |
| Synthetic labeled incidents | n=10 | MEASURED, same command | `src/events_briefing/evalkit/synthetic.py` |
| Life-safety incidents ranked above every noise incident | 3/3, rate 1.0 | MEASURED on that synthetic set only | Same command. Not nDCG. Not production precision |
| Forced regression exit code | 1 | MEASURED 2026-10-17 | `python3 -m events_briefing eval-regression` |
| Test count and coverage | 56 passed on 2026-10-22. pytest-cov total 88.51% with branch coverage on. Statement (line) coverage 91.83% (2068/2252). The 2026-10-17 count was 55 passed | 55 passed and the 88.51% total were recorded on 2026-10-17 (commit `61618ad9d63e78ab9fac014db52375fe4888b305`, Python 3.12.3). On 2026-10-22 the same command printed 56 passed and the same 88.51% total (Python 3.12.3, pytest 9.1.1, package 0.1.0, `APPROVAL_STATE_KEY` unset, Python sources at `a95e827`). The extra pass is one docs-contract test outside the package. Statement coverage was split out on 2026-10-22 only. `percent_statements_covered` was 91.82948490230906. `percent_covered` was 88.50889192886457. The floor of 80% applies to the pytest-cov total | `python3 -m pytest -o addopts= --cov=events_briefing --cov-report=term-missing --cov-fail-under=80` |
| Unapproved publish in the eval | 0 (publish from DRAFT refused) | MEASURED, scenario `no_unapproved_publish` | Same eval command |
| Stub cost | 0 USD | MEASURED, scenario `cost_within_cap` | Same eval command |
| Offline demo incidents | 67 public, 1 sensitive row withheld. Briefing markdown had 2026-09-30 and not 2026-10-01 | MEASURED 2026-10-17, commit `61618ad9d63e78ab9fac014db52375fe4888b305`, `APPROVAL_STATE_KEY` unset | `python3 -m events_briefing demo --offline` |
| Demo duration | min 5.418 ms, median 5.789 ms, max 7.803 ms, n=5 | MEASURED 2026-10-17 | `time.perf_counter` around `run_offline_demo`. p95 not measured |
| Editor acceptance | — | not measured | Would be a shadow-phase log |
| Live model quality or latency | 5 of 6 runs accepted model text; 0 borough-count rejections | External verification VERIFY_REPORT_11, 2026-10-17, model grok-4.20-0309-non-reasoning, n=6, small sample, not a rate. This lab did not re-run that (not measured yet here). `python3 -m events_briefing live` does not call a vendor | `src/events_briefing/cli.py` |
| Publish-claim heuristic | weak heuristic. Previous regex: paraphrase recall 0/20, negation false positives 3/20. External verification VERIFY_REPORT_9, 2026-10-17, n=20, small, not conclusive: post-change recall 7/20, false positives 3/20. This lab has not re-run that corpus (not measured yet). Not a control | cited external check, not a lab re-measure | `src/events_briefing/briefing/invariants.py` |
| Borough and category counts in briefing text | partially checked. VERIFY_REPORT_10: 13/19 detected, 1/10 false positives. VERIFY_REPORT_11, different set: 13/24 detected, 3/15 false positives | Both external, 2026-10-17, small samples, not conclusive, not comparable with each other. A category count scoped to a borough is only partially checked: false positives remain, and "Brooklyn saw 4…" is not covered. This lab did not re-run either set (not measured yet). It is not a reliable control | `src/events_briefing/briefing/textcheck.py` |

Do not quote the rate 1.0 outside the synthetic set.
