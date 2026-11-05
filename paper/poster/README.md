# JCRAI 2026 poster (paper RI080)

`jcrai_poster_RI080.pdf` is the poster: A1 portrait (594 x 841 mm), laid out in
the format of the reference poster `JCRAI2026_RI048_Poster.pdf` - paper-ID box,
centred title, authors, dashed affiliation strip, two columns with orange
section bars, and a footer naming the conference, the session and the paper.

`preview_RI080.png` is a low-resolution render; `jcrai_poster_RI080.tex` is the
source (LaTeX, `extarticle` + `tcolorbox`, compiled with XeLaTeX).

## Sections

Only the template's seven sections are used, in the template's order:

- Left column: Introduction, Objectives, Materials and Methods (two figures).
- Right column: Results (three result tables and the cost figure), Conclusion,
  References, Contact.

Content that earlier sat in extra blocks is folded in: the seven judgment
questions are introduced in the Introduction, the module list and evaluation
sizes in Materials and Methods, and the headline numbers in the Conclusion.

The columns flow rather than snap to fixed rows: with this paper's content the
Results section is much taller than Objectives, so forcing row alignment would
leave a large blank under Objectives. The reference poster's rows line up
because its two columns happen to carry similar amounts of material.

## Font

`Poster Template-A1.pptx` uses Arial. Arial is not installed on this host, so
the poster is set in Liberation Sans, which is metric-compatible with Arial
(identical advance widths). To use literal Arial, change
`\setmainfont{LiberationSans}` to `\setmainfont{Arial}` and rebuild with XeLaTeX.

## Other files

- `JCRAI2026_RI048_Poster.pdf` - the reference poster.
- `Poster Template-A1.pptx` - the A1 template with Arial theme fonts.
- `jcrai_poster_template.pptx` - the older A0 template from the conference site.
- `poster_template_a1.pptx` / `poster_template_a0.pptx` - earlier attempts that
  filled the blank PPTX template's own boxes.
- `latex_alternative/` - an earlier non-template layout.

Rebuild:

```bash
xetex -fmt=xelatex jcrai_poster_RI080.tex
xetex -fmt=xelatex jcrai_poster_RI080.tex
```
