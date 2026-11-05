# JCRAI 2026 poster (paper 80)

`jcrai_poster_80.pdf` is the poster, laid out in the format of the reference
poster `JCRAI2026_RI048_Poster.pdf`: A1 portrait (594 x 841 mm), paper-ID box in
the top-left corner, centred title, authors, dashed affiliation strip, two
columns with orange section bars, and a footer naming the conference, the
special session and the paper.

`preview_jcrai80.png` is a low-resolution render for checking on screen;
`jcrai_poster_80.tex` is the source (LaTeX, `extarticle` + `tcolorbox`).

## Columns

Left: Introduction, Objectives, Judgment plane, Materials and Methods
(architecture figure), Contributions.

Right: Results (routing, paired ablations, consent, judgment layer, gateway
cost figure), Processing flow (flow figure), Conclusion, References, Contact.

Numbers match the manuscript: routing 48/48/50 of 50, ambiguous 39/38/38 of 40,
out-of-scope 0/40; ablations 0/30 versus 30/30; consent 0/40 and 36/36;
judgment layer 94.1% versus 83.9% with Brier 0.095 versus 0.266.

## Other files

- `JCRAI2026_RI048_Poster.pdf` - the reference poster supplied by the authors.
- `jcrai_poster_template.pptx` - the blank template from the conference site.
- `poster_template_a1.pptx` / `poster_template_a0.pptx` - an earlier attempt that
  filled the blank template's own boxes; kept for reference.
- `latex_alternative/` - an earlier non-template layout.

Rebuild with:

```bash
pdflatex jcrai_poster_80.tex
pdflatex jcrai_poster_80.tex
```

## Font

`Poster Template-A1.pptx` uses Arial for both theme fonts. Arial is not
installed on this host, so the poster is typeset in Liberation Sans, the
Arial-metric substitute (Verdana-metric? no: Liberation Sans is metric-compatible
with Arial). Text widths therefore match the template's font, and the two are
visually almost identical. If literal Arial is required, open the PDF's source
`jcrai_poster_80.tex` and change the `\setmainfont{LiberationSans}` block to
`\setmainfont{Arial}` on a machine that has Arial installed, then rebuild with
XeLaTeX.
