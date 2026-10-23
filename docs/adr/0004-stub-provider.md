# ADR 0004: Stub provider by default

## Status

Accepted

## Context

CI must not call a paid API. A live adapter is still useful later, behind an explicit switch.

## Decision

The stub is the default and the demo forces it. A cassette replays text for tests. The live client runs only when `LIVE_LLM=1`, a key, a base URL, a model name, and both prices are present. Prices are not hardcoded. Estimated cost above `MAX_LIVE_SPEND_USD` refuses the call. The token estimate is chars/4 and is labeled an estimate. Every trace records the leg: stub, cassette, live, or fallback.

## Consequences

Docs must not say "measured with real providers" until a real run is recorded with date, model, and command. That run has not happened.
