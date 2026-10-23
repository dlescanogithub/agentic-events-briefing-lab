# Security

This is a lab repository. It is not a production service.

## Reporting

Use GitHub private vulnerability reporting ("Report a vulnerability" on the Security tab). Do not open a public gist or a public issue with a secret, a snapshot you think is too precise, or a live API key.

## Secrets

- Configuration is environment variables only. `.env.example` has empty placeholders.
- Do not commit `.env`, app tokens, or `XAI_API_KEY`.
- CI does not set vendor credentials and does not call the network from tests.
- `python -m events_briefing secretscan` is the in-repo scanner. It is a pattern check, not a full secret-management program.

## License boundary

Code in `LICENSE` is the MIT text, copyright Diego Lescano. NYC Open Data snapshots are not covered by that license. The boundary and the City terms are in `NOTICE` and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Data

Snapshots are trimmed public NYC Open Data fields. Exact addresses, names, phone numbers, and free-text descriptions are not stored. Coordinates in committed snapshots are rounded to 2 decimal degrees before write. If you run `refresh-snapshots`, review the new files before committing them.

## Effects

Publish writes a local outbox directory only. There is no email, chat, or dispatch integration. The demo step is an approval gate (simulated actor): an HMAC from `APPROVAL_STATE_KEY`, bound to the program id, a one-time nonce, and the nonce-ledger head, plus an allowlist. Deleting the ledger fails closed when program state exists. Restoring the ledger together with an old APPROVED file still republishes. It is not an authenticated channel. The value `lab-simulated-not-a-secret` is a public lab fixture. Rotate it. `briefing` refuses that value. Demo and eval may use it when the variable is unset. Sensitive categories are left out of the public briefing and the map.

## Known limits

The secret scanner and the publish-claim checker are regex-style. Their recall is not measured. A clean scan is not a proof that no secret exists.
