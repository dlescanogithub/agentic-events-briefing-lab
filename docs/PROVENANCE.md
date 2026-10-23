# Provenance

The lab brief named a reference repo, `dlescanogithub/agent-runtime-evals`, pull request #1 draft, branch `cursor/agent-runtime-evals-mvp-7e58`, commit `55cfd4183fb2489d77fc9c8552e008274dc78f77`, as a quality template and a possible source for a documented copy of an eval kit.

On 2026-10-17 this environment could not read that repo. `git ls-remote` and the GitHub API both returned 404 with the token available here (the token is scoped to this repository). No file was copied from that commit. This tree does not contain a byte-for-byte copy, and it does not claim one.

What was written here, following the patterns the brief named:

| Piece in this repo | Pattern named in the brief |
| --- | --- |
| `src/events_briefing/providers/cassette.py` | cassette provider |
| `src/events_briefing/providers/stub.py` | fake / stub provider, off-by-default live adapter |
| `src/events_briefing/trace.py` | JSONL trace |
| `src/events_briefing/logging_setup.py` | JSON logging |
| `src/events_briefing/secretscan.py` | secret scan |
| `src/events_briefing/evalkit/` | invariant checks, not exact tool-call trajectories |

Those modules are original to this repo. If the reference repo becomes readable later, a diff should replace this note with a real copy list: source path, commit, and what changed.
