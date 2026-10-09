# Implementation evidence map (internal research note)

This file records which remote artifacts support the manuscript's architecture claims. It is not intended for direct publication.

| Paper module | Remote artifact | Evidence used in the draft |
| --- | --- | --- |
| M1 ingress authentication | `/data/imessage/photon-bridge.mjs` | Timestamped Spectrum HMAC verification, inbound event filtering, quick acknowledgement, asynchronous routing |
| M1/M2 loopback boundary | `/data/imessage/src/imessage_adapter/app.py` | `/v1/photon/inbound`, internal-token check, caller derived from verified Photon sender identifier |
| M2 session isolation | `/data/imessage/src/imessage_adapter/config.py`, `store.py` | `photon:<sender_id>` namespace; caller/chat keyed state and history |
| M3 discovery | `/data/imessage/src/imessage_adapter/agent.py`, `src/acps_directory.py` | Structured `selected_combination`; exact filtered lookup by `skills.tags` for personal assistants |
| M4 consent | `/data/imessage/src/imessage_adapter/agent.py` | Candidate list is persisted; target execution requires explicit selection and concrete instruction |
| M5 identity-bound execution | `/data/imessage/src/imessage_adapter/agent.py`, `.env.example` | HTTPS `/rpc` and JSONRPC/AIPRPC filtering; AIC expectation; mTLS client context |
| M5 protocol state | `/data/imessage/src/imessage_adapter/agent.py` | Explicit AIP v2.2 transition table; `start`, `get`, `continue`, `complete`, `cancel` |
| M6 state and recovery | `/data/imessage/src/imessage_adapter/store.py`, `agent.py` | SQLite event response, conversation, pending choices, and task-context state; process-local SDK task manager boundary |
| M7 delivery | `/data/imessage/photon-bridge.mjs`, `imessage-sender.mjs` | Result conversion and Photon/iMessage outbound message path |
| ACPs application instance | `/data/imessage/acs/imessage-leader.acs.json` | Protocol version 02.02, iMessage Leader identity, JSON-RPC endpoint and mTLS declaration |
| ACPs Partner instance | `/data/imessage/acs/message-forwarder.acs.json`, `hermes-adapter/README.md` | Single-skill forwarding Partner, allowlist policy, AIP task lifecycle, mTLS termination |

## Existing verification evidence

The remote project already contains unit, end-to-end, and smoke tests for caller isolation, duplicate handling, structured discovery, endpoint filtering, AIP state transitions, forwarding allowlists, and personal-assistant routing. The paper should cite these as implementation checks, then add the controlled simulator and fault-injection results as the scientific evaluation.

The remote deployment also contains runtime state and message history. Those files are operational data and must not be copied into the paper repository or experiment artifact. The paper uses synthetic or de-identified workloads.
