# Response to Reviewers

We thank the reviewer for a careful reading. The revision is a minor revision:
the text, the figure captions and the table layout are revised, and no new runs
were made. Changes are marked below with the section they touch.

## Major issues

**M1. The recommendation outcome is parsed from reply text rather than an
instrumented API, and the 42/50 agreement with the discovery ranking deserves
deeper analysis.**

We agree that the reply parse is the weaker of the two instruments, and the
revision analyses the disagreement at the per-sample level using the stored
records. Section 9.1 now reports three facts that the earlier one-sentence
version did not: the disagreement is one-sided, because discovery never ranked
the target first in a case where the reply missed it; of the eight reply-only
selections in the first delivery, six sit at ranks two or three in the
structured list and two fall outside its top three; and therefore, where the
two instruments differ, the reply re-orders or extends the same candidate pool
rather than substituting a different one. The per-sample records behind these
numbers are the `live_discovery_check_v2.jsonl` and `live_runs_v2_r*.jsonl`
files in the artifact, so a reader can recheck every case.

We have not replaced the reply parse with an instrumented API in this revision.
Section 6 states how selection is read from the reply, and Section 9.1 states
that the structured ranking was read once per request and what it produced.

**M2. Only one hosted model is evaluated, so the typed-versus-free-text claim
needs a second model.**

This is correct and unchanged. Section 9.3 opens by naming the single hosted
model, its temperature, its reasoning effort and the absence of an output-token
cap, so the measurement is presented as a property of the two answer shapes at
this endpoint. We have not added a second model in this revision; the paper
does not claim cross-model generalisation anywhere in the abstract, results or
conclusion.

**M3. The injection stress set is template-generated, so robustness to real
attacks is untested.**

Correct. The set is a designed grid: eight steering families times five
carriers times five authority frames give 200 injected items, and eight
families times four carriers times eight report forms give 256 benign
near-misses. Section 9.3 describes the grid and the blind re-read that changed
51 of the built labels, and Section 9.6 states that the set is built from
templates. What the stress set measures is the false-alarm behaviour of the two
answer shapes on quoted and reported text; it is not presented as a measure of
robustness to attacks collected in the wild.

## Minor issues

**Fig. 1 and Fig. 2 captions.** Both captions now describe the message flow.
Fig. 1 names the path from ingress (M1) through partition (M2), discovery (M3),
consent (M4), execution (M5), state (M6) and delivery (M7), and says which
judgment points feed which module. Fig. 2 names the branches: cached-event
return, policy cancellation, the pending decision that re-enters at
authentication when the user answers, endpoint validation and the retry
classifier.

**Table 5 port notation.** The caption now states that ports are read as
ablation / same-code control / live instance, and the column header carries the
same abbreviation, so the triple no longer has to be inferred from the caption.

**Section 9.5 sample size.** The text states the design directly: twenty
conversations, three event types each, 60 events judged, with 20/20 replay
recall, 0/40 false positives at the 0.9 threshold, Wilson bounds on both, and a
median advisory latency of 1.07 s. We have kept the numbers and made the
design explicit rather than adding events.

**Hyphenation and spacing.** We checked the current build. Page 1 reads "plane
in advisory mode" with the space intact, and a scan of the PDF text for long
alphabetic strings returns no joined words; the two apparent hits are
line-break artefacts of `pdftotext`, not text in the PDF. If the reviewer's
copy still shows a joined word, it is worth checking the extraction tool.

**Ambiguous-request composition.** Section 9.1 already states that the
combination is counted as more than one recommended agent and that whether the
plan semantically covers the request was not adjudicated. We have left that
statement as it is, because the revision does not add a semantic adjudication
of the 40 ambiguous requests.

## Effect on the manuscript

The revised manuscript is 15 pages in the LNCS layout, with no overfull boxes
and no undefined references. The changes above are confined to Section 9.1, the
captions of Figs. 1 and 2, and the caption and header of Table 5; Section 9.6
and the conclusion were shortened by the sentences those additions duplicated.
