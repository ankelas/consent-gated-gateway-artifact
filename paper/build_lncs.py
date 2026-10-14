"""Convert the Markdown manuscript into an LNCS proceedings source.

The repository keeps Markdown as the editable source.  This small converter is
deliberately deterministic: it handles the Markdown constructs used by the
manuscript and emits an author-ready ``llncs.cls`` document without requiring
Pandoc.  It is not intended to be a general Markdown converter.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "draft.md"
OUTPUT = ROOT / "draft_lncs.tex"

# Figures whose natural width leaves too much vertical space are scaled down
# so the proceedings layout keeps a usable page budget.
FIGURE_PLACEMENT = {
    "fig2_state_machine.png": "tb",
    "fig3_overhead.png": "tb",
}

FIGURE_WIDTH = {
    "fig2_state_machine.png": 0.79,
    "fig3_overhead.png": 0.68,
}

# Per-table column specification. Tables default to equal-width X columns, but
# a table whose columns carry very different amounts of text (a label next to a
# sentence, or a run of three numbers next to a metric name) needs explicit
# widths, otherwise the label column is as wide as the sentence column and the
# text wraps mid-word. Keys are table numbers in document order.
TABLE_COLUMNS = {
    1: r"@{}cXp{2.6cm}c>{\raggedright\arraybackslash}X@{}",
    2: r"@{}l>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X@{}",
    4: r"@{}lcXp{2.6cm}@{}",
    5: r"@{}l>{\raggedright\arraybackslash}p{1.9cm}>{\raggedright\arraybackslash}p{3.2cm}>{\raggedright\arraybackslash}p{2.4cm}>{\raggedright\arraybackslash}X@{}",
    6: r"@{}l>{\raggedright\arraybackslash}p{3.8cm}>{\raggedright\arraybackslash}p{3.6cm}c@{}",
    7: r"@{}lXXc@{}",
}


CITATION_KEYS = {
    # Position in the reference list. LNCS orders the list alphabetically by
    # author, so these keys follow that order rather than citation order.
    "1": "acps2026repo",
    "2": "conformal2021",
    "3": "struq2024",
    "4": "debenedetti2024agentdojo",
    "5": "camel2025",
    "6": "interop2025",
    "7": "geifman2017selective",
    "8": "geng2023grammar",
    "9": "greshake2023indirect",
    "10": "guo2017calibration",
    "11": "oauth2012",
    "12": "helland2012idempotence",
    "13": "kim2026scaling",
    "14": "li2025acps",
    "15": "liu2025acps",
    "16": "liu2024promptinjection",
    "17": "maestro2026",
    "18": "toolemu2023",
    "19": "saltzer1975protection",
    "20": "progent2025",
    "21": "tam2024format",
    "22": "agentspec2025",
    "23": "isolategpt2024",
    "24": "guardagent2024",
    "25": "injecagent2024",
}


def tex_escape(text: str) -> str:
    """Escape ordinary text while retaining a few useful Unicode glyphs."""

    text = (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("~", r"\textasciitilde{}")
        .replace("^", r"\textasciicircum{}")
        .replace("–", "--")
        .replace("—", "---")
        .replace("“", "``")
        .replace("”", "''")
        .replace("’", "'")
    )
    return text


def inline(text: str) -> str:
    """Convert the inline Markdown used in the manuscript."""

    held: dict[str, str] = {}

    def hold(value: str) -> str:
        token = f"QXHOLD{len(held)}XQ"
        held[token] = value
        return token

    # Links, inline code, math, bold, and italics are held before escaping.
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: hold(r"\href{" + m.group(2) + "}{" + tex_escape(m.group(1)) + "}"),
        text,
    )
    def code(match: re.Match[str]) -> str:
        raw = match.group(1).replace("→", "->")
        # Long identifiers and hashes have no hyphenation points; cut them into
        # short runs so a paragraph can break inside a code span.
        raw = re.sub(
            r"[A-Za-z0-9._\-]{16,}",
            lambda m: "QXB".join(m.group(0)[i:i + 8] for i in range(0, len(m.group(0)), 8)),
            raw,
        )
        body = tex_escape(raw)
        # File paths and identifiers have no hyphenation points, so insert an
        # explicit break opportunity after separators to avoid overfull lines.
        body = body.replace("/", "/\\allowbreak{}").replace(r"\_", r"\_\allowbreak{}")
        body = body.replace("QXB", r"\allowbreak{}")
        return hold(r"\texttt{" + body + "}")

    text = re.sub(r"`([^`]+)`", code, text)
    text = re.sub(r"\$([^$]+)\$", lambda m: hold(r"\(" + m.group(1) + r"\)"), text)
    text = re.sub(r"\*\*([^*]+)\*\*", lambda m: hold(r"\textbf{" + inline(m.group(1)) + "}"), text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", lambda m: hold(r"\emph{" + inline(m.group(1)) + "}"), text)

    def citations(match: re.Match[str]) -> str:
        keys = [CITATION_KEYS[n.strip()] for n in match.group(1).split(",") if n.strip() in CITATION_KEYS]
        return hold(r"\cite{" + ",".join(keys) + "}") if keys else match.group(0)

    text = re.sub(r"\[([0-9]+(?:\s*,\s*[0-9]+)*)\]", citations, text)
    text = text.replace("→", hold(r"\(\rightarrow\)"))
    text = tex_escape(text)
    for token, value in held.items():
        text = text.replace(token, value)
    return text


def strip_caption(label: str) -> str:
    label = re.sub(r"^Fig\.\s*\d+\.\s*", "", label)
    label = re.sub(r"^Table\s*\d+\.\s*", "", label)
    label = re.sub(r"^\*\*|\*\*$", "", label)
    return label.strip()


def table_block(lines: list[str], caption: str | None, number: int) -> list[str]:
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if cells:
            rows.append(cells)
    if not rows:
        return []
    cols = max(len(row) for row in rows)
    out = [r"\begin{table}[htbp]", r"\centering", r"\small"]
    out.append(rf"\caption{{{inline(strip_caption(caption or f'Table {number}.'))}}}\label{{tab:{number}}}")
    spec = TABLE_COLUMNS.get(number, rf"@{{}}*{{{cols}}}{{X}}@{{}}")
    out.append(rf"\begin{{tabularx}}{{\textwidth}}{{{spec}}}")
    out.append(r"\toprule")
    for index, row in enumerate(rows):
        values = [inline(row[i] if i < len(row) else "") for i in range(cols)]
        if index == 0:
            values = [r"\textbf{" + value + "}" for value in values]
        out.append(" & ".join(values) + r" \\")
        if index == 0:
            out.append(r"\midrule")
    out.extend([r"\bottomrule", r"\end{tabularx}", r"\end{table}"])
    return out


def figure_block(alt: str, path: str, number: int) -> list[str]:
    caption = strip_caption(alt)
    safe_path = path.replace("\\", "/")
    width = FIGURE_WIDTH.get(Path(safe_path).name, 1.0)
    placement = FIGURE_PLACEMENT.get(Path(safe_path).name, "t")
    spec = r"\textwidth" if width == 1.0 else rf"{width}\textwidth"
    return [
        r"\begin{figure}[" + placement + "]",
        r"\centering",
        rf"\includegraphics[width={spec}]{{{safe_path}}}",
        rf"\caption{{{inline(caption)}}}\label{{fig:{number}}}",
        r"\end{figure}",
    ]


def bibliography() -> list[str]:
    """Render the Markdown reference list so citations and entries cannot drift.

    The previous implementation hard-coded nine entries; that silently broke
    when the manuscript added sources.  The Markdown reference list is now the
    single source of truth for both the numbering and the entry text.
    """
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    start = lines.index("## References")
    pattern = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")
    entries: list[tuple[int, str]] = []
    for line in lines[start + 1:]:
        match = pattern.match(line.strip())
        if match:
            entries.append((int(match.group(1)), match.group(2)))
    out = [rf"\begin{{thebibliography}}{{{len(entries)}}}", r"\small", r"\setlength{\itemsep}{0pt}", r"\setlength{\parskip}{0pt}"]
    for number, text in entries:
        key = CITATION_KEYS.get(str(number), f"ref{number}")
        out.append(rf"\bibitem{{{key}}} {inline(text)}")
    out.append(r"\end{thebibliography}")
    return out


def convert() -> str:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    title = lines[0].removeprefix("# ").strip()
    abstract_start = lines.index("## Abstract") + 1
    abstract_end = lines.index("## 1. Introduction")
    abstract_lines = [line.strip() for line in lines[abstract_start:abstract_end] if line.strip()]
    abstract = " ".join(line for line in abstract_lines if not line.startswith("**Keywords:**"))
    keyword_line = next(line for line in abstract_lines if line.startswith("**Keywords:**"))
    keywords = keyword_line.removeprefix("**Keywords:**").strip()

    out = [
        r"\documentclass[runningheads]{llncs}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{newtxtext}",
        r"\usepackage[varvw]{newtxmath}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{tabularx}",
        r"\usepackage{array}",
        r"\usepackage{hyperref}",
        # Float parameters: allow a page to carry its figures and text without
        # leaving large gaps when a tall figure is deferred.
        r"\setcounter{topnumber}{4}",
        r"\setcounter{bottomnumber}{3}",
        r"\setcounter{totalnumber}{6}",
        r"\renewcommand{\topfraction}{0.95}",
        r"\renewcommand{\bottomfraction}{0.6}",
        r"\renewcommand{\textfraction}{0.05}",
        r"\renewcommand{\floatpagefraction}{0.7}",
        r"\urlstyle{rm}",
        r"\begin{document}",
        rf"\title{{{inline(title)}}}",
        r"\titlerunning{Typed Judgment, Deterministic Enforcement}",
        r"\author{Yizhang Cai\inst{1} \and Jun Liu\inst{1} \and Di Ma\inst{2} \and Ke Yu\inst{1} \and Ke Li\inst{1}}",
        r"\authorrunning{Y. Cai et al.}",
        r"\institute{School of Artificial Intelligence, Beijing University of Posts and Telecommunications, Beijing, China \\ \email{liujun@bupt.edu.cn}, \email{like1990@bupt.edu.cn} (corresponding author) \and Beijing Guoshu Zhilian Technology Co., Ltd., Beijing, China \\ \email{madi@guoshuzhilian.com.cn}}",
        r"\maketitle",
        r"\begin{abstract}",
        inline(abstract),
        rf"\keywords{{{inline(keywords)}}}",
        r"\end{abstract}",
    ]

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
        raw = lines[i]
        stripped = raw.strip()
        if stripped == "## References":
            flush_paragraph()
            close_list()
            out.extend(bibliography())
            break
        if not stripped:
            flush_paragraph()
            close_list()
            i += 1
            continue
        table_caption = re.fullmatch(r"\*\*Table\s+\d+\.\*\*\s*(.*)", stripped)
        if table_caption:
            flush_paragraph()
            close_list()
            pending_caption = table_caption.group(1).strip()
            i += 1
            continue
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image:
            flush_paragraph()
            close_list()
            figure_number += 1
            out.extend(figure_block(image.group(1), image.group(2), figure_number))
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
            out.append(rf"\item {inline(re.sub(r'^\d+\.\s+', '', stripped))}")
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
            # Emit the environment as one block: the writer joins elements
            # with blank lines, and a blank line inside math mode is fatal.
            out.append("\n".join([
                r"\begin{equation}",
                stripped[1:-1],
                r"\end{equation}",
            ]))
            i += 1
            continue
        paragraph.append(stripped)
        i += 1
    flush_paragraph()
    close_list()
    out.extend([r"\end{document}"])
    return "\n\n".join(out) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(convert(), encoding="utf-8")
    print(OUTPUT)
