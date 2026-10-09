# Human-label and external-validity completion plan

The current judgment suite is generator-labeled. It must not be described as human ground truth. Before submission, obtain independent labels for a held-out sample using the following protocol.

1. Sample the existing held-out task IDs with the stable `test` split, preserving all seven judgment points and injected/benign J7 cases.
2. Give two annotators the redacted state, question, closed option list, and the declared abstention option. Do not show model predictions or the latent generator label.
3. Record one option, `uncertain`, and an adjudication note. A third reviewer resolves disagreements. The final label is the adjudicated label; report raw agreement and Cohen's kappa before adjudication.
4. Replace the synthetic label only in a new evaluation file. Keep the generator-labeled run as a separate mechanism artifact.

`experiments/data/judgment_human_annotation_template.csv` is the blank import/export template. It intentionally contains no fabricated labels.

For external validity, repeat `judgment_model_eval.py` with a second model family or a self-hosted model at the same prompts, split, and temperature. Report the model identifier, endpoint class, cost/latency, accuracy, Brier, ECE, coverage, residual error, and injection-conditioned error. Do not pool models or change the threshold-selection rule.

The current paper may report the existing numbers as one-model synthetic-suite evidence only. It cannot claim human-label validity or model-family generality until these two additions are run.
