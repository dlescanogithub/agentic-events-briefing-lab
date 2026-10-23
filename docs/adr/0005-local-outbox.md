# ADR 0005: Local outbox and simulated approval

## Status

Accepted

## Context

A briefing that can send itself is the failure mode the gate exists to prevent. A real identity provider is out of scope for this lab.

## Decision

States are `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `PUBLISHED`. Only `APPROVED` may publish. Publish writes `out/outbox/` and nothing else. The demo approves as `simulated-editor` and prints SIMULATED. Program ids are restricted to a safe filename pattern.

The step is an approval gate (simulated actor). Each state file carries an HMAC (`APPROVAL_STATE_KEY` from the environment). The signature covers the program id, the approved segments, a one-time nonce, and the head of the signed nonce ledger. Load rejects a file whose signed id does not match the path. Load also rejects a missing ledger when program state exists, and a ledger whose own HMAC does not verify. Publish consumes the nonce. Deleting the ledger and restoring an old APPROVED file does not publish again. A tampered state file or a tampered ledger is rejected. The actor must be non-empty and listed in `config/approvers.json`. Passing `simulated=False` is refused, because this lab has no authenticated channel. The lab fixture key is public. Demo and eval may use it when the variable is unset. `briefing` refuses it. Rotate the key before any non-demo run.

## Consequences

`PUBLISHED` in this repo means a local file exists. It does not mean a person with an account approved it. Anyone who has the signing key and a listed actor name can sign a state file. The public lab fixture must be rotated; using it outside demo mode fails. Restoring the nonce ledger together with the old APPROVED file is not stopped, because the same key signs both. Production approval stays design-only and needs an authenticated channel.
