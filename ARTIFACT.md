# Artifact: Typed Judgment, Deterministic Enforcement

Reproduction package for the manuscript *Typed Judgment, Deterministic
Enforcement: A Consent-Gated Gateway Architecture for Inter-Agent Collaboration
over Messaging Channels*.

Everything reported in the paper traces to a file here. The live study ran on a
deployed iMessage/Photon ingress and an ACPs/AIP v2.2 Leader--Partner path, not
on a simulator; the retired simulator under `experiments/` is kept only for
provenance and is not cited.

## Layout

```
paper/                     manuscript
  draft.md                 submission source (English)
  draft_zh.md              Chinese reading copy
  build_lncs.py            Markdown -> Springer LNCS LaTeX
  build_zh_pdf.py          Markdown -> XeLaTeX (Chinese)
  build_docx.py            Markdown -> Word review copy
  redraw_figures.py        regenerates figures/ and drawio/ from the recorded data
  figures/, drawio/        figure exports and editable sources
experiments/               live harness and recorded data
  live/                    ingress drivers, consent/effect test, judgment drivers
  data/                    recorded runs (see the map below)
  judgment_*.py            off-line judgment suite, adjudication, stress set
references.bib             the 24 cited entries, keys matching the manuscript
```

## Claim -> artifact map

| Paper element | Recorded data | Command |
| --- | --- | --- |
| Table 5, direct/ambiguous/out-of-scope routing | `experiments/data/live_samples_v2.jsonl`, `live_runs_v2_r{1,2,3}.jsonl` | `python3 live/analyze_routing.py --runs 1 2 3` |
| Structured discovery cross-check | `experiments/data/live_discovery_check_v2.jsonl` | `python3 live/discovery_check.py` |
| Table 6, invariant ablations | `experiments/data/live_ablation_{identity,dedup,isolation}.jsonl` | staging harness, see `experiments/live_runbook.md` |
| Section 9.4, consent gate and partner effect | `live_consent_execution_live.jsonl`, `live_consent_redelivery.jsonl` | `python3 live/consent_execution.py --effect-log <outbox>` and `python3 live/verify_effect_log.py` |
| Section 9.4, J5 semantic-replay judgment on the deployed adapter | `live/judgment_advise.py`, `data/judgment_advise_samples.jsonl`, `data/judgment_advise_runs.jsonl` | `python3 live/judgment_advise.py` (drives the ingress; the verdicts land in the adapter's `judgment_log.jsonl`) |
| Table 7, Table 8, judgment layer and stress set | `judgment_model_eval_adj_r{1,2,3}.csv`, `j7_stress_eval_adj_r{1,2,3}.csv`, `judgment_*_responses_*.jsonl` | `python3 judgment_model_eval.py` and `python3 j7_stress_report.py` |
| Figure 3, gateway-side cost | `experiments/data/live_gateway_overhead.json` | `python3 live/gateway_overhead.py` |
| Figures 1--3 | `paper/figures/*.png`, `paper/drawio/*.drawio` | `python3 paper/redraw_figures.py` |

## Rebuilding the manuscript

```bash
cd paper
python3 build_lncs.py     # draft.md  -> draft_lncs.tex
python3 build_zh_pdf.py   # draft_zh.md -> draft_zh_tex.tex
# then two pdflatex passes (English) and two xelatex passes (Chinese)
```

The LNCS class file is not redistributed here; drop `llncs.cls` and
`splncs04.bst` from the official Springer proceedings template into a
`springer_templates/latex/` directory next to `build_lncs.py` before compiling.

## Environment

* Python 3.12. The live harness uses only the standard library (`urllib`), so it
  runs without a virtual environment; the figure and DOCX builders need Pillow
  and python-docx.
* Credentials are never stored in this artifact. The judgment drivers read
  `JUDGMENT_BASE_URL` / `JUDGMENT_API_KEY` (or `GEN_*` for the sample generator)
  from the environment, and the adapter reads its key from its own `.env`, which
  is not part of this repository.
* Message bodies, phone numbers, certificates, and private keys are not
  recorded: the request suites are model-generated and the identifiers in the
  raw runs are synthetic.
