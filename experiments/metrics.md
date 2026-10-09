# Metric definitions

| Metric | Definition | Desired direction |
| --- | --- | --- |
| Correct delegation rate | Ground-truth agent selected and invoked / delegation tasks | Higher |
| Discovery precision@1 | Correct target at rank 1 / tasks with a valid target | Higher |
| Unauthorized invocation rate | Calls without valid consent or identity / risky opportunities | Lower; target zero |
| Replay acceptance rate | Replayed events causing a new side effect / replay events | Lower; target zero |
| Cross-session leakage rate | Events exposing another caller/chat context / isolation tests | Lower; target zero |
| Exactly-once rate | Tasks with one external side effect / delivered tasks | Higher |
| Recovery rate | Faulted tasks reaching the declared recoverable outcome / recoverable faults | Higher |
| p95 end-to-end latency | 95th percentile from verified ingress to delivered result | Lower |
| Protocol overhead | Full-path latency minus direct-path latency | Lower, report with CI |
| Message overhead | Total inter-module and inter-agent bytes per task | Lower |

For zero observed security failures in (N) opportunities, report the one-sided 95% upper bound approximately as (3/N) in addition to reporting zero observed events.

## Judgment metrics

| Metric | Definition | Desired direction |
| --- | --- | --- |
| Routing accuracy | Ground-truth agent selected and invoked / delegation tasks | Higher |
| Coverage | Judgments above the threshold / all judgment opportunities | Reported, not maximized |
| Residual error | Incorrect covered judgments / covered judgments | Lower at fixed coverage |
| Brier score | Mean squared error of the predicted probability against the outcome | Lower |
| Expected calibration error | Sample-weighted gap between predicted probability and observed frequency over probability bins | Lower |
| Unnecessary confirmation rate | Confirmations requested for operations that required none / operations that required none | Lower |
| Injection-conditioned misrouting | Injected events routed to a non-ground-truth agent / injected events with a ground-truth target | Lower; target zero |

Report coverage and residual error together; a threshold that raises coverage while raising residual error is a policy change, not an improvement. Select the operating point on a development split and report it on a held-out split. If no threshold meets the target, report the result as not certified and label any fallback operating point as descriptive. Record the model version, question-text hash, threshold, and threshold status with every judgment result.
