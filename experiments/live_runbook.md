# Live experiment runbook

`live_experiment_plan.md` states the design. This file is the operational plan:
what to run, in what order, behind which gates, and what each stage can support.
Nothing in stage 1 or later may run until every gate in section 1 is signed off.

## 0. What this host can actually run

Inventory taken 2026-10-06; all containers healthy.

| Path | Real components | Determinism | Side effects | Can support |
| --- | --- | --- | --- | --- |
| P1 local ACPs demo | `caiyizhang-acps-leader` (127.0.0.1:19520 → 9031; web 9522 → 9030), `caiyizhang-acps-partner` (127.0.0.1:19521 → 9024), `caiyizhang-acps-llm-demo` stub at `http://llm-demo:9199/v1`, registry 9002, discovery 9005, CA 9003, mq-auth 9007, mTLS edge `caiyizhang-acps-prereg-gateway` (9520/9521) | Deterministic (stub model) | None | Routing, protocol completion, identity/endpoint rejection, replay, isolation, per-stage latency |
| P3 iMessage, user A | `assistant-a` (owner A), `imessage-agent-1` (127.0.0.1:9410), `imessage-photon-bridge-1` (127.0.0.1:9411), `imessage-sender`, `stage-nginx` (127.0.0.1:8443) | Non-deterministic | **Sends real messages** | The paper's actual ingress → consent → delivery pipeline, and the whole main suite |
| P3b dedicated cells, user B | `assistant-b` (owner B, separate AIC and TLS port 9532) | Non-deterministic | **Sends real messages** | Cross-caller isolation and two-hop A→B forwarding only |
| P4 AMQP group | `stage-rabbitmq` (5671), mq-auth 9007, `e2e_group.py` template | Non-deterministic | None | Group-mode interaction, multi-Partner fan-out |

P1 and P4 are usable today with no configuration change. P3 is the only path
that supports a claim about real ingress and delivery: it can run in dry-run
once G2's dry-run step is applied, and real delivery stays blocked until G2 is
signed off.

The Hermes partner path was dropped on 2026-10-06. It was the only path backed
by a real LLM, but it exercises no part of the claim set: the adapter is a CLI
bridge, not the typed-judgment layer, and it is non-deterministic at 20–120 s
per task, which made it the wall-clock bottleneck. Real end-to-end latency now
comes from P3 through the actual pipeline, and model behaviour is measured
separately by the judgment study.

### Current safety state of P3 (checked 2026-10-06)

- `imessage-sender` has a real dry-run switch, `SENDER_DRY_RUN`, but it is **not
  set**, so `dryRun` is `false` and the sender is **armed for real sends**.
- The forwarding allowlist exists as `FORWARDER_ALLOWED_NUMBERS` and currently
  holds **2 entries**. The numbers were not printed; the owner must confirm they
  are the intended test recipients.
- `FORWARDER_IDENTITY_BINDING_ENABLED=true` on the forwarder, but
  `AIP_SERVER_IDENTITY_BINDING_ENABLED=false` on the agent server, and both
  demo configs (`acps-public-demo/{leader,partner}-config.toml`) set
  `identity_binding_enabled = false`.

Consequence: the sender must be put into dry-run before Stage 1, and the
identity-binding decision (G1) is not uniform across components today.

How to set the dry-run flag (checked 2026-10-06): `docker-compose.forwarder.yml`
defines an `imessage-sender` service, but the **running container was not
created by compose v2** — it has no `com.docker.compose.project.config_files`
or `working_dir` label and is named `/imessage-sender` rather than
`imessage-<service>-1`. A plain `docker compose up -d imessage-sender` would
therefore create a second container and collide on port 9425. The safe
procedure is a reversible rename-and-replace:

1. `docker rename imessage-sender imessage-sender.live-backup && docker stop imessage-sender.live-backup`
2. start a replacement with the same image, env-file, network, mounts and
   `SENDER_DRY_RUN=true` (all recoverable from `docker inspect`);
3. confirm `GET /health` reports `dryRun: true`;
4. rollback is `docker rm -f <replacement> && docker rename imessage-sender.live-backup imessage-sender && docker start imessage-sender`.

The `message-forwarder` container that consumes the sender is not currently
running, so nothing else depends on it during the switch.

### Evaluation scope: paired cells, not a balanced suite

`assistant-a` and `assistant-b` are two different users, not two instances of
one: they carry different AICs, different certificates, different TLS ports
(9531/9532), and different owner numbers. The allowlist holds exactly those two
numbers.

Decision (2026-10-06, revised with the redesign in `live_experiment_plan.md`):
the live work is organized as paired fault-injection cells rather than a balanced
message suite, so who carries what is decided per cell.

- User A carries I1, I3, I4, I6, E2 and E4.
- User B appears only in the I5 cross-caller isolation cells, where a second
  caller is the fault condition and cannot be simulated away.
- The A → B two-hop path is optional. It illustrates the mapping in Sect. 8.4
  but supports no current hypothesis, so it runs only if that description stays
  in the paper.

Consequences: B's real-message volume is bounded by the I5 cells; B still needs
informed consent because those cells deliver to a real phone; the allowlist
stays at two entries.

## 1. Gates

| Gate | Requirement | Why |
| --- | --- | --- |
| G1 | **Largely resolved by measurement (2026-10-06).** The identity check held with `identity_binding_enabled = false`: 120/120 mismatched `senderId` attempts were rejected with `-32009`, so the flag does not gate the check. What remains is to attribute the check to a component (edge, SDK, or application) rather than to flip a switch. | The original premise — that binding had to be enabled to test the invariant — was wrong, and the plan no longer relies on a config ablation. |
| G2 | Confirm the 2 `FORWARDER_ALLOWED_NUMBERS` entries are the intended test recipients; set `SENDER_DRY_RUN=true` for Stage 1 and every ablation; only clear it for Stage 2 after the allowlist is confirmed and a non-allowlisted number is shown to be rejected. | The sender is currently armed (no `SENDER_DRY_RUN`), so an unguarded run sends real messages to real people. |
| G3 | Message suite frozen; two annotators staffed and the adjudication rule fixed (see `annotation_protocol.md`). | Labels must be independent of the generator. |
| G4 | Telemetry sink reachable and a run manifest written (VictoriaMetrics 8428, ClickHouse 8123, Postgres 15433 are all up). | Without real timestamps the latency claims are modellable only. |
| G5 | A single kill switch that stops the driver and drains in-flight tasks, plus a recorded source revision and cert fingerprint per agent. | An unattended run must be stoppable. |

## 2. What to record per task

Every attempt writes one row, whether it succeeds, fails, or is rejected:

```text
run_id, arm, path, scenario_card, message_hash, generator_model, temperature
ingress_verified, caller_hash, chat_hash
discovery_candidate_count, selected_aic, label_aic, route_correct
consent_required, consent_requested, consent_supplied, side_effect_attempted
endpoint_ok, aic_ok, mtls_ok, identity_check_result
task_id, state_sequence, terminal_state, failure_category, retry_count
replay_key, side_effect_count, cross_session_access
t_ingress, t_discovery, t_rpc, t_poll, t_delivery, latency_total_ms
```

Raw message text stays in a protected local review set and is hashed in the
artifact. No phone number, token, key, or certificate body is written.

## 3. Stages

### Stage 0 — preflight, no traffic

1. Record identity for every agent under test: ACS file, AIC, protocol version,
   endpoint, certificate fingerprint, image digest.
   `docker inspect --format '{{.Image}}' caiyizhang-acps-leader caiyizhang-acps-partner`
2. Verify the registry returns the agents and discovery returns their candidates.
3. Verify mTLS on the Leader--Partner path with the existing client material
   (`acps-upgrade-20260924/mq-e2e-20260928/keyfiles/`) and the pattern in
   `direct_rpc_check.py`; `experiments/live/preflight.py` records the handshake
   and peer CN for every endpoint under test.
4. Record G1's decision and, if binding is enabled, verify that a certificate
   whose CN does not match the advertised AIC is rejected before any task runs.
5. Confirm G2 and G5 in writing; install the kill switch; dry-run it.

Exit criterion: all five items recorded in a signed run manifest.

### Stage 1 — cell pilot, N = 30 per cell, sink destination

Run every E1 cell with 30 paired trials on the local demo, plus I1/I3/I4 on the
real ingress with `SENDER_DRY_RUN=true`. The purpose is not effect size: it is
to confirm that each injected fault actually reaches the module that owns it,
that the clean side of each pair behaves, and that the runner's guards hold.
The message suite is the carrier for the cells, not the object of study.

Exit criterion: < 5% invalid messages, no unexpected recipient, no unbounded
retry, and a usable latency distribution.

### Stage 2 — confirmatory cells

N = 100 paired trials per E1 cell, same cells as the pilot, full configuration.
No cell has a configuration switch that removes its protection (see G1), so the
confirmatory run measures enforcement; the ablation contrasts stay in the
synthetic study, which is labelled as mechanism-level.

### Stage 3 — overhead, human labels, delivery smoke

- **E2 overhead**: 100 paired messages, full path versus reduced path, with
  per-stage timestamps. This is the live evidence for H4.
- **E3 labels**: 100-150 items human-adjudicated per `annotation_protocol.md`,
  then re-run the judgment harness on those labels. This removes the paper's
  generator-label caveat for the judgment layer.
- **E4 smoke**: 20 real deliveries to user A plus whatever the I5 cells
  require. Not a rate measurement; it shows the ingress-to-delivery leg works
  and that the allowlist rejects a non-allowlisted recipient.

### Stage 4 — analysis and paper integration

Compute, per metric in `metrics.md`: binary rates with 95% Wilson intervals,
paired Full-vs-ablation contrasts, one-sided 3/N upper bounds for zero observed
events, and p50/p95 latency per stage. The live study becomes the primary
evaluation; the 20,000-row synthetic study is reported separately as a
mechanism regression.

## 4. Sizing and budget

| Work | N (confirmatory) | Cost per task | Notes |
| --- | --- | --- | --- |
| P1 cells I1-I6 | 100 paired per cell | seconds | deterministic demo, no side effects |
| P3 dry-run cells I1, I3, I4 | 100 paired per cell | seconds | real ingress, no sends |
| I5 isolation cells | 100 | seconds | user A and user B; B receives only what I5 requires |
| E2 overhead | 100 paired | seconds | full path vs reduced path |
| E3 human labels | 100-150 items | annotator time | no compute beyond one judgment run |
| E4 smoke | 20 + I5 deliveries | seconds | real sends, allowlisted |

Total is roughly 600-800 live tasks, most of them on the local demo and the
dry-run ingress, instead of 1,000+ real messages. Fewer real messages, more of
the paper's claims actually covered.

A zero-event count is bounded by 3/N: N = 30 → < 10%, N = 100 → < 3%,
N = 300 → < 1%. Size each cell against the bound the paper will state, and
print that bound next to every zero.

## 5. Safety and stopping rules

- P3 only: test accounts, allowlisted recipients, non-sensitive text, sink or
  dry-run destination for every side-effecting task.
- Stop the run immediately on any unexpected recipient, any certificate
  mismatch outside the planned fault arm, an unbounded retry loop, or evidence
  that a non-test account can receive a message.
- Ablations never touch the production iMessage sender.
- Operational history, raw text, and identifiers stay out of the paper artifact.

## 6. Claim mapping

| Paper claim | Live cell | Still not supported |
| --- | --- | --- |
| H1 controlled delegation | I1 routing cells, I3 consent cells | Production traffic at scale |
| H2 authorization safety | I1 ingress integrity, I2 identity binding (enforcement measurement) | Other platforms |
| H3 isolation and idempotency | I4 replay, I5 cross-caller and cross-chat isolation | More than the two test accounts |
| H4 bounded overhead | E2 real per-stage and total latency, paired | Host contention outside this deployment |
| Ingress → delivery works | E4 delivery smoke | Delivery rate at scale |
| Judgment calibration on real inputs | E3 human-adjudicated labels | Model-family generality (one model) |
| Two-hop / multi-hop forwarding | optional cell, supports no hypothesis | Not a paper claim |

## 7. Decisions needed from the owner before Stage 1

1. Confirm that the two `FORWARDER_ALLOWED_NUMBERS` entries are exactly user A
   and user B, and obtain user B's informed consent for the I5 isolation cells
   (and for the optional two-hop cell if it is kept).
2. Do we enable identity binding for the live arm (G1), and is a certificate
   with the matching CN available for every agent under test?
3. Who are the two annotators, and what is the adjudication timeline?
