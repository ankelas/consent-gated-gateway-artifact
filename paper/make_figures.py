"""Regenerate the manuscript figures from native diagrams.net sources.

The canonical geometry and labels live in ``redraw_figures.py``. Each page is
also stored as editable mxGraph XML under ``drawio/``; PNG and SVG exports are
generated from the same data and layout.
"""

from redraw_figures import architecture, coverage, states


if __name__ == "__main__":
    # The manuscript cites three figures; the retired fault-outcome page is no
    # longer generated. The full threshold curves are emitted by
    # redraw_figures.py as a supplementary page.
    for page in (architecture, states, coverage):
        page()
    print("Regenerated the three manuscript figures and their PNG/SVG exports.")
