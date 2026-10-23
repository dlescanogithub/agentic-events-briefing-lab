# Discovery

Ten questions. Each one changes the design. None of these answers are filled in for a real desk, because this repo is a personal lab.

1. Who reads the briefing, and what decision do they make in the next hour?
   If the reader is a duty editor, the output is a rundown. If the reader is a dispatcher, the gated effect is different and this lab should stay in shadow. Dispatch is not implemented.
2. What does "publish" mean in their tools?
   Mail, chat, a CMS, or a screen in a room are different effects. This repo only writes a local outbox. A new effect needs a new gate, not a prompt change.
3. Which categories are life-safety for this desk?
   The floors in `config/rubric.json` are a lab choice (for example, traffic-signal complaints are life-safety here; electrical complaints are property). A desk that disagrees changes the map, then re-runs the invariant eval. Do not keep a floor that their counsel rejects.
4. What location precision is allowed?
   This lab stores 2 decimal degrees and geohash 6 computed from those rounded values. A stricter rule means dropping coordinates entirely. A looser rule needs a written reason. Exact addresses stay out.
5. Who may approve, and how do we know it is them?
   The demo uses `simulated-editor` and labels the step SIMULATED. A real approver needs an authenticated channel. Until that exists, status `PUBLISHED` only means "local file written".
6. What is the approval window?
   A five-minute window and a next-morning window imply different queueing. No SLA is implemented. A short window would add paging; that is new scope.
7. What is the spend cap per day, and who raises it?
   Live calls refuse when estimated cost exceeds `MAX_LIVE_SPEND_USD`. Prices come from the environment. Empty prices refuse the call. A desk that will not set a cap stays on the stub.
8. Which datasets are in scope, and how fresh must they be?
   The lab uses three public NYC sets, snapshotted 2026-10-17. Adding a dataset means a new allowlist and a new privacy test, not a wider `$select`.
9. What does shadow mode have to show before a gate turns on?
   Suggested bar, not measured here: editors agree with the top of the list often enough to trust the floor, and zero unapproved sends. The synthetic rate 1.0 does not answer that.
10. What must never be automated?
    This lab's answer is: anything that leaves the machine, and anything that names a person. If a desk wants an exception, it is a new threat model, not a config flag.
