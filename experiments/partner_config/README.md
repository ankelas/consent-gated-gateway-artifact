# Registered partner configuration (Section 6, Table 3)

The capability documents the partners under test advertised through the ACPs registry:

- `beijing_urban.acs.json`, `beijing_rural.acs.json`, `beijing_food.acs.json`,
  `china_transport.acs.json`, `china_hotel.acs.json` — the five study partners of Table 3.
- `generic_assistant.acs.json`, `message_forwarder.acs.json` — the assistant and the forwarding
  partner used by the harness.
- `roster.json` — the roster index; `compose.yml` — the partner stack as deployed.

Not included, by design: `certs/`, `keyfiles/` and `eab/` (certificate material and the mTLS
private keys) and `llm.env` / `forwarder.env` (credentials). The partner actions recorded during
the consent experiment are in `../data/live_effects_trials.jsonl`, and the reconciliation is
`../data/live_effect_reconciliation.json`.

