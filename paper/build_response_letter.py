"""Render the response letter from Markdown to a standalone PDF source.

The letter is not a LNCS paper, so it gets its own small converter: headings,
bold runs, block quotes and pipe tables, nothing else.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "response_to_reviewers.md"
OUTPUT = ROOT / "response_to_reviewers.tex"


def escape(text: str) -> str:
    for char, repl in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ):
        text = text.replace(char, repl)
    return text


def fmt(text: str) -> str:
    """Escape and then restore the three inline marks the letter uses."""
    parts: list[str] = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")
    for chunk in pattern.split(text):
        if chunk.startswith("**") and chunk.endswith("**") and len(chunk) > 4:
            parts.append(r"\textbf{" + escape(chunk[2:-2]) + "}")
        elif chunk.startswith("`") and chunk.endswith("`") and len(chunk) > 2:
            inner = escape(chunk[1:-1]).replace(r"\_", r"\_\allowbreak{}")
            parts.append(r"\texttt{" + inner + "}")
        elif chunk.startswith("*") and chunk.endswith("*") and len(chunk) > 2:
            parts.append(r"\emph{" + escape(chunk[1:-1]) + "}")
        else:
            parts.append(escape(chunk))
    text = "".join(parts)
    return text.replace(" x ", r" $\times$ ")


def main() -> None:
    zh = "--zh" in sys.argv[1:]
    source = ROOT / ("response_to_reviewers_zh.md" if zh else "response_to_reviewers.md")
    output = ROOT / ("response_to_reviewers_zh.tex" if zh else "response_to_reviewers.tex")
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    lines = source.read_text(encoding="utf-8").splitlines()
    preamble = [r"\documentclass[11pt,a4paper]{article}"]
    if zh:
        preamble += [
            r"\usepackage{fontspec}",
            r"\setmainfont{Noto Serif CJK SC}",
            r'\XeTeXlinebreaklocale "zh"',
            r"\XeTeXlinebreakskip = 0pt plus 1pt minus 0.1pt",
        ]
    else:
        preamble += [r"\usepackage[T1]{fontenc}", r"\usepackage{newtxtext}"]
    out = preamble + [
        r"\usepackage{geometry}",
        r"\geometry{left=2.3cm,right=2.3cm,top=2.2cm,bottom=2.2cm}",
        r"\usepackage{tabularx}",
        r"\usepackage{booktabs}",
        r"\usepackage{enumitem}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{0.55em}",
        r"\begin{document}",
        r"\begin{center}{\Large\bfseries " + fmt(lines[0].lstrip("# ").strip()) + r"}\end{center}",
        r"\vspace{0.2em}",
    ]

    paragraph: list[str] = []
    quote: list[str] = []
    table: list[list[str]] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(paragraph).strip()
            if text.startswith("**") and text.endswith("**") and text.count("**") == 2:
                out.append(r"\par\vspace{0.5em}\noindent " + fmt(text))
            else:
                out.append(fmt(text))
            out.append("")  # blank line so consecutive blocks stay separate
            paragraph.clear()

    def flush_quote() -> None:
        if quote:
            out.append(r"\begin{quote}\small " + fmt(" ".join(quote)) + r"\end{quote}")
            quote.clear()

    def flush_table() -> None:
        if table:
            rows = [row for row in table
                    if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)]
            cols = max(len(row) for row in rows) if rows else 0
            spec = "@{}" + "X" * cols + "@{}"
            out.append(r"\begin{center}\small")
            out.append(rf"\begin{{tabularx}}{{\textwidth}}{{{spec}}}")
            out.append(r"\toprule")
            for index, row in enumerate(rows):
                cells = [fmt(row[i] if i < len(row) else "") for i in range(cols)]
                if index == 0:
                    cells = [r"\textbf{" + cell + "}" for cell in cells]
                out.append(" & ".join(cells) + r" \\")
                if index == 0:
                    out.append(r"\midrule")
            out.append(r"\bottomrule")
            out.append(r"\end{tabularx}")
            out.append(r"\end{center}")
            table.clear()

    for line in lines[1:]:  # the first line is the document title
        stripped = line.strip()
        if stripped.startswith("|"):
            flush_paragraph(); flush_quote()
            table.append([cell.strip() for cell in stripped.strip("|").split("|")])
            continue
        flush_table()
        if stripped.startswith(">"):
            flush_paragraph()
            quote.append(stripped.lstrip("> ").strip())
            continue
        flush_quote()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            out.append(r"\section*{" + fmt(stripped[3:]) + "}")
            continue
        if stripped.startswith("**") and paragraph:
            flush_paragraph()
        paragraph.append(stripped)

    flush_table(); flush_quote(); flush_paragraph()
    out.extend([r"\end{document}"])
    output.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
