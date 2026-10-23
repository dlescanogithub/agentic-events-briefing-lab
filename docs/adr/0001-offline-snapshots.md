# ADR 0001: Offline snapshots are the default

## Status

Accepted

## Context

CI must not call the network. A demo still has to show real public rows, trimmed so they are aggregate-safe.

## Decision

`EVENTS_OFFLINE` defaults to on. Tests, evals, and `demo --offline` read `fixtures/snapshots/`. `refresh-snapshots --online` is the only SODA pull, and it is manual.

## Consequences

The committed snapshot can go stale. The manifest stores `captured_at`. A desk that needs "this morning" is in a later phase, not in CI.
