# Real-agent evaluation protocol (v1, superseded)

> Superseded on 2026-10-06 by `live_experiment_plan.md`. Retained for provenance.

> Operational stages, gates and commands: [`live_runbook.md`](live_runbook.md).

The synthetic gateway study remains a deterministic mechanism regression test. The primary paper experiment should exercise the registered ACPs agents and their real AIP v2.2 RPC paths with model-generated user messages.

## Evaluated paths

The initial live study uses only registered, controlled agents:

1. iMessage Leader (user A): discovery and user-confirmation path through Photon; carries the whole main suite.
2. Message-forwarder Partner (user A): single-skill forwarding through the allowlisted test sender.
3. Local ACPs Leader--Partner demo: deterministic AIP `start`/`get`/`complete` against the stub model, for protocol and fault mechanics.
4. ACPs group mode (optional): group session creation and multi-Partner fan-out.

Personal-assistant A -> personal-assistant B carries user B and is therefore restricted to the dedicated cross-caller isolation and two-hop cell families; it is not part of the main balanced suite.

The Hermes partner path was dropped on 2026-10-06. It is backed by a real LLM but exercises none of the claim set, and at 20-120 s per task it was the wall-clock bottleneck. Real end-to-end latency comes from the iMessage path instead, and model behaviour is measured by the judgment study.

The ACS file, AIC, protocol version, endpoint, certificate fingerprint, and source revision are recorded for every run. Private keys, tokens, phone numbers, and raw message bodies are excluded from the publication artifact.

## Message generation and labels

The generator model produces paraphrases from a fixed scenario card. A card contains the intended target skill, whether an external side effect is intended, the required consent state, the expected candidate set, and the expected final protocol state. The generator is not the evaluator. Each generated message is checked by two human annotators against the card; disagreements are adjudicated before the item enters the held-out set.

The message suite contains four families:

- direct capability requests;
- ambiguous requests that should cause candidate presentation or clarification;
- side-effecting requests that require explicit consent;
- adversarial or quoted instruction content that must not change gateway policy.

Each family includes paraphrases, negations, indirect references, benign quoted injection phrases, repeated requests with a new event key, and genuine replay events with the same key. The model, temperature, prompt hash, scenario-card identifier, and generated-message hash are recorded.

## Arms and causal comparisons

The main arm is the full gateway connected to the real registered agents. Three controlled ablations run against the same agent registry and message suite:

- no-consent: the gateway sends a side-effecting task without the confirmation transition, but the destination is a sink or an allowlisted test account;
- no-identity: a replay proxy presents an incorrect AIC or endpoint while the target service remains unchanged;
- no-dedup/isolation: the same authenticated event is replayed or delivered under a second test session through a staging proxy.

The ablations are implemented in a staging gateway or protocol proxy. The production iMessage sender and non-test recipients are never used by an ablation.

## Minimum run size

The main suite uses only user A: three paths (iMessage Leader, message-forwarder Partner, local ACPs demo), ten scenario cards per path, and five model-generated paraphrases per card, giving a 150-item pilot. A further two dedicated cell families carry user B: cross-caller isolation (A vs B) and two-hop forwarding (A -> assistant A -> assistant B -> Partner -> B), ten cards each with two paraphrases, giving a 40-item pilot block. Use the pilot to estimate invalid-message, routing, and live-failure rates.

The confirmatory run should contain at least 1,000 held-out messages for user A, balanced by path and scenario family, with each fault condition repeated at least 25 times. Size the C1/C2 blocks separately against the one-sided 3/N bound the paper will state (at least 100 each). Increase repetitions after the pilot if the Wilson interval for a primary rate is wider than 5 percentage points, and keep B's message volume inside C1/C2 so the number of real deliveries to a second person stays bounded.

## Measurements

For every run, record:

- discovery candidates, selected AIC, and whether the selected target matches the human label;
- consent requested, consent supplied, and whether an external side effect was attempted;
- TLS/AIC/endpoint verification and AIP state transitions;
- task start/get/continue/complete/cancel outcomes;
- replay key, side-effect count, cross-session access result, and recovery;
- real elapsed latency for ingress, discovery, RPC, polling, and delivery;
- model-generation and gateway decision metadata, with text stored only in a protected local review set.

Primary endpoints are correct routing, unauthorized side-effect attempts, identity-bypass acceptance, cross-session leakage, duplicate side effects, protocol completion, safe rejection, and p95 end-to-end latency. Report Wilson intervals for binary rates and paired contrasts because every arm reuses the same message and scenario card.

## Safety and stopping rules

The first live run uses only test accounts, a test allowlist, non-sensitive text, and a dry-run or sink destination for all side-effecting tasks. Stop the run on any unexpected recipient, certificate mismatch outside the planned fault arm, unbounded retry loop, or evidence that a non-test account can receive a message. No raw operational history is copied into the paper repository.

## Paper integration

The live study becomes the primary evaluation in the paper. The current 20,000-row synthetic study is retained as a reproducible mechanism regression and is reported separately. Claims about production risk, general model quality, or deployment performance are made only from the live study after human label adjudication and a second-model or placement comparison.
