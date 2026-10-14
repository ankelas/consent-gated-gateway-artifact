"""Build a Chinese reference PDF from ``draft_zh.md`` with XeLaTeX.

The English submission is produced by ``build_lncs.py`` and keeps the Springer
LNCS class.  This script produces a readable Chinese review PDF: the same
structure, tables, figures and reference list, typeset with XeLaTeX because
the host has no CJK support under pdfLaTeX.  It imports the Markdown helpers
from ``build_lncs`` so the English and Chinese renderings cannot drift apart.

Compile with::

    xetex -fmt=xelatex draft_zh_tex.tex      # twice, for references
"""

from __future__ import annotations

import re
from pathlib import Path

from build_lncs import (  # reuse the shared Markdown helpers
    CITATION_KEYS,
    UNNUMBERED_SECTIONS,
    figure_block,
    inline,
    table_block,
)

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "draft_zh.md"
TEX_OUTPUT = ROOT / "draft_zh_tex.tex"

PREAMBLE = [
    r"\documentclass[11pt,a4paper]{article}",
    r"\usepackage{geometry}",
    r"\geometry{left=2.4cm,right=2.4cm,top=2.6cm,bottom=2.6cm}",
    r"\usepackage{fontspec}",
    r"\setmainfont{Noto Serif CJK SC}",
    r"\setsansfont{Noto Sans CJK SC}",
    r'\XeTeXlinebreaklocale "zh"',
    r"\XeTeXlinebreakskip = 0pt plus 1pt minus 0.1pt",
    r"\XeTeXlinebreakpenalty = 0",
    r"\usepackage{graphicx}",
    r"\usepackage{booktabs}",
    r"\usepackage{tabularx}",
    r"\usepackage{array}",
    r"\usepackage{amsmath}",
    r"\usepackage[hidelinks]{hyperref}",
    r"\setlength{\parindent}{2em}",
    r"\setlength{\parskip}{0.35ex}",
    r"\setlength{\emergencystretch}{3em}",
    r"\tolerance=1500",
    r"\renewcommand{\abstractname}{摘要}",
    r"\renewcommand{\tablename}{表}",
    r"\renewcommand{\figurename}{图}",
    r"\renewcommand{\refname}{参考文献}",
    r"\linespread{1.18}",
    r"\renewcommand{\arraystretch}{1.15}",
    r"\begin{document}",
]


def bibliography(lines: list[str]) -> list[str]:
    start = lines.index("## 参考文献")
    pattern = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")
    entries: list[tuple[int, str]] = []
    for line in lines[start + 1:]:
        match = pattern.match(line.strip())
        if match:
            entries.append((int(match.group(1)), match.group(2)))
    out = [rf"\begin{{thebibliography}}{{{len(entries)}}}"]
    for number, text in entries:
        key = CITATION_KEYS.get(str(number), f"ref{number}")
        out.append(rf"\bibitem{{{key}}} {inline(text)}")
    out.append(r"\end{thebibliography}")
    return out


def convert() -> str:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    title = lines[0].removeprefix("# ").strip()
    author = lines[2].strip()
    affiliation = lines[3].strip()

    abstract_start = lines.index("## 摘要") + 1
    abstract_end = lines.index("## 1. 引言")
    abstract_lines = [line.strip() for line in lines[abstract_start:abstract_end] if line.strip()]
    abstract = " ".join(line for line in abstract_lines if not line.startswith("**关键词"))
    keywords = next(line for line in abstract_lines if line.startswith("**关键词")).removeprefix("**关键词：**").strip()

    out = list(PREAMBLE)
    out.append(rf"\title{{{inline(title)}}}")
    # ``\author`` is typeset inside a single-cell tabular, which cannot wrap a
    # long affiliation line; a centred \parbox restores paragraph mode so the
    # CJK and the e-mail list can break across lines.
    out.append(
        rf"\author{{\parbox{{\dimexpr\textwidth-2\tabcolsep\relax}}{{\centering {inline(author)}\\[0.4em]\small {inline(affiliation)}}}}}"
    )
    out.append(r"\date{}")
    out.append(r"\maketitle")
    out.append(r"\begin{abstract}")
    out.append(inline(abstract))
    out.append(rf"\par\medskip\noindent\textbf{{关键词：}} {inline(keywords)}")
    out.append(r"\end{abstract}")

    i = abstract_end
    pending_caption: str | None = None
    table_number = 0
    figure_number = 0
    list_mode: str | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(inline(" ".join(item.strip() for item in paragraph)))
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            out.append(rf"\end{{{list_mode}}}")
            list_mode = None

    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "## 参考文献":
            flush_paragraph()
            close_list()
            out.extend(bibliography(lines))
            break
        if not stripped:
            flush_paragraph()
            close_list()
            i += 1
            continue
        caption_match = re.fullmatch(r"\*\*表\s*(\d+)[.。]\*\*\s*(.*)", stripped)
        if caption_match:
            flush_paragraph()
            close_list()
            pending_caption = caption_match.group(2).strip()
            i += 1
            continue
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image:
            flush_paragraph()
            close_list()
            figure_number += 1
            caption = re.sub(r"^图\s*\d+[：:.]?\s*", "", image.group(1))
            out.extend(figure_block(caption, image.group(2), figure_number))
            i += 1
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            close_list()
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            table_number += 1
            out.extend(table_block(table_lines, pending_caption, table_number))
            pending_caption = None
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].replace("→", "->"))
                i += 1
            out.extend([r"\begin{verbatim}", *code, r"\end{verbatim}"])
            i += 1
            continue
        heading = re.match(r"^(#{2,3})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level, heading_text = len(heading.group(1)), heading.group(2)
            heading_text = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", heading_text)
            if heading_text in UNNUMBERED_SECTIONS:
                command = "section*"
            else:
                command = "section" if level == 2 else "subsection"
            out.append(rf"\{command}{{{inline(heading_text)}}}")
            i += 1
            continue
        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            if list_mode != "enumerate":
                close_list()
                out.append(r"\begin{enumerate}")
                list_mode = "enumerate"
            out.append(rf"\item {inline(re.sub(r'^[0-9]+[.、]\s*', '', stripped))}")
            i += 1
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            if list_mode != "itemize":
                close_list()
                out.append(r"\begin{itemize}")
                list_mode = "itemize"
            out.append(rf"\item {inline(stripped[2:])}")
            i += 1
            continue
        if re.fullmatch(r"\$[^$]+\$", stripped):
            flush_paragraph()
            close_list()
            out.append("\n".join([r"\begin{equation}", stripped[1:-1], r"\end{equation}"]))
            i += 1
            continue
        paragraph.append(stripped)
        i += 1
    flush_paragraph()
    close_list()
    out.extend([r"\end{document}"])
    return "\n\n".join(out) + "\n"


def main() -> None:
    TEX_OUTPUT.write_text(convert(), encoding="utf-8")
    print(TEX_OUTPUT)


if __name__ == "__main__":
    main()
