# Pre-submission blockers

- **LNCS compilation.** `paper/draft_lncs.tex` builds in two passes with 0 errors and 0 undefined citations and is 15 pages, inside the 8--15 page range. Do the final page-by-page visual review before upload.
- **Author metadata.** Add the corresponding-author email and ORCID, plus the funding, conflict-of-interest, and data/code availability statements.
- **Labels.** The 280-item judgment suite is labelled by construction, re-read blind by an independent model annotator, and adjudicated by a third model pass (52 contested items: 19 kept, 18 changed, 15 unresolved). Every reported number is scored against those adjudicated labels, and the final set has been checked by human review.
- **Similarity and format.** Run iThenticate (total below 25%, each source below 5%) and confirm the venue page limit against the final camera-ready.

The manuscript's evidence boundary is one live deployment: discovery and recommendation through the real ingress over 130 generated requests and three deliveries each, a consent and effect experiment on the deployed adapter (30 consent trials and 10 redelivery trials, with each partner writing one record per accepted task), invariant ablations driven directly at the protocol layer, gateway cost measured component by component, and a generator-labelled judgment measurement on one hosted model sampled three times.
