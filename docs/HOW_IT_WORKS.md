# How this lab works

Recreated scenario with public data. It is not a client deliverable.

The architecture is inspired by a team project. This is a personal recreation with public data, not a client deliverable.

The business value note is in English in `docs/BUSINESS_VALUE.md`. That note does not add figures: it uses the ones this repository already marks as measured or as [EST].

## Analogy

Think of a newscast desk, not a magic chat. Wires come in (the open data). An editor with a written rule orders the items. A scriptwriter drafts the program. Nobody goes on air until a person says yes, and here that "air" is a local folder. The model, when it is present, is the scriptwriter. The system around it is the control desk: the rule, the data trim, and the gate.

## The path, step by step

1. Look at where the data comes from. The briefing reads snapshots in `fixtures/snapshots/`, captured on 2026-10-17. The demo and `briefing` with no flags do not touch the network. If you want a refresh and then the rank, the command is `python3 -m events_briefing briefing --online`. It does not rewrite the committed snapshots. The label `mode=online (SODA refresh then rank)` appears only if every pull responded. If any pull falls back to the snapshot, the mode is `mixed`. If every pull falls back, the mode is `snapshots`. Each pull has a cap (`SOCRATA_FETCH_BUDGET_S`, default 20 s). `SOCRATA_RUN_BUDGET_S` (default 45 s) bounds only the SODA refresh: it does not bound the model and it is not a cap on the whole `briefing --online --live` run. The money cap for the model is `MAX_LIVE_SPEND_USD`. `LLM_TIMEOUT_S` and `LLM_MAX_ATTEMPTS` bound model time. Without the refresh cap, 6 pulls times 20 s would be about 120 s; that is arithmetic on the config, not a time measured live. To save new snapshots, the separate command is `refresh-snapshots --online`. CI does not run it.
2. See what is dropped. Addresses, names, phone numbers, and free text do not come in. Latitude and longitude are rounded to 2 decimal places (about 1.1 km) before they are stored. The precision-6 geohash is computed on that already-rounded number. FDNY does not bring a point: the map places a schematic borough center and marks it `borough_centroid`. That is not a coordinate from the source.
3. The rubric orders. Each group has a floor: life-safety above, noise below. Inside the floor, severity, recency, density, and category have weight. The weights are in `config/rubric.json`. The same input gives the same order.
4. The scriptwriter writes a JSON with segments: title, why it matters, source ids. The prompt carries each incident's date (only the day in America/New_York, not the UTC day), an `AS_OF` date in that same zone, and `BOROUGH_COUNTS` already computed by the code. The model copies them; it does not count incidents. An FDNY fire at 23:51 New York time stays on the local day even when UTC is already the next day. Measured on 2026-10-17 with `demo --offline` and the key unset: the markdown said `2026-09-30` and did not say `2026-10-01`. If the text says "today" when the data are not from that day, uses a plural for a single case, or a borough count that does not match ("one in Brooklyn" when there are two), it is retried with a cap and then there is a deterministic fallback. Live cost sums the ticks of every attempt, including the rejected one. The default provider is a stub. The live model runs only with `briefing --live` when `LIVE_LLM=1`, `XAI_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, both prices, and `MAX_LIVE_SPEND_USD` are set. If any is missing, the command exits with code 2 and names the ones that are missing. It does not call the model. Nothing is published "because the model said so".
5. The gate is a state machine: `DRAFT` → `PENDING_APPROVAL` → `APPROVED` or `REJECTED` → `PUBLISHED`. It is called an approval gate (simulated actor). The state is signed with HMAC. The signature includes the program id, the approved text, and a one-time nonce. Copying an APPROVED file from one id onto another fails. Deleting `nonce-ledger.json` and restoring an old APPROVED file also fails. Restoring the ledger together with that APPROVED file still republishes, because the same key signs both. The actor has to be on the list. Publish writes `out/outbox/`. In the demo the approval says **SIMULATED**. `demo` and `eval` use the public lab key if `APPROVAL_STATE_KEY` is unset. `briefing` refuses it: it has to be rotated. Production needs an authenticated channel. That is not built.
6. A JSONL trace is left: hash of the inputs, rubric version, model leg (`stub`, `cassette`, `live`, or `fallback`), whether there was an approval, and whether it was published.
7. The HTML map is built on its own, without requesting tiles. It still carries the OpenStreetMap tile attribution control (`leaflet-control-attribution`), with the copyright link. Sensitive categories (sexual offenses and the configurable list of domestic violence or offenses involving minors) do not enter the map or the public briefing.

## Glossary

| Word | What it is here |
| --- | --- |
| Snapshot | A small, already trimmed picture of a public dataset |
| Rubric | The ordering rule, with weights and floors, in a JSON file |
| Floor | A number that separates groups so that life-safety does not land below noise |
| Scriptwriter | The module that builds the program (JSON + Markdown) |
| Stub | A fixed response, with no network and no cost |
| Cassette | A recorded response for tests |
| Gate | The state machine before the outbox |
| Outbox | The local folder that is written only with status `APPROVED` |
| Model leg | Whether that run was stub, cassette, live, or fallback |

## Honest limits

- The rate 1.0 of "life-safety above noise" was measured on 2026-10-17 on 10 synthetic incidents (`python3 -m events_briefing eval`, key unset, 8 PASS, elapsed 6.996 ms on that run). It is not a production precision number. On 2026-10-22 the suite was measured again, not that eval run: Python 3.12.3, pytest 9.1.1, key unset, 56 passed. The 2026-10-17 note recorded 55; this change adds one docs-contract test. Statement coverage 91.83% (2068 of 2252). The pytest-cov total, with branches, was 88.51%. The detail is in the Proof section of the README.
- The detector for "this was already published / was already sent" is a weak verb-plus-object heuristic, with a negation window. It is not a control. The previous regex, measured on 2026-10-17 with n=20 (small sample), had recall 0/20 on paraphrases and 3/20 false positives on negations. An external verification (VERIFY_REPORT_9, the same day, n=20, small sample, not conclusive) measured recall 7/20 and 3/20 false positives after the change. This lab did not re-run that set: not measured yet.
- The text check is not a reliable control. A category count scoped to a borough is only partially understood: false positives remain, and it does not cover the form "Brooklyn saw 4…". An external verification (VERIFY_REPORT_10, 2026-10-17, n=19 incorrect texts, small sample, not conclusive) detected 13/19 and had 1/10 false positives. Another external verification, with a different set (VERIFY_REPORT_11, 2026-10-17, 24 incorrect and 15 correct, small sample, not conclusive), detected 13/24 and had 3/15 false positives. Those two sets are not comparable. This lab did not re-run either: not measured yet. It also does not cover invented casualties or invented superlatives. After the prompt with counts, that same verification measured 5 of 6 `briefing --live` runs with accepted model text and 0 borough rejections (n=6, small sample, not a rate). This lab did not repeat those calls.
- Quality and latency with a paid model: not measured. The `live` command prints `expect_failures` and does not call anyone.
- The demo approval is an approval gate (simulated actor). It is not an authenticated channel.
- A borough center is not the location of the FDNY incident.
