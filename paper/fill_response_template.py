"""Fill the conference's 'Response to Review Comments' form.

The template ships one header table plus nine Comment/Response pairs; the nine
slots below cover the three major issues, the four minor issues, and the
suggestions, grouped two-per-slot where they share a subject.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Pt


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "Response to Review Comments.docx"
OUTPUT = ROOT / "Response_to_Review_Comments_filled.docx"

HEADER = {
    "Conference:": "JCRAI 2026, Special Session XII (Agent Interconnection and "
                   "Collaboration Intelligence)",
    "Manuscript ID:": "[to be completed in CMT]",
    "Paper Title:": "Typed Judgment, Deterministic Enforcement: A Consent-Gated "
                    "Gateway Architecture for Inter-Agent Collaboration over "
                    "Messaging Channels",
    "Authors:": "Yizhang Cai, Jun Liu, Di Ma, Ke Yu, Ke Li",
    "Date:": "2 November 2026",
}

OVERALL_COMMENT = (
    "A well-motivated and carefully evaluated systems paper that cleanly separates "
    "bounded model judgment from deterministic policy enforcement in a "
    "messaging-to-agent gateway; minor weaknesses in scale and generalizability."
)

OVERALL_RESPONSE = (
    "We thank the reviewer for the careful reading and for stating the three weak "
    "points accurately. This is a minor revision: we have changed what the paper "
    "says about its evidence, added the per-sample analysis that the stored records "
    "support, and made the figure captions and the table layout carry the "
    "information the reviewer asked for. No new runs were made. Changes are listed "
    "point by point below; the manuscript remains 15 pages with no overfull boxes "
    "and no undefined references."
)

PAIRS = [
    (
        'Section 9.1: the "recommendation" outcome is parsed from reply text rather '
        "than an instrumented API, admitted by the authors; the discrepancy with "
        "discovery ranking (42/50 agreement) deserves deeper analysis.",
        "We agree that the reply parse is the weaker of the two instruments, and "
        "Section 9.1 now analyses the disagreement at the per-sample level. It "
        "reports that discovery ranked the target first for 40 of 50 direct "
        "requests and inside the top three for 48; that the reply selected the "
        "target in 48, 48 and 50 of 50 across the three deliveries; and that the "
        "instruments agree on 42 of 50 with a one-sided disagreement, since "
        "discovery never ranked the target first in a case where the reply missed "
        "it.\n"
        "Of the eight reply-only selections in the first delivery, six sit at ranks "
        "two or three in the structured list and two fall outside its top three, so "
        "where the instruments differ the reply re-orders or extends the same "
        "candidate pool rather than substituting another. The records behind these "
        "counts are live_discovery_check_v2.jsonl and live_runs_v2_r1..r3.jsonl in "
        "the artifact. We have not replaced the reply parse with an instrumented "
        "API in this revision; Section 6 states how selection is read and Section "
        "9.1 states that the structured ranking was read once per request.",
    ),
    (
        "Section 9.3: only one hosted model (deepseek-flash) is evaluated; "
        "generalisation of the typed-versus-free-text claim needs at least one "
        "more model.",
        "This is correct and remains the main open item. Section 9.3 opens by "
        "naming the endpoint and its settings (one hosted model, temperature 0, "
        "reasoning effort pinned low, no output-token cap), so the measurement is "
        "presented as a property of the two answer shapes at this endpoint; the "
        "abstract, results and conclusion make no cross-model claim. The suite, the "
        "prompts and the cached responses are in the artifact, so the comparison "
        "can be repeated on another model without changing the harness. We did not "
        "add a second model in this revision, because that requires a new run of "
        "the 280-item suite at the same three repetitions.",
    ),
    (
        "Section 9.6: the injection stress set is template-generated, so real-attack "
        "robustness is untested.",
        "Correct, and the paper states the construction rather than hiding it. The "
        "set is a designed grid: 8 steering families x 5 carriers x 5 authority "
        "frames give 200 injected items, and 8 families x 4 carriers x 8 report "
        "forms give 256 benign near-misses. A blind re-read disagreed with 64 of "
        "the 456 built labels, adjudication changed 51, and the held-out split "
        "holds 67 injected and 47 benign items. The set measures the false-alarm "
        "behaviour of the two answer shapes on quoted and reported text; it is not "
        "presented as robustness to attacks collected in the wild. Section 9.6 now "
        "states the template construction in one clause, without the repetition "
        "around it.",
    ),
    (
        "Fig. 1 and Fig. 2 lack caption-level explanation of message flows.",
        "Both captions now carry the flow. Fig. 1 follows the message from ingress "
        "(M1) through partition (M2), discovery (M3), consent (M4), execution (M5), "
        "state (M6) and delivery (M7), and names which judgment points feed which "
        "module. Fig. 2 names the branches: cached-event return, policy "
        "cancellation, the pending decision that re-enters at authentication when "
        "the user answers, endpoint validation, and the retry classifier.",
    ),
    (
        "Table 5's port triple notation is confusing.",
        "The caption now states that ports are read as ablation / same-code control "
        "/ live instance, and the column header carries the same abbreviation, so "
        "the triple no longer has to be inferred from the caption text.",
    ),
    (
        "Section 9.5's J5 advisory experiment (60 events) is small.",
        "The design is now stated in one place: twenty conversations, three event "
        "types each, 60 events judged. At the 0.9 threshold the layer called 20 of "
        "20 paraphrases replays (95% Wilson [83.9%, 100%]) and let 0 of 40 "
        "non-replays cross it (bounding the rate at 7.5%); the advisory call has a "
        "median of 1.07 s (0.53-1.74 s). We have kept the counts and made the "
        "design explicit rather than adding events in this revision.",
    ),
    (
        'Several hyphenation/spacing errors in the PDF (e.g., "planeinadvisorymode", '
        "p.1).",
        'We checked the current build: page 1 reads "plane in advisory mode" with '
        "the space intact, and a scan of the PDF text for long alphabetic strings "
        "returns no joined words. The two apparent hits are line-break artefacts of "
        "the text extractor rather than text in the PDF. If the reviewer's copy "
        "still shows a joined word, it may be worth checking the extraction tool.",
    ),
    (
        "Suggestions: add a second judgment model; instrument recommendation "
        "extraction.",
        "Both acknowledged. The second model is the next item we would prioritise; "
        "the harness, suite and cached prompts are in the artifact, so the run can "
        "be repeated on another endpoint without changing the measurement code. For "
        "recommendation extraction, this revision adds the rank-level analysis that "
        "the structured instrument already supports; replacing the reply parse with "
        "a protocol-level record would require an adapter change and a re-delivery "
        "of the 130 requests, which this revision does not include.",
    ),
    (
        "Suggestions: report the latency-accuracy trade-off of the judgment plane; "
        "expand Fig. 2 with consent-branch detail; clarify whether ambiguous-request "
        "composition was manually checked.",
        "The paper reports the advisory call latency (Section 9.5) and the "
        "gateway-side handling cost (Section 9.4), but not a latency-accuracy curve "
        "across thresholds; such a curve would need a run at each threshold, which "
        "the recorded data do not contain. Fig. 2's caption now describes the "
        "pending-decision branch and the re-entry at authentication. Section 9.1 "
        "states that a combination counts as more than one recommended agent and "
        "that whether the plan semantically covers the request was not adjudicated; "
        "the revision keeps that statement because the 40 ambiguous requests were "
        "not semantically adjudicated.",
    ),
]


def append_text(paragraph, text: str, size: float = 10.5) -> None:
    """"Append value text to a labelled paragraph, keeping the label intact."""
    current = paragraph.text
    if current.rstrip().endswith("Response"):
        separator = ": "
    elif current.endswith((" ", "\u00a0")):
        separator = ""
    else:
        separator = " "
    run = paragraph.add_run(separator + text)
    run.font.size = Pt(size)


def main() -> None:
    doc = Document(TEMPLATE)

    # Header table: append the value to each field label.
    for cell in doc.tables[0].rows[0].cells:
        for paragraph in cell.paragraphs:
            label = paragraph.text.strip()
            if label in HEADER and HEADER[label] not in paragraph.text:
                append_text(paragraph, HEADER[label], size=10)

    # Overall comment and response.
    paragraphs = doc.paragraphs
    for index, paragraph in enumerate(paragraphs):
        if paragraph.text.strip().startswith("Overall Comment:"):
            append_text(paragraph, OVERALL_COMMENT, size=10.5)
            for candidate in paragraphs[index + 1:]:
                if candidate.text.strip().startswith("Response:"):
                    append_text(candidate, OVERALL_RESPONSE, size=10.5)
                    break
            break

    # The nine Comment/Response pairs: for each "Comment N:" take the first
    # "Response" paragraph that follows it (one slot is spelled without a colon).
    paragraphs = doc.paragraphs
    for number, (comment, response) in enumerate(PAIRS, start=1):
        for index, paragraph in enumerate(paragraphs):
            if paragraph.text.strip().startswith(f"Comment {number}:"):
                append_text(paragraph, comment, size=10.5)
                for candidate in paragraphs[index + 1:]:
                    if candidate.text.strip().startswith("Response"):
                        append_text(candidate, response, size=10.5)
                        break
                break

    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
