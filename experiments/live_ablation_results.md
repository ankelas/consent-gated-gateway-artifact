# Live ablation results

All three ablations run against the real deployed code. Each ablation is a
staging copy under `/data/caiyizhang/ablation` with an **environment-gated
one-line patch**; the live demo instances were never modified. Every ablation
arm is paired with a control built from the *same* staging copy with the flag
off, so the contrast isolates the mechanism and not the staging environment.

## 1. no-identity (AIP sender-to-peer assertion)

Patch: `acps_sdk/aip/aip_rpc_server.py`, the `assert_sender_matches_peer` call is
skipped when `ABLATION_SKIP_IDENTITY=1`. This assertion is hard-coded and is
**not** gated by `identity_binding_enabled` in the deployment.

Test: send the same task with a `senderId` that does not match the client
certificate CN. 30 paired trials per arm.

| Arm | Port | Bypass accepted |
| --- | --- | --- |
| real partner (untouched) | 9540 | **0/30 (0%)** |
| staged control (same patched copy, flag off) | 9550 | **0/30 (0%)** |
| no-identity ablation (`ABLATION_SKIP_IDENTITY=1`) | 9551 | **30/30 (100%)** |

The staged control matching the real instance shows the staging copy itself is
behaviour-neutral.

## 2. no-dedup (event-level idempotency store)

Patch: `imessage_adapter/agent.py`, the `event_response` lookup is skipped when
`ABLATION_SKIP_DEDUP=1`. An execution log records every delivery that actually
enters processing, because the state table's primary key would collapse
duplicate rows and hide the effect.

Test: deliver the same `message_id` twice in a fresh caller/conversation,
30 pairs per arm. `ABLATION_EXEC_LOG` records every delivery that enters
processing, so the counts below come from the preserved execution logs
(`state/ctrl/exec.jsonl`, `state/nodedup/exec.jsonl`) rather than from a
per-run print.

| Arm | Port | Deliveries | Executions | Second delivery |
| --- | --- | --- | --- | --- |
| staged control | 9420 | 30 pairs | **30** (1 per pair) | 3 ms (cache hit) |
| no-dedup ablation | 9421 | 30 pairs | **60** (2 per pair) | 9 ms (re-entered processing) |

In the control log no `message_id` appears twice; in the ablation log 30
distinct `message_id` values each appear twice.

Removing the event-level dedup doubles the executions. **Important nuance:** the
second execution did not produce a duplicate side effect, because a second layer
(the conversation/task state machine) absorbed it. What this layer contributes
is preventing re-entry, not preventing a duplicate effect on its own.

## 3. no-isolation (caller/conversation partition)

Patch: `imessage_adapter/store.py`, `conversation`, `save_conversation`,
`save_pending_agent_choices`, `pending_agent_choices` and
`clear_pending_agent_choices` collapse `(caller_id, chat_guid)` to a single
`("shared","shared")` key when `ABLATION_SHARED_SESSION=1`.

Test: caller A creates a pending candidate state with a unique marker; caller B,
in a different caller and conversation, sends "select the first option and
execute". 30 pairs per arm. A leak is B's reply reflecting A's request content,
which B's own message cannot supply.

| Arm | Port | Cross-caller read |
| --- | --- | --- |
| staged control | 9420 | **0/30** |
| no-isolation ablation | 9422 | **30/30** |

Control reply: "I have not received any candidate list ...". Ablation reply:
"I understand your request: **recommend cultural attractions in Beijing urban
areas** ..." — built from the first caller's context.

## Not available

**No consent / side-effect ablation.** The forwarding Partner was removed at the
owner's request, so there is no side-effecting target on the live path. The
consent invariant can only be reported as untested live.

## Caveats

- The leak and routing decisions are extracted from the assistant's reply text
  (the adapter returns `messages`, not a structured decision record). The rule
  is stated with each table.
- Sample sizes are 30 / 10 / 8 pairs. They establish direction and mechanism
  attribution; they are not rate estimates for production traffic.
- All arms ran with `SENDER_DRY_RUN` untouched and no outbound message was sent.
