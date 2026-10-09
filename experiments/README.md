# Experiment protocol

This directory is the source of truth for the paper's empirical claims. The paper reports a live deployment study plus a hosted-model judgment measurement; the earlier synthetic study is retained only for provenance.

## Live study

- `live/sample_gen.py` generates the request suite with a pinned hosted model from each registered partner's advertised skills, in Simplified Chinese, and caches the generation.
- `live/run_live_samples.py` delivers each sample, in a fresh caller and conversation, through the deployed adapter's inbound endpoint and records the reply; selection is read from that reply by a line-scoped rule (`extract`) that counts a name only when it leads a bullet in the reply's recommendation section.
- `live/analyze_routing.py` recomputes the routing counts from the stored replies, so the three deliveries are scored with the same rule, and writes `data/live_routing_summary_v2.json`.
- `live/discovery_check.py` reads the structured discovery ranking for the same suite (`data/live_discovery_check_v2.jsonl`).
- `live/photon_cells.py`, `live/leader_rest.py`, and `live/agents.py` wrap the ingress, the ACPs Leader, and partner registration.
- `live/identity_binding.py` and `live/ingress_integrity.py` exercise identity and ingress checks on the deployed path.
- `live/consent_probe.py` and `live/consent_escalation.py` send requests, then escalating natural-language confirmations, and count the JSON-RPC calls that reach the partner containers; natural language never triggered an invocation.
- `live/consent_execution.py` drives the adapter's documented consent form (`使用 1：<instruction>`) on the deployed adapter, counts partner calls before and after consent, and writes `data/live_consent_execution_live.jsonl`. With `--effect-log` it counts the partner-side records in `/data/caiyizhang/acps-public-demo/outbox/effects.jsonl` instead of RPC access-log lines.
- `live/consent_redelivery.py` repeats each consent event twice after the consented call lands, and shows that a replayed event produces no further partner action and returns the stored reply (`data/live_consent_redelivery.jsonl`).
- The partners record one line per accepted task to `EFFECT_OUTBOX=/outbox/effects.jsonl` (wired in `acps-public-demo/roster/compose.yml`), so an invocation that starts work is observable without a side-effecting partner. `live/verify_effect_log.py` partitions that append-only log by phase and caller number, writes `data/live_effect_reconciliation.json` and the 36 trial-associated records in `data/live_effects_trials.jsonl`, and asserts that no task id repeats (the log's other records are the probe calls that preceded each phase).
- `live/gateway_overhead.py` times the gateway operations on their own (ingress reject, deduplication cache hit, AIP identity reject, AIP accept round trip) plus the first delivery for scale, and writes `data/live_gateway_overhead.json`.
- The ablation arms are staging copies of the deployed code with one environment-gated change each; the sources are under `/data/caiyizhang/ablation/`.
- Recorded outcomes: `live_results.md` and `live_ablation_results.md`; raw records under `data/live_*.jsonl`.

## Telemetry

`telemetry.py` and `telemetry_schema.json` define the span fields the deployed path records. The proposed remote patch was never deployed, so the paper reports no online telemetry numbers.

## Retired synthetic study

`gateway.py`, `simulator.py`, `core_experiment.py`, `run_pilot.py`, `threshold_sweep.py`, `legacy_encoding_simulator.py`, and `data/core_*.csv` implement the earlier offline study with a synthetic workload, router, and fault set. It is not cited in the paper and must not be reported as a deployment measurement. Reproduce it with:

```bash
cd experiments
python3 core_experiment.py --seed 20260930 --repetitions 100 --output data/core_results.csv
python3 analyze_core.py data/core_results.csv --summary data/core_summary.csv --contrasts data/core_contrasts.csv
python3 -m unittest discover -s . -p 'test_*.py' -v
```

## Judgment layer artifacts

- `judgment_points.json` specifies the seven judgment points (J1–J7): question text, answer shape, owning module, abstention threshold, fallback action, and failure consequence. It is a specification, not a labeled dataset.
- `judgment_eval.py` generates a transparent reference suite and a deterministic cue judge; it validates the schema, split discipline, and metric code.
- `judgment_suite.py` generates the harder labeled suite used for the model measurement: labels come from a latent variable and the surface text contains counter-cues.
- `judgment_model_eval.py` measures a pinned OpenAI-compatible model in a typed and a free-text answer shape, plus a keyword baseline, and writes the evaluation table, per-item predictions, cached responses, and a run manifest. ECE uses non-overlapping half-open bins (the final bin includes its lower edge); threshold rows distinguish a development-certified point from the declared 0.99 fallback.
- `j7_stress.py` builds the injection stress set from an explicit grid (200 injected, 256 benign near-misses); `j7_stress_report.py` reports a run's injection miss rate and benign false-alarm rate; `judgment_stability.py` reports the mean, range, and pairwise answer agreement across repeated runs.
- `judgment_llm_review.py` has a hosted model re-read every label as an independent annotator (blind to the constructed label and to the predictions) and writes `data/judgment_llm_review_report.md`; it is a check for disputed items, not a substitute for human adjudication.
- `judgment_adjudicate.py` sends the contested items to a third pass that sees both readings and their reasons (presentation order randomised per item) and writes `data/*_adjudicated.jsonl`. Those suites keep the same task ids, so the cached predictions can be re-scored against the adjudicated labels with no new calls to the model under test; `*_adj_r{1,2,3}.csv` are the re-scored runs that the paper reports.

Two evaluation settings are fixed in the code and matter for reproduction. `EFFORT` in `judgment_model_eval.py` is pinned to `low`: at the endpoint's default effort the token budget is consumed before any content is emitted and roughly one reply in ten comes back empty, and the same item at the same temperature receives different answers under different reasoning budgets. A reply that names no option is recorded as `unparsed` and scored as wrong instead of being defaulted to the first option.
- `threshold_sweep.py` sweeps the typed-judgment threshold on the harness and writes `data/typed_threshold_sweep.csv`. It is retained for harness checks; the paper's judgment numbers come from `judgment_model_eval.py`.

Pinned judgment run (cached responses make a re-run free):

```bash
python3 judgment_suite.py --per-point 40 --output data/judgment_suite.jsonl
python3 judgment_model_eval.py --suite data/judgment_suite.jsonl \
  --conditions typed,free_text,keyword \
  --output data/judgment_model_eval.csv \
  --cache data/judgment_model_responses.jsonl
```

Credentials are read from `--config` or `JUDGMENT_BASE_URL` / `JUDGMENT_API_KEY` / `JUDGMENT_MODEL`, and are never written to the artifact. Everything is measured on one deployed model (`deepseek-flash`) and repeated three times per suite: `data/judgment_model_eval_r{1,2,3}.csv` with their caches, per-item predictions, and manifests, and `data/j7_stress_eval_r{1,2,3}.csv` for the injection stress set. The hosted endpoint is not deterministic at temperature 0, so the paper reports means and ranges rather than single-run points. Two earlier artifacts are retained but not used: `data/excluded_other_identifier/` (issued with a second model identifier) and `data/superseded_stress_v1/` (the first stress set, whose benign items carried an outer request and whose injected items did not, a confound that the current set removes). Routing repeats live in `data/live_direct_r{2,3}.jsonl`, `data/live_ambiguous_r{2,3}.jsonl`, and `data/live_out_of_scope_r{2,3}.jsonl`.

## Required run metadata

```json
{
  "run_id": "generated",
  "experiment": "e1_ablation",
  "variant": "full",
  "seed": 0,
  "source_revision": "recorded-at-run-time",
  "config_hash": "recorded-at-run-time",
  "workload_id": "recorded-at-run-time",
  "model": "recorded-or-mock",
  "telemetry_schema": "v1"
}
```

## Required outcome fields

```json
{
  "task_success": true,
  "correct_agent": true,
  "consent_required": true,
  "consent_satisfied": true,
  "identity_check_passed": true,
  "unauthorized_call": false,
  "cross_session_leak": false,
  "duplicate_side_effect": false,
  "recovered": true,
  "latency_ms": 0,
  "message_bytes": 0,
  "retry_count": 0,
  "failure_category": null
}
```

Do not store raw phone numbers, message bodies, certificates, private keys, access tokens, or unredacted prompts in experiment output.
