# ADR 0003: Hard floors for category groups

## Status

Accepted

## Context

A weighted sum can let a fresh, severe noise row outrank an older life-safety row. The lab invariant forbids that.

## Decision

Each category group has a floor at least 1.0 apart. The within-band score is capped at 0.999. Weights live in `config/rubric.json` and must sum to 1. Ties break on score, time, then id.

## Consequences

The invariant holds by construction, which is what we want to test. It also means a desk cannot "let the weights decide" to put noise first without editing the floors and breaking the eval on purpose.
