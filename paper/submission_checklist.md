# JCRAI 2026 submission checklist

## Files ready

- `draft.md`: complete English manuscript with three figures, the live routing, consent/effect, and ablation results, and the judgment-layer results for one deployed model sampled three times, including the injection stress set.
- `draft_lncs.tex`: Springer LNCS source with author block, ACPs references, seven tables, three figures, and a bibliography generated from the Markdown reference list.
- `draft_lncs.pdf`: compiled LNCS rendering (15 pages) produced with the official class.
- `draft.docx`: English review copy with figures embedded.
- `draft_zh.md` and `draft_zh.docx`: Chinese review copies.
- `draft_zh_tex.tex` and `draft_zh.pdf`: Chinese review copy typeset with XeLaTeX (16 pages, no overfull boxes); the embedded figures carry the shared English labels.
- `figures/`: architecture, state transitions, and gateway-cost figures (the coverage--risk curve pages are supplementary). Each figure has an editable source under `drawio/`, plus SVG and high-resolution PNG exports.
- `../experiments/`: live study harness, judgment suite and cached model responses, the ablation staging builds (`ablation/`), the registered partners' capability documents (`partner_config/`), the retired simulator, and reproduction scripts.

## Required before CMT upload

- **Page limit:** the latest two-pass LNCS build is 15 pages, inside the 8–15 page target; the last page carries one reference, so the author email and statements fit in the remaining space. Perform the final page-by-page visual review before upload.
- `draft_lncs.tex` compiles cleanly with `llncs.cls` v2.25 (0 errors, 0 undefined citations). Recompile with a stock TeX Live full installation; on this host the missing `newtx` fonts and support macros were added under `/data/caiyizhang/texmf` with the font map in `/data/caiyizhang/texmf-var` (see the command below).
- Add the corresponding-author email, ORCID(s), acknowledgements/funding, conflict-of-interest statement, and data/code availability statement.
- The manuscript now records the verified ACPs names and versions: Agent Collaboration Protocols, Agent Interaction Protocol, Agent Identity Code, Agent Capability Specification, `ACPs-spec-v02.02`, SDK `v2.2.0`, and commit `896e4bc79b95f11589e92eab06322430e5c64505`. Recheck normative quotations against this pinned source before upload.
- The judgment layer is measured on a hosted model (`deepseek-flash`, temperature 0) sampled three times per suite; the paper reports means with observed ranges. Labels were built, re-read blind, adjudicated by a third pass, and then checked by human review. The reported operating point is fixed at 0.99.
- The live iMessage/ACPs deployment experiment has been run: 130 generated requests through the real ingress (three deliveries each), a consent and partner-effect experiment on the deployed adapter (30 consent trials plus 10 redelivery trials, reconciled by `experiments/live/verify_effect_log.py`), and three paired ablation arms on staging copies. Raw records are under `experiments/data/live_*`; outcomes are in `experiments/live_results.md` and `experiments/live_ablation_results.md`.
- The bibliography has 25 cited entries, all present in `references.bib` under matching keys, and the repository-type citation is limited to the ACPs stack the implementation uses. Confirm that iThenticate similarity is below 25% and that no single source contributes more than 5%.
- Inspect the compiled PDF page by page and fix or accept any visual warnings.
- Confirm the final English manuscript is 8-15 pages including figures, tables, and references, then submit the English file through CMT3.

## Reproduction

```bash
cd experiments
python3 judgment_model_eval.py --suite data/judgment_suite.jsonl \
  --conditions typed,free_text,keyword \
  --output data/judgment_model_eval_r1.csv \
  --cache data/judgment_model_responses_r1.jsonl
python3 judgment_stability.py --eval data/judgment_model_eval_r{1,2,3}.csv \
  --predictions data/judgment_model_predictions_r{1,2,3}.csv
python3 j7_stress_report.py --predictions data/j7_stress_predictions_r1.csv
```

The recorded runs reuse cached responses and issue no new model calls. Routing and ablation records are replayed from `experiments/data/live_*.jsonl`; their collection required the deployed ingress and the staging ablation builds now shipped in `experiments/ablation/` (described in `experiments/live_runbook.md`). The retired simulator under `experiments/` is not part of the paper's evidence.

## LNCS compile

```bash
cd paper
python3 build_lncs.py                       # regenerate draft_lncs.tex from draft.md
export TEXMFHOME=/data/caiyizhang/texmf TEXMFVAR=/data/caiyizhang/texmf-var
export TEXINPUTS=".:$PWD/springer_templates/latex:"
pdflatex -interaction=nonstopmode draft_lncs.tex
pdflatex -interaction=nonstopmode draft_lncs.tex
```

With a full TeX Live installation the two `TEXMF*` exports are unnecessary. The generated figure PNGs must exist under `figures/` before compiling.

## Chinese reference PDF

```bash
cd paper
python3 build_zh_pdf.py                       # regenerate draft_zh_tex.tex from draft_zh.md
export TEXMFHOME=/data/caiyizhang/texmf TEXMFVAR=/data/caiyizhang/texmf-var
export FONTCONFIG_FILE=/data/caiyizhang/texmf/fonts.conf
xetex -fmt=xelatex -interaction=nonstopmode draft_zh_tex.tex
xetex -fmt=xelatex -interaction=nonstopmode draft_zh_tex.tex
```

On a host without `xelatex`, build the format once with
`xetex -ini -jobname=xelatex -progname=xelatex -translate-file=cp227.tcx '*xelatex.ini'`
under the same `TEXMFVAR`, and make a CJK font available to fontconfig (here Noto Serif/Sans CJK SC under `/data/caiyizhang/texmf/fonts/opentype/public/noto`).
