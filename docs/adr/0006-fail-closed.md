# ADR 0006: Invalid model output fails closed

## Status

Accepted

## Context

A model can return prose, extra keys, or incident ids it invented. Treating that as a briefing would hide the failure.

## Decision

The prompt carries a JSON schema. Pydantic validates the same shape. Invalid output retries up to `LLM_MAX_ATTEMPTS`, then the writer substitutes a deterministic fallback and records `model_leg=fallback`. Ids that are not in the input are dropped. If nothing usable remains, the fallback is used. Timeouts are stored on the result and logged. An empty success is not a PASS in the eval runner: a scenario that does not finish is `INCOMPLETE`.

## Consequences

The desk still gets a draft, and the trace shows it was not the model's draft. The fallback text avoids the words the publish-claim regex watches.
