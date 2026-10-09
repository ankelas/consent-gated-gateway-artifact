# Real-agent evaluation protocol (redesign, 2026-10-06)

> Operational stages, gates and commands: [`live_runbook.md`](live_runbook.md).
> The superseded v1 protocol is retained as `live_experiment_plan_v1.md`.

## 1. Why this is a redesign, not a scale-up

The paper's four hypotheses (H1 controlled delegation, H2 authorization safety,
H3 isolation and idempotency, H4 bounded overhead) are currently supported only
by the synthetic harness. The paper says so itself: the harness "demonstrates
the encoded control mechanisms, not production failure probabilities", and
sections 8.3, 11 and 12.3 name the open items as live protocol latency,
throughput, hosted-versus-self-hosted placement, human-adjudicated labels, and
"live iMessage/ACPs replay".

The v1 protocol answered that with 1,000+ paraphrased user messages spread
across paths. That mostly re-measures **routing under a synthetic workload**,
which is the one thing the synthetic study already covers, while leaving every
item the paper names as open still open. It is also the most expensive
configuration to run.

The redesign inverts the priority: the live study exists to answer the three
questions the synthetic study *cannot*.

| # | Question the synthetic study cannot answer | Live instrument |
| --- | --- | --- |
| Q1 | Does the deployed code actually enforce the four invariants? | E1 invariant fault injection, with a config-level ablation where the deployment allows one |
| Q2 | What does the safety path cost in real elapsed time? | E2 per-stage timing, full path versus reduced path |
| Q3 | How good is the judgment layer on human-adjudicated input? | E3 human labels on the live message set |

Plus E4, a small delivery smoke, because "the message actually arrives" is a
claim no dry run can support.

## 2. Claim to evidence map

| Paper claim | Synthetic study | Live addition |
| --- | --- | --- |
| H1 controlled delegation | full | E1-I3 consent cells, E1-I1 routing cells |
| H2 authorization safety | full | E1-I1 ingress integrity, E1-I2 identity binding |
| H3 isolation and idempotency | full | E1-I4 replay, E1-I5 cross-caller/cross-chat isolation |
| H4 bounded overhead | cost model only | E2 real latency and protocol overhead |
| Judgment calibration (Sec. 12.4) | generator labels | E3 human-adjudicated labels on real inputs |
| Ingress to delivery works | not claimed | E4 delivery smoke, in dry-run for everything else |

Rows that stay synthetic are stated as such; the paper does not need a live
number for a claim it already scopes to the mechanism study.

## 3. E1 -- invariant fault injection on the live gateway

Each cell is a paired comparison: the same message and scenario card run once
clean and once with a fault injected, so the contrast is within-item. A cell is
run on the local deterministic demo (P1) for protocol mechanics and on the real
iMessage ingress (P3) where the ingress or delivery path is part of the claim.

| Cell | Fault injected | Expected under Full | Ablation lever | Primary outcome |
| --- | --- | --- | --- | --- |
| I1 ingress integrity | tampered/absent webhook signature, malformed event | rejected before discovery | none (shared control) | reject rate; no candidate lookup after reject |
| I2 identity binding | `senderId` differs from the certificate CN (four variants), or endpoint outside policy | rejected before execution | none: measured 2026-10-06, the check is active even with `identity_binding_enabled = false` | identity-bypass acceptance rate |
| I3 consent gate | side-effecting request with no prior confirmation | no side effect attempted | none available in config; measured observationally | unauthorized side-effect attempts |
| I4 idempotency | same `clientRequestId` replayed k times | exactly one effect | replay with a new key but identical text (the mechanism gap) | duplicate effect count |
| I5 isolation | session B reads or acts on session A's pending state | no cross-context access | second chat (same user) versus second caller (user B) | cross-context access rate |
| I6 recovery | downstream timeout, then restart | classified retry, one effect | none | recovery rate, duplicate count |

**No cell exposes a configuration switch that removes its protection.** The
first I2 run showed the identity check holding with `identity_binding_enabled =
false` (120/120 rejections, `-32009`), consistent with a separate authorization
check that the flag does not disable; consent and deduplication are not
configurable either. The live study therefore measures *enforcement*, and the
ablation evidence stays where it belongs: in the synthetic study, which is
already labelled as mechanism-level. This is stated in the paper rather than
implying live ablations that do not exist. Characterising which component
performs the identity check (edge, SDK, or application) is the remaining useful
question for that cell.

## 4. E2 -- real overhead

Run the same messages twice: once through the full gateway path, once through a
reduced path (direct Partner RPC without Leader orchestration and without the
consent transition). Record `t_ingress`, `t_discovery`, `t_rpc`, `t_poll`,
`t_delivery` and the total, then report p50/p95 and the paired difference with a
bootstrap interval. This replaces the synthetic per-step cost model where the
paper currently has only cost units, and it is what H4 needs.

## 5. E3 -- human-adjudicated judgment labels

Sample the messages that actually traverse the live cells plus a set of
realistic user requests, and label them with two annotators and adjudication per
`annotation_protocol.md`. Re-run the judgment harness on the human-labeled
subset and report accuracy, Brier, ECE, coverage and residual error against
human labels. This is the single change that removes the paper's "generator
labels" caveat for the judgment layer; it needs no new infrastructure, only
annotator time.

## 6. E4 -- delivery smoke

A small bounded set of real sends to user A (target 20), plus the deliveries
that I5 already requires for user B. Purpose is to show the ingress-to-delivery
leg works end to end and that the allowlist rejects a non-allowlisted
recipient. It is not a rate measurement and is reported separately from E1.

## 7. Paths and where each cell runs

| Path | Carries | Side effects |
| --- | --- | --- |
| P1 local demo (Leader REST, Partner AIP) | I1-I6 mechanics, E2 | none |
| P3 iMessage, user A | I1, I3, I4, E2, E4 on the real ingress and delivery | dry-run except E4 |
| P3b user B | I5 cross-caller cells only | dry-run except the deliveries I5 requires |
| P4 AMQP group (optional) | not required by any current claim | none |

## 8. Sizing and power

The live study does not estimate production rates; it bounds them. For a cell
with no observed event, the one-sided 95% upper bound is approximately 3/N:

| N per cell | Upper bound on the observed zero rate |
| --- | --- |
| 30 | < 10% |
| 100 | < 3% |
| 300 | < 1% |

Default is N = 30 per cell for the pilot and N = 100 for the confirmatory run
(< 3%), with the bound stated next to each zero count. Cells are paired, so the
contrast uses the same message on both sides. E2 uses N = 100 paired messages;
E3 targets 100-150 human-labeled items; E4 is 20 deliveries plus the I5 cells
and is not a rate.

This is roughly 600-800 live tasks in the confirmatory run, most of them on the
local demo and the dry-run iMessage path, instead of 1,000+ real ingress
messages. Fewer real messages, more of the claims actually covered.

## 9. Safety

- Side-effecting cells run with `SENDER_DRY_RUN=true`; the runner refuses a
  suite with side-effecting cards otherwise, on any path, because P1 can also
  route to the forwarding Partner.
- Real deliveries happen only in E4 and the I5 cells, only to allowlisted test
  recipients, and only after the allowlist is verified and consent obtained.
- Stop on any unexpected recipient, certificate mismatch outside the planned
  fault arm, unbounded retry, or evidence a non-test account can receive a
  message. Ablations never touch the production sender.

## 10. Analysis

Wilson intervals for binary rates; the 3/N bound for every zero count; paired
contrasts within message; bootstrap intervals for latency differences; per-stage
latency percentiles. Rows carry the card label, fault arm, path, and run id.

## 11. Paper integration

| Paper location | Change after the live study |
| --- | --- |
| Sec. 8.4 | replace "no live measurement is claimed" with the E1-E4 design and scope |
| Sec. 9 | keep the metric definitions; the live numbers use them directly |
| Sec. 11 | drop "live replay is future work"; keep synthetic-only limits explicit |
| Sec. 12.1-12.2 | unchanged, still labeled simulator outcomes |
| Sec. 12.4 | re-report against human labels (E3) |
| new Sec. 12.5 | live invariant evidence, plus E2 latency and the E4 smoke |
| Sec. 13 | state which claims are now live-backed and which remain synthetic |

## 12. Out of scope

Production traffic at scale, other messaging platforms, throughput and resource
contention, model-family generality, and hosted-versus-self-hosted placement are
not added by this redesign. They are named in the paper as future work and would
each need their own instrument.
