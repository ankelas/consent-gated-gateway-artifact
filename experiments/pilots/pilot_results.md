# Pilot results: three topics, real runs, small scale

Date: 2026-10-15. Model: `deepseek-v4-flash` through the DeepSeek
chat-completions API, temperature 0 for the task pilots and 0.3 for the
dialogue pilot. One run per condition, no repeats, tasks auto-generated with
computed ground truth. Scripts and raw records are in this directory:
`p1_decomposition.py`, `p2_reflection.py`, `p3_memory.py`, plus
`data/p1_decomposition.jsonl`, `data/p1_longchain.jsonl`,
`data/p2_reflection.jsonl`, `data/p3_memory.jsonl`.

These are pilots. They support statements about mechanism and direction at this
scale; they do not support claims about benchmarks or about performance in
general.

## P1 — Hierarchical decomposition with confidence-based routing

Treatment: planner emits subtasks with a confidence value; subtasks below 0.7
confidence, or of kind `calc`, go to a calculator specialist; an aggregator
combines the results and a verifier recomputes the final answer.
Baseline: one call to the same model with the same question.

| Task family | Baseline | Treatment | Baseline calls / latency | Treatment calls / latency |
| --- | --- | --- | --- | --- |
| 6-step chains, 3-digit operands, n=24 | 24/24 | 24/24 | 1.00 / 1.4 s | 5.29 / 18.5 s |
| 12-step chains, variable operands, n=8 | 8/8 | 8/8 | 1.00 / 9.3 s | 5.12 / 74.2 s |

Mean subtasks routed to the specialist: 1.83 of about 2.

Result: no accuracy difference. Decomposition cost roughly five model calls and
thirteen times the latency for the same answers, and the confidence router sent
almost every subtask to the specialist. On arithmetic chains the model does not
leave headroom for a decomposition framework to exploit, which is the honest
reading of this family rather than evidence that decomposition is useless.

## P2 — Forward planning with retrospective reflection over tools

Treatment: after the planned calls are executed, a verification call inspects
the recorded tool outputs against the question; when the check fails, a
reflection round repairs the plan, up to two rounds.
Baseline: the same planner and the same tools, executed once with no check.

| Task family | Plan only | Plan + reflection |
| --- | --- | --- |
| Dependent chain (second call needs the first result), n=8 | 8/8 | 8/8 |
| Failing tool (unknown city; the agent must substitute), n=8 | 1/8 | 6/8 |
| Plain single-call task, n=8 | 8/8 | 8/8 |
| Overall, n=24 | 17/24 (70.8%) | 22/24 (91.7%) |

Mean model calls: 2.00 → 3.71. Mean tool invocations: 1.42 → 2.21. Reflection
triggered on 17 of 24 tasks and every triggered task ended correct; of the
seven tasks the first pass got wrong, reflection repaired five.

Result: the entire difference sits in the family where the natural plan fails
and has to be revised. On tasks that need no repair, the check is pure overhead
(17 triggers for 7 real failures). This is the mechanism the paper claims, at
24 tasks and one model.

## P3 — Long-horizon consistency with a three-layer memory

Five scripted personas, four sessions each, with a confusable distractor
(a third party's attribute) planted in session 2. Treatment keeps working
turns, an end-of-session episode summary and semantic fact triples, retrieves by
relevance, recency and importance, and runs a consistency check on the draft
reply. Baseline sees only the current session.

| Measure | Session only | Three-layer memory |
| --- | --- | --- |
| Fact retention over 30 recall probes | 0/30 (0%) | 20/30 (66.7%) |
| Constraint kept (allergy prompt), 5 probes | 4/5 (80%) | 5/5 (100%) |
| Model calls | 70 | 145 |

Result: the baseline is a floor by construction, since it has no path to an
earlier session, so the zero is a sanity check rather than a finding. The
informative numbers are the 66.7% retention and the five consistent replies
under a memory that also carries a planted distractor: a third of the facts are
still lost, which locates the remaining problem in retrieval and
consolidation rather than in storage.

## What these numbers can and cannot carry

Can carry: a mechanism comparison on generated task sets at roughly 25 items
per condition, a cost accounting per call and per second, and a reproducible
harness for each of the three topics.

Cannot carry: benchmark claims, cross-model generalisation (one model is
tested), statistical confidence (single run, no repeats), or user satisfaction
(no human raters; the dialogue judgement is model-made). Each of the three
topics would need roughly 5–10 times the task volume and at least two model
families before its abstract could carry words like "outperforms existing
baselines".
