# Thesis workspace

Paper workspace for Yizhang Cai: *Typed Judgment, Deterministic Enforcement* (JCRAI 2026).

## Layout

- `paper/draft.md`: English submission source; `paper/draft_zh.md`: Chinese reading copy.
- `paper/draft_lncs.tex` / `paper/draft_lncs.pdf`: generated Springer LNCS source and its 15-page build.
- `paper/draft_zh_tex.tex` / `paper/draft_zh.pdf`: generated Chinese source and its 16-page build (no page limit on the reading copy).
- `paper/draft.docx`, `paper/draft_zh.docx`: generated review copies.
- `paper/figures/`, `paper/drawio/`: figure exports and editable sources.
- `experiments/`: live study harness, judgment suite, cached model responses, and the retired simulator.
- `experiments/live/`: sample generation, ingress delivery, discovery cross-check, and ablation drivers.
- `references.bib`: bibliography records behind the Markdown reference list.

## Live study

The routing, consent, and ablation results come from a deployed iMessage/Photon + ACPs path, not from a simulator. Design and prerequisites are in `experiments/live_experiment_plan.md` and `experiments/live_runbook.md`; recorded outcomes are in `experiments/live_results.md` and `experiments/live_ablation_results.md`. The ablation staging source is in `experiments/ablation/`, copied from `/data/caiyizhang/ablation/` on the study host without the runtime state, the partner logs or any certificate material; the registered partners' capability documents are in `experiments/partner_config/`. Raw records are under `experiments/data/` (`live_samples_v2.jsonl`, `live_runs_v2_r{1,2,3}.jsonl`, `live_discovery_check_v2.jsonl`, `live_consent_execution_live.jsonl`, `live_consent_redelivery.jsonl`, `live_ablation_identity.jsonl`, `live_ablation_dedup.jsonl`, `live_ablation_isolation.jsonl`).

## Judgment layer

```bash
cd experiments
python3 judgment_model_eval.py --suite data/judgment_suite.jsonl \
  --conditions typed,free_text,keyword \
  --output data/judgment_model_eval.csv \
  --cache data/judgment_model_responses.jsonl
```

One deployed model (`deepseek-flash`) is sampled three times per suite; `data/judgment_model_eval_r{1,2,3}.csv` and `data/j7_stress_eval_r{1,2,3}.csv` are the recorded runs, each with its cached responses, per-item predictions, and manifest. Cached responses make a re-run free. The endpoint is not deterministic at temperature 0, so `judgment_stability.py` reports means, ranges, and pairwise answer agreement, and the paper quotes those ranges rather than single-run points. Credentials come from a local config file or environment variables and never enter the artifact.

## Paper build

```bash
cd paper
python3 build_lncs.py      # draft.md -> draft_lncs.tex
python3 build_zh_pdf.py    # draft_zh.md -> draft_zh_tex.tex
```

Then compile `draft_lncs.tex` with pdflatex and `draft_zh_tex.tex` with XeLaTeX; `paper/submission_checklist.md` records the environment variables this host needs. Regenerating figures or Word review copies requires Pillow and python-docx.

The simulator under `experiments/` (`gateway.py`, `core_experiment.py`, `simulator.py`, `data/core_*.csv`) is the earlier synthetic study. It is kept for provenance and is not part of the paper's evidence.

No credentials, raw user messages, phone numbers, certificates, or private keys are included.

## Artifact

The reproduction package is published at
**https://github.com/ankelas/consent-gated-gateway-artifact** (public).
`ARTIFACT.md` maps every reported result to the file it comes from and the command
that reproduces it.
