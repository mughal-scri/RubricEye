from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.db.models import AnswerSheet, GradingResult, Project, QuestionGroup
from app.services import storage
from app.services.question_grouping import question_sort_key


def _safe_text(value: object | None) -> str:
    return str(value or "").strip()


def _markdown_escape(value: object) -> str:
    return _safe_text(value).replace("|", "\\|").replace("\n", " ")


def _is_reviewable(result: GradingResult) -> bool:
    return result.choice_status in ("graded", "flagged_ambiguous") and result.grading_status != "failed"


def _ordered_results(results: list[GradingResult]) -> list[GradingResult]:
    labels = [result.question_number for result in results]
    return sorted(results, key=lambda result: (*question_sort_key(result.question_number, labels), result.id))


def report_blockers(results: list[GradingResult]) -> list[str]:
    blockers: list[str] = []
    for result in _ordered_results(results):
        if result.grading_status == "failed":
            blockers.append(f"Q{result.question_number}: grading failed")
        elif _is_reviewable(result) and not result.reviewed:
            blockers.append(f"Q{result.question_number}: examiner confirmation missing")
    return blockers


def _decision(result: GradingResult) -> str:
    if result.choice_status == "skipped_blank":
        return "Not attempted — locked out"
    if result.choice_status == "skipped_beyond_n":
        return "Skipped by choice rule"
    if result.grading_status == "failed":
        return "Grading failed"
    if result.choice_status == "flagged_ambiguous":
        return "Examiner-confirmed ambiguous answer" if result.reviewed else "Ambiguous — review required"
    return "Examiner confirmed" if result.reviewed else "AI draft"


def _score(result: GradingResult) -> int | float | None:
    return result.human_confirmed_score if result.reviewed else result.ai_score


def _question_display(result: GradingResult, question_text_by_number: dict[str, str] | None) -> str:
    question = f"Q{result.question_number}"
    wording = _safe_text((question_text_by_number or {}).get(result.question_number))
    return f"{question}\n{wording}" if wording else question


def render_report(project: Project, sheet: AnswerSheet, results: list[GradingResult], groups: list[QuestionGroup], question_text_by_number: dict[str, str] | None = None) -> str:
    """Retain a plain-text representation for diagnostics; downloads use PDF."""
    ordered = _ordered_results(results)
    awarded = sum((_score(result) or 0) for result in ordered)
    possible = sum(result.ai_total_possible or 0 for result in ordered if _is_reviewable(result))
    lines = [
        f"# RubricEye Examiner Report — {_markdown_escape(project.name)}",
        "",
        f"- **Roll number:** {_markdown_escape(sheet.roll_number)}",
        f"- **Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"- **Confirmed total:** {awarded} / {possible}",
        "",
        "## Question decisions",
        "",
        "| Question | Decision | Attained | Possible | Examiner note |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for result in ordered:
        lines.append(
            f"| {_markdown_escape(_question_display(result, question_text_by_number))} | {_markdown_escape(_decision(result))} | "
            f"{_score(result) if _score(result) is not None else '—'} | "
            f"{result.ai_total_possible if result.ai_total_possible is not None else '—'} | "
            f"{_markdown_escape(result.human_reviewer_note)} |"
        )
    return "\n".join(lines) + "\n"


def _pdf_text(value: object | None, style: ParagraphStyle) -> Paragraph:
    escaped = (
        _safe_text(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    return Paragraph(escaped or "—", style)


def render_report_pdf(destination: Path, project: Project, sheet: AnswerSheet, results: list[GradingResult], groups: list[QuestionGroup], question_text_by_number: dict[str, str] | None = None) -> Path:
    """Render a durable, ordered examiner report PDF from reviewed grading data."""
    ordered = _ordered_results(results)
    awarded = sum((_score(result) or 0) for result in ordered)
    possible = sum(result.ai_total_possible or 0 for result in ordered if _is_reviewable(result))
    pages = len(json.loads(sheet.page_image_paths_json or "[]"))

    styles = getSampleStyleSheet()
    title = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=21, alignment=TA_CENTER, textColor=colors.HexColor("#17212b"), spaceAfter=2 * mm)
    subtitle = ParagraphStyle("ReportSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#52606d"), spaceAfter=6 * mm)
    heading = ParagraphStyle("ReportHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#1745c2"), spaceBefore=5 * mm, spaceAfter=2.5 * mm)
    body = ParagraphStyle("ReportBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#293845"))
    small = ParagraphStyle("ReportSmall", parent=body, fontSize=7.2, leading=9, textColor=colors.HexColor("#667583"))
    table_head = ParagraphStyle("ReportTableHead", parent=small, fontName="Helvetica-Bold", textColor=colors.HexColor("#40505d"))

    story: list[object] = [
        _pdf_text(project.name, title),
        _pdf_text("Examiner grading report", subtitle),
    ]
    summary = Table([
        [_pdf_text("Candidate / roll number", small), _pdf_text(sheet.roll_number, body), _pdf_text("Answer pages", small), _pdf_text(str(pages), body)],
        [_pdf_text("Generated", small), _pdf_text(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), body), _pdf_text("Status", small), _pdf_text("Examiner reviewed and completed", body)],
    ], colWidths=[34 * mm, 55 * mm, 26 * mm, 55 * mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f6f8")),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#dfe5ea")),
        ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#e8edf0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([summary, Spacer(1, 4 * mm), _pdf_text("Final score", heading), _pdf_text(f"{awarded} / {possible}", title), _pdf_text("The denominator includes only the selectable answer units that were eligible for grading. Blank and choice-excluded units are listed below as closed decisions.", small), _pdf_text("Question decisions", heading)])

    rows: list[list[Paragraph]] = [[_pdf_text("Question", table_head), _pdf_text("Decision", table_head), _pdf_text("Attained", table_head), _pdf_text("Possible", table_head), _pdf_text("Examiner note", table_head)]]
    for result in ordered:
        rows.append([
            _pdf_text(_question_display(result, question_text_by_number), body),
            _pdf_text(_decision(result), body),
            _pdf_text(_score(result), body),
            _pdf_text(result.ai_total_possible, body),
            _pdf_text(result.human_reviewer_note, small),
        ])
    table = Table(rows, colWidths=[53 * mm, 39 * mm, 18 * mm, 18 * mm, 50 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf0f4")),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#dfe5ea")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)

    notes = [_safe_text(result.human_reviewer_note) for result in ordered if _safe_text(result.human_reviewer_note)]
    story.extend([_pdf_text("Additional examiner notes", heading)])
    story.extend(_pdf_text(f"• {note}", body) for note in notes) if notes else story.append(_pdf_text("No additional examiner notes were recorded.", body))

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    document = SimpleDocTemplate(str(temporary), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title="RubricEye Examiner Report", author="RubricEye")
    document.build(story)
    return storage.atomic_write_bytes(destination, temporary.read_bytes())


def generate_report(project: Project, sheet: AnswerSheet, results: list[GradingResult], groups: list[QuestionGroup], question_text_by_number: dict[str, str] | None = None) -> Path:
    destination = storage.answer_sheet_dir(project.id, sheet.id) / "examiner_report.pdf"
    return render_report_pdf(destination, project, sheet, results, groups, question_text_by_number)
