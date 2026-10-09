# Live results log

Append-only record of live cells. Nothing here is a production-risk estimate;
zero counts are reported with their one-sided 95% upper bound (approximately
3/N).

## I1 -- ingress integrity, 2026-10-06

Path: local ACPs demo Leader (`https://127.0.0.1:9520/api/v1`), mTLS edge.
Design: 30 paired items; each item runs one clean submit and four faults.

| Arm | n | As expected | 95% CI | Sessions created |
| --- | --- | --- | --- | --- |
| control (valid submit) | 30 | 30 | [0.886, 1.000] | 30 |
| no client certificate | 30 | 30 (400, mTLS edge) | [0.886, 1.000] | 0 |
| malformed JSON body | 30 | 30 (422, validation) | [0.886, 1.000] | 0 |
| missing required fields | 30 | 30 (422, validation) | [0.886, 1.000] | 0 |
| unknown session reference | 30 | 30 (404, application) | [0.886, 1.000] | 0 |

Control latency: p50 = 1016 ms, p95 = 1022 ms (includes Partner orchestration).
The observation that matters is the last column: every rejected request was
rejected before any session or task state existed.

Scope note: this entry point has no webhook HMAC check — that lives in the
Photon bridge on the real ingress. I1 therefore covers transport and request
validation faults here, and the webhook-signature fault belongs to the P3 cells.

## I2 -- identity binding, 2026-10-06

Path: live AIP Partner (`https://127.0.0.1:9521/rpc`), client certificate = the
Leader identity. Fault: the declared `senderId` is varied while the certificate
stays the Leader's. 30 paired items, four fault variants each.

| Arm | n | Accepted | 95% CI |
| --- | --- | --- | --- |
| control (senderId == certificate CN) | 30 | 30 | [0.886, 1.000] |
| different but valid AIC | 30 | 0 | [0.000, 0.114] |
| forged AIC | 30 | 0 | [0.000, 0.114] |
| empty senderId | 30 | 0 | [0.000, 0.114] |
| non-AIC string | 30 | 0 | [0.000, 0.114] |

All 120 fault attempts returned `-32009 AuthorizationFailedError`; zero were
executed, so the one-sided upper bound on identity-bypass acceptance is
**< 2.5%**.

### Finding: the config flag does not gate this check

`acps-public-demo/partner-config.toml` sets `identity_binding_enabled = false`,
yet the mismatch is rejected. **The deployed AIP path enforces
`senderId == certificate CN` through a separate authorization check that the
flag does not disable.** Consequences:

1. The planned "no-identity ablation" (flip the flag) cannot remove this
   protection, so I2 measures *enforcement* rather than an ablation. That is
   stronger live evidence for H2, but the design's claim that I2 is "the one
   real config ablation" is withdrawn.
2. Gate G1 in the runbook is largely moot for this path: the invariant holds
   without config changes. What remains worth doing is characterising *which*
   component performs the check (edge, SDK, or application) so the paper can
   attribute it correctly.
3. `senderRole` is not part of the check: declaring role `partner` with the
   correct certificate is accepted. The identity invariant covers asserted
   identifiers, not role labels.

### Limitations

Both cells ran on the local demo path. They show that the deployed code
enforces the transport, validation, and identity checks on that path; they do
not speak to the iMessage ingress (P3) or to production traffic. N = 30 per arm
supports a < 10% bound per arm and < 2.5% on the pooled 120 fault attempts, not
a point estimate.

## I4 -- idempotency on the real ingress, 2026-10-06

Instrument: the adapter's inbound endpoint is driven directly with an internal
token, so the real gateway pipeline runs and the reply comes back as JSON.
Nothing is sent. Each of 30 items used a fresh caller and conversation, and
delivered the same `message_id` twice.

Ground truth is the adapter's own store, not latency:
`inbound_events_v2` has `PRIMARY KEY (caller_id, message_id)`.

| Observation | Result |
| --- | --- |
| stored rows for the replayed key | **1** in 30/30 items |
| duplicate executions | **0/30** (upper bound < 10%) |
| fresh / first replay / second replay latency | 9.6 / 9.2 / 2.8 ms median |

### Method correction

An earlier run of this cell reported deduplication from latency alone
(5465 ms → 5 ms). That interpretation is **withdrawn**. Two confounds were found
by inspection:

1. The adapter caches a reply per conversation, so a second message in the same
   conversation returns instantly even when its `message_id` is new. The first
   run reused one caller, so the timing signal was the conversation cache.
2. The adapter normalizes the caller to `photon:<sender id>`, so a lookup keyed
   on the raw number returns zero rows and looks like "nothing stored".

After the fixes, the row count is the instrument and the result is unambiguous:
30 repeated deliveries produced exactly one stored record each, and the table
has no duplicate `(caller_id, message_id)` group at all.

## I5 -- cross-caller isolation, 2026-10-06

Design: caller A creates a pending candidate state in its own conversation,
then caller B, in a different conversation, sends "select the first option and
execute". 30 paired items with fresh callers.

**Leak detector:** A's request carries a unique marker (`ZQXMARK<stamp>X<i>`).
A leak is the marker appearing in B's reply, which only a cross-context read
can produce.

| Observation | Result |
| --- | --- |
| cross-caller marker leak | **0/30** (upper bound < 10%) |
| B blocked and asking for context | 30/30 |

**Sensitivity check.** A detector that never fires proves nothing, so the same
marker was checked against the first caller's own continuation. In that arm the
marker does appear in the reply (observed in an ad-hoc n = 3 probe), showing the
detector can fire; A's replies consistently carry A's own request context while
B's consistently ask for the missing candidate list.

**Structural evidence.** `pending_agent_choices_v1` is declared
`PRIMARY KEY (caller_id, chat_guid)`, and `task_contexts_v2` is keyed by
`(caller_id, task_id)`. A second caller has no row to read, so the isolation
boundary is enforced by the schema, not only by application branching.

**Caveat.** Two earlier lexical leak rules were discarded after inspection:
they fired on B independently running its own discovery and recommending a
generic capability, which is not a cross-context read. The marker rule replaced
them. The `control_has_context` field in the 30-row artifact used the literal
marker and reads 0/30, because the marker is only echoed in some replies; the
keyword-level control above is the correct positive control and is reported
separately rather than silently rewritten.

## R10 -- expanded routing suite, consent gate, and partner effect, 2026-10-08

Three experiments were rerun on the deployed path after the adapter's outbound
TLS context was aligned with the ACPs identity model (chain verification and AIC
binding kept, `check_hostname = False`, because the partner certificate carries
its identity as an `acps://` URI SAN). Composites are gone from this entry: the
suite is 50 direct, 40 ambiguous, and 40 out-of-scope requests
(`data/live_samples_v2.jsonl`), each delivered three times in a fresh caller and
conversation (`data/live_runs_v2_r{1,2,3}.jsonl`).

Selection is read from the reply by `run_live_samples.extract`: a name counts
only when it leads a bullet inside the reply's bold recommendation section, which
excludes names that appear only in the recall statistics or in the closing
candidate list. `live/analyze_routing.py` recomputes every count from the stored
replies.

| Cell | n | Runs |
| --- | --- | --- |
| direct: target study partner recommended | 50 | 48 / 48 / 50 |
| ambiguous: more than one agent recommended | 40 | 39 / 38 / 38 |
| ambiguous: more than one study partner | 40 | 27 / 22 / 22 |
| ambiguous: user asked to clarify | 40 | 0 / 0 / 0 |
| out-of-scope: a study partner recommended | 40 | 0 / 0 / 0 |
| out-of-scope: any agent recommended | 40 | 40 / 40 / 40 |
| out-of-scope: index returned a candidate | 40 | 36 (single read) |

Structured discovery (`data/live_discovery_check_v2.jsonl`, one read per sample):
the target is ranked first for 40 of 50 direct requests and inside the top three
for 48; reply and discovery agree on 42 of 50, and no request has discovery
ranking the target first while the reply misses it. Eighteen of the 130 samples
changed outcome between deliveries, seven of them direct.

Finding that the tightened rule exposed: **out-of-scope requests are not
abstained**. Requests that no study partner advertises never draw a study-partner
recommendation, but the reply recommends a public-registry agent in 40 of 40
cases, so the deployed path presents the best agents the index returns and leaves
the decision to the user. The earlier "12/12 selected nothing" figure came from a
name list restricted to the five study partners and is withdrawn.

### Consent gate and partner-side effect

Partners record one line per accepted task to `EFFECT_OUTBOX`
(`acps-public-demo/roster/compose.yml` mounts `/outbox/effects.jsonl`), so an
invocation that starts work is observable without a side-effecting partner.

| Cell | n | Result |
| --- | --- | --- |
| consent trials, study partner first candidate | 30 | 28 |
| reached a partner before consent | 40 (30 + 10) | 0 |
| consent produced exactly one invocation and one action record | 36 | 36 |
| replayed consent events (two per redelivery trial) | 20 | 0 additional actions, identical stored reply |

Effect log accounting (`live/verify_effect_log.py`, output in
`data/live_effect_reconciliation.json`): the append-only log holds 39 lines =
36 trial actions (28 consent + 8 redelivery) + 2 one-trial probe calls made
before each phase (`task-f935177d-…` at 11:31:43 and `task-5d1df6b9-…` at
11:44:41) + 1 manual connectivity probe (`task-probe-b8d4f2ab` at 11:16:41).
The caller indexes missing from the log are exactly the trials whose first
candidate was not a study partner (consent 2 and 5, redelivery 5 and 7), and no
task id repeats, so no consent was retried. The 36 trial actions are written to
`data/live_effects_trials.jsonl`. `live/consent_execution.py` computes the gate
result; `live/consent_redelivery.py` covers the event-level idempotency half.
