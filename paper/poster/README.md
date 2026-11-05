# JCRAI 2026 poster

The poster is built **from the conference's own template**, not re-laid-out.

| File | What it is |
| --- | --- |
| `jcrai_poster_template.pptx` | the file downloaded from the conference site, untouched |
| `poster_template_a1.pptx` | the template filled in and scaled to A1 portrait (594 x 841 mm) |
| `poster_template_a0.pptx` | the template filled in at its original A0 portrait size (841 x 1189 mm) |

`fill_poster_template.py` opens the template, replaces the placeholder text in
each framed box, scales every shape and font by 1/sqrt(2), and sets the slide
size for the A1 file. The frame layout, the dashed section boxes and the
placeholder styling are the template's.

## Orientation

The template is A0 **portrait** (841 x 1189 mm), although the submission page
describes the board as "A1 (841mm*594mm)", which is A1 landscape. The A1 file is
therefore 594 x 841 mm: it keeps the template's portrait layout at A1 size. If
the board really is landscape, the template's columns have to be re-flowed and
it cannot stay template-faithful; confirm with the organisers before printing.

## Content

Introduction, Objectives, Materials and Methods, Results, Conclusion,
References, and Acknowledgements/Contact, plus title, authors, affiliation and
session. Three figures are embedded as pictures inside the template frames:
the architecture in Materials and Methods, the processing flow in Conclusion,
and the gateway-cost chart in Results. Each picture keeps the figure's own
aspect ratio. The numbers match the manuscript: routing 48/48/50, ablations 0/30
versus 30/30, consent 0/40 and 36/36, judgment layer 94.1% versus 83.9% with
Brier 0.095 versus 0.266.

`latex_alternative/` holds an earlier, non-template layout built with
`tikzposter`; it is kept only for reference.
