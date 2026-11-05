# JCRAI 2026 poster

Two print-ready versions, generated from one script, `build_poster.py`:

| File | Size | Orientation | Use |
| --- | --- | --- | --- |
| `poster_a1_landscape.pdf` | 841 x 594 mm | landscape | the size stated on the submission page |
| `poster_a0_portrait.pdf` | 841 x 1189 mm | portrait | the canvas of the distributed PPTX template |

`preview_a1.png` and `preview_a0.png` are low-resolution renders for checking
layout on screen. `jcrai_poster_template.pptx` is the file downloaded from the
conference site (one slide, A0 portrait, placeholder text only).

## Why two sizes

The submission page says "A1 (841mm*594mm)", while the template it links to is
841 x 1189 mm (A0 portrait). Both are produced so the printer can take whichever
the organisers confirm. If they ask for A1, use the landscape file; if they
confirm the template canvas, use the portrait file.

## Editing

Content lives in `build_poster.py` (`TITLE`, `AUTHORS`, `INSTITUTE`, and the
block strings), and the A1 and A0 bodies are separate so the shorter board stays
inside its height. Rebuild with:

```bash
python3 build_poster.py
pdflatex poster_a1_landscape.tex
pdflatex poster_a0_portrait.tex
```

Both files use `tikzposter`, Helvetica, and the paper's figures from
`../figures/`. The numbers on the poster are the same ones reported in the
manuscript: routing 48/48/50, ablations 0/30 versus 30/30, consent 0/40 and
36/36, judgment layer 94.1% versus 83.9% with Brier 0.095 versus 0.266.
