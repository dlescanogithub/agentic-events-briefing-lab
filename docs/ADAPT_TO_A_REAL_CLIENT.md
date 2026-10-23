# Adapt to a real client

Short version. Do not copy this lab into a newsroom and call it done.

1. Run the questions in `docs/DISCOVERY.md` with the people who own the rubric, the data, and the approval.
2. Replace the fictional desk names. Do not reuse a real client's name in this repository unless they asked for that and counsel agreed. This lab does not contain one.
3. Rebuild the category map with them. Re-run `python3 -m events_briefing eval` after every floor change. If life-safety can rank below noise, do not ship the change.
4. Ask counsel what location precision is allowed. This lab's 2 decimal degrees may be too fine or, less often, finer than they need. Exact addresses stay out.
5. Keep shadow mode until they have a disagreement log. No external effect in shadow.
6. Replace `simulated-editor` with an authenticated approver before any real publish. The local outbox is the pattern, not their channel.
7. Put prices and the spend cap in the environment. Leave the live provider off until a named person accepts the cap.
8. Write their rollback in their runbook. Deleting `out/` is only the lab's rollback.
