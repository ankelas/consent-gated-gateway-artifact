"""Build a readable review DOCX from the Markdown manuscript."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "draft.md"
OUTPUT = ROOT / "draft.docx"


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)


def add_inline(paragraph, text: str) -> None:
    tokens = re.split(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)", text)
    for token in tokens:
        if not token:
            continue
        if token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        elif token.startswith("**") and token.endswith("**"):
            paragraph.add_run(token[2:-2]).bold = True
        elif token.startswith("*") and token.endswith("*"):
            paragraph.add_run(token[1:-1]).italic = True
        else:
            paragraph.add_run(token)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def _apply_east_asian_font(run, ea_font: str) -> None:
    """Tag a run with an East Asian font so CJK text does not fall back."""
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), ea_font)


def apply_east_asian_fonts(doc, ea_font: str) -> None:
    for style_name in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3"):
        style = doc.styles[style_name]
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), ea_font)
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            _apply_east_asian_font(run, ea_font)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        _apply_east_asian_font(run, ea_font)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--ea-font", default="SimSun")
    parser.add_argument("--footer", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--subject", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    is_chinese = "_zh" in args.source.stem
    if args.footer is None:
        args.footer = (
            "中文初稿 | 仅为仿真器试点" if is_chinese
            else "Core paired simulator study | No live controlled evaluation"
        )
    if args.subject is None and is_chinese:
        args.subject = "含仿真器试点的论文初稿；尚无线上受控评测"
    lines = args.source.read_text(encoding="utf-8").splitlines()
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.72)
    section.bottom_margin = Inches(0.72)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.12
    for name, size in (("Title", 18), ("Heading 1", 14), ("Heading 2", 12), ("Heading 3", 11)):
        style = doc.styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.keep_with_next = True

    i = 0
    in_code = False
    code_lines: list[str] = []
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code:
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.22)
                p.paragraph_format.space_before = Pt(3)
                p.paragraph_format.space_after = Pt(7)
                run = p.add_run("\n".join(code_lines))
                run.font.name = "Consolas"
                run.font.size = Pt(8.5)
                code_lines = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(raw)
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        image_match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            alt, image_path = image_match.groups()
            resolved = (args.source.parent / image_path).resolve()
            if resolved.exists():
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.keep_with_next = True
                run = p.add_run()
                inline_shape = run.add_picture(str(resolved), width=Inches(6.35))
                # Populate the OOXML description so screen readers and the
                # document accessibility audit can identify each figure.
                inline_shape._inline.docPr.set("descr", alt)
                inline_shape._inline.docPr.set("title", alt)
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap.paragraph_format.space_before = Pt(2)
                cap.paragraph_format.space_after = Pt(6)
                caption_run = cap.add_run(alt)
                caption_run.font.name = "Times New Roman"
                caption_run.font.size = Pt(9)
            i += 1
            continue
        if stripped in {"**Yizhang Cai**", "**蔡亦张（Yizhang Cai）**"}:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(stripped[2:-2])
            run.bold = True
            run.font.name = "Times New Roman"
            run.font.size = Pt(11)
            i += 1
            continue
        if stripped.startswith("School of Artificial Intelligence,") or stripped.startswith("北京邮电大学人工智能学院"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(8)
            run = p.add_run(stripped)
            run.font.name = "Times New Roman"
            run.font.size = Pt(9.5)
            i += 1
            continue
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            rows = []
            for line in table_lines:
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    continue
                rows.append(cells)
            if rows:
                cols = max(len(row) for row in rows)
                table = doc.add_table(rows=len(rows), cols=cols)
                table.style = "Table Grid"
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                table.autofit = True
                for ridx, row in enumerate(rows):
                    for cidx in range(cols):
                        cell = table.cell(ridx, cidx)
                        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                        p = cell.paragraphs[0]
                        p.paragraph_format.space_after = Pt(1)
                        p.paragraph_format.line_spacing = 1.0
                        add_inline(p, row[cidx] if cidx < len(row) else "")
                        for run in p.runs:
                            run.font.size = Pt(8.5)
                        if ridx == 0:
                            set_cell_shading(cell, "DDE8E4")
                            for run in p.runs:
                                run.bold = True
                set_repeat_table_header(table.rows[0])
                doc.add_paragraph().paragraph_format.space_after = Pt(1)
            continue
        if stripped.startswith("# "):
            p = doc.add_paragraph(style="Title")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_inline(p, stripped[2:])
        elif stripped.startswith("### "):
            p = doc.add_paragraph(style="Heading 2")
            add_inline(p, stripped[4:])
        elif stripped.startswith("## "):
            p = doc.add_paragraph(style="Heading 1")
            add_inline(p, stripped[3:])
        elif stripped.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            add_inline(p, stripped[2:])
        elif re.match(r"\d+\.\s", stripped):
            p = doc.add_paragraph(style="List Number")
            add_inline(p, re.sub(r"^\d+\.\s", "", stripped))
        else:
            p = doc.add_paragraph()
            add_inline(p, stripped)
        i += 1

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run(args.footer)
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(90, 90, 90)
    title = args.title or doc.paragraphs[0].text
    doc.core_properties.title = title
    doc.core_properties.subject = args.subject or (
        "Live deployment study: routing and invariant ablations on an iMessage/ACPs gateway"
    )
    apply_east_asian_fonts(doc, args.ea_font)
    doc.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
