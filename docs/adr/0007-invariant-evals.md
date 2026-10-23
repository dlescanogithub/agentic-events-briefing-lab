# ADR 0007: Invariant evals, not trajectories

## Status

Accepted

## Context

Exact tool-call traces break when a prompt is reworded and do not state the property we care about.

## Decision

Scenarios check properties: life-safety above noise, stable order, stable ties, cost within cap, no unapproved publish, no external side effect, invalid model output fails closed, and a planted publish claim is flagged when the outbox is empty. PASS requires a completed check and a non-empty detail. A thrown exception is INCOMPLETE. A separate command ranks with a broken sorter and must exit 1. CI fails if that command does not exit 1.

## Consequences

We can change the stub's wording without rewriting the eval. We cannot claim nDCG. Regex recall stays unmeasured, so the claim detector is a tripwire, not a proof.
