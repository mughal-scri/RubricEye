from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.storage import atomic_write_bytes
from app.services.question_grouping import sort_records_by_question


_BULLET_SPLIT = re.compile(r"(?:^|\n)\s*(?:[•●▪‣*-]|\d+[.)])\s*")


def _safe_text(value: object | None) -> str:
    return str(value or "").strip()


def _criteria_points(text: str) -> list[str]:
    value = _safe_text(text)
    if not value:
        return ["No criterion supplied; examiner review is required."]
    chunks = [chunk.strip(" \t\r\n•●▪‣*-·") for chunk in _BULLET_SPLIT.split(value)]
    points = [chunk for chunk in chunks if chunk]
    return points or [value]


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    escaped = (
        _safe_text(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    return Paragraph(escaped, style)


def _ordered_criteria(criteria: Iterable[dict]) -> list[dict]:
    filtered = [item for item in criteria if _safe_text(item.get("question_number"))]
    return sort_records_by_question(filtered, lambda item: _safe_text(item.get("question_number")))


def render_rubric_pdf(destination: Path, *, project_name: str, source_label: str, criteria: Iterable[dict]) -> Path:
    """Render an examiner-editable rubric into a structured PDF.

    The renderer never invents question identifiers or marks. It uses the ordered
    criteria supplied by paper extraction or the examiner, so labels such as
    ``2i`` or ``3(a)`` remain exactly as they appeared in the source data.
    """
    ordered = _ordered_criteria(criteria)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "RubricTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17,
        leading=21, alignment=TA_CENTER, textColor=colors.HexColor("#17212b"), spaceAfter=3 * mm,
    )
    subtitle = ParagraphStyle(
        "RubricSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9,
        leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#52606d"), spaceAfter=6 * mm,
    )
    section = ParagraphStyle(
        "RubricSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11,
        leading=14, textColor=colors.HexColor("#1745c2"), spaceBefore=4 * mm, spaceAfter=2 * mm,
    )
    question = ParagraphStyle(
        "RubricQuestion", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10,
        leading=13, textColor=colors.HexColor("#17212b"), spaceBefore=2 * mm, spaceAfter=1.5 * mm,
    )
    body = ParagraphStyle(
        "RubricBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.7,
        leading=12, textColor=colors.HexColor("#293845"), spaceAfter=1.5 * mm,
    )
    question_prompt = ParagraphStyle(
        "RubricQuestionPrompt", parent=body, fontName="Helvetica-Oblique", fontSize=8.6,
        leading=11.5, textColor=colors.HexColor("#52606d"), spaceAfter=1.5 * mm,
    )
    bullet = ParagraphStyle(
        "RubricBullet", parent=body, leftIndent=5 * mm, firstLineIndent=-3 * mm,
        bulletIndent=1.5 * mm, spaceAfter=1 * mm,
    )
    small = ParagraphStyle(
        "RubricSmall", parent=body, fontSize=7.5, leading=10, textColor=colors.HexColor("#667583"),
    )

    story: list[object] = [
        _paragraph(_safe_text(project_name) or "RubricEye Assessment", title),
        _paragraph("Structured marking rubric", subtitle),
    ]
    metadata = Table(
        [[_paragraph("Source", small), _paragraph(_safe_text(source_label) or "Question paper", small),
          _paragraph("Generated", small), _paragraph(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), small)]],
        colWidths=[18 * mm, 68 * mm, 22 * mm, 62 * mm],
    )
    metadata.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f6f8")),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#dfe5ea")),
        ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#e8edf0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([metadata, Spacer(1, 4 * mm), _paragraph("Marking criteria", section)])

    if not ordered:
        story.append(_paragraph("No criteria were supplied. Add criteria in Rubric Studio before using this file.", body))
    else:
        last_section = None
        for item in ordered:
            section_label = _safe_text(item.get("section_label"))
            if section_label and section_label != last_section:
                story.append(_paragraph(section_label, section))
                last_section = section_label
            label = _safe_text(item.get("question_number"))
            marks = item.get("marks_possible")
            marks_text = f" — {marks} marks" if isinstance(marks, int) else ""
            question_block = [_paragraph(f"{label}{marks_text}", question)]
            if _safe_text(item.get("question_text")):
                question_block.append(_paragraph(item.get("question_text"), question_prompt))
            for point in _criteria_points(_safe_text(item.get("key_points"))):
                question_block.append(_paragraph(f"• {point}", bullet))
            provenance = _safe_text(item.get("rubric_provenance"))
            confidence = _safe_text(item.get("rubric_confidence"))
            if provenance or confidence:
                source_note = " · ".join(part for part in (provenance, f"{confidence} confidence" if confidence else "") if part)
                question_block.append(_paragraph(f"Source note: {source_note}", small))
            story.append(KeepTogether(question_block))

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    document = SimpleDocTemplate(
        str(temporary), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title="RubricEye Structured Rubric",
        author="RubricEye",
    )
    document.build(story)
    return atomic_write_bytes(destination, temporary.read_bytes())


def render_text_rubric_pdf(destination: Path, *, project_name: str, rubric_text: str, source_label: str = "Examiner-supplied rubric text") -> Path:
    """Render pasted rubric text into a readable PDF without changing its labels or wording."""
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TextRubricTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=21, alignment=TA_CENTER, textColor=colors.HexColor("#17212b"), spaceAfter=2 * mm)
    subtitle = ParagraphStyle("TextRubricSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#52606d"), spaceAfter=6 * mm)
    body = ParagraphStyle("TextRubricBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=colors.HexColor("#293845"), spaceAfter=2 * mm)

    story: list[object] = [_paragraph(_safe_text(project_name) or "RubricEye Assessment", title), _paragraph(source_label, subtitle)]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", _safe_text(rubric_text)) if part.strip()]
    if not paragraphs:
        paragraphs = ["No rubric text supplied."]
    for paragraph in paragraphs:
        story.append(_paragraph(paragraph, body))

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    document = SimpleDocTemplate(str(temporary), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="RubricEye Supplied Rubric", author="RubricEye")
    document.build(story)
    return atomic_write_bytes(destination, temporary.read_bytes())
