# Ablation arms (invariant ablations, Section 9.2 / Table 5)

Staging copies of the deployed code used for the three paired ablation arms. Each arm differs
from its same-code control by one environment-gated change; the raw records produced from them
are in `../data/live_ablation_{identity,dedup,isolation}.jsonl`, and the reported outcomes are
in `../live_ablation_results.md`.

| Arm | Flag | Ports (arm / control / live) | The one change |
| --- | --- | --- | --- |
| no-identity | `ABLATION_SKIP_IDENTITY=1` | 9551 / 9550 / 9540 | `sdk/acps_sdk/aip/aip_rpc_server.py` drops the sender-to-peer assertion, so a mismatched identity is accepted |
| no-dedup | `ABLATION_SKIP_DEDUP=1` | 9421 / 9420 | `assistant/imessage_adapter/agent.py` drops the event-level response lookup, so a redelivered event re-enters processing |
| no-isolation | `ABLATION_SHARED_SESSION=1` | 9422 / 9420 | `assistant/imessage_adapter/store.py` collapses the caller–conversation key to one shared namespace |

Contents:

- `compose.yml` — the partner-side arm (identity) and its same-code control.
- `compose-adapter.yml` — the adapter-side arms (dedup, isolation) and their shared control.
- `assistant/` — the adapter source mounted as `/data/imessage/src`; carries the two adapter-side
  gates and the host-name-verification change described in Section 9.4. It is the study revision
  and predates the advisory J5 patch, which is in `../live/adapter_patch/`.
- `sdk/` — the ACPs SDK source; carries the `ABLATION_SKIP_IDENTITY` gate.
- `partner/` — the partner runtime source.
- `runtime/` — the per-arm `config.toml` and `acs.json` overrides.

Not included, by design: `state/` (SQLite runtime state), `logs/` (the partner's AMP logs),
every `*.key` / `*.pem` / `*.crt`, and the host `.env` files. Paths inside the compose files are
absolute and are the paths as run on the study host.

