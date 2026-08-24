#!/usr/bin/env python3
"""Verify local report generation and completion semantics without model calls."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import fitz

os.environ["RUBRICEYE_DATA_DIR"] = tempfile.mkdtemp(prefix="rubriceye_report_")

from fastapi.testclient import TestClient  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import AnswerSheet, GradingResult, Project, QuestionBankItem  # noqa: E402
from app.main import app  # noqa: E402


def main() -> int:
    with TestClient(app) as client:
        project_id = "report-project"
        sheet_id = "report-sheet"
        db = SessionLocal()
        project = Project(id=project_id, name="Report Check", rubric_file_path="rubric.pdf", question_paper_file_path="paper.pdf", blank_booklet_file_path="blank.pdf", template_map_confirmed=True, question_bank_confirmed=True)
        sheet = AnswerSheet(id=sheet_id, project_id=project_id, roll_number="R-01", original_pdf_path="answer.pdf", page_image_paths_json="[]", question_region_map_json="{}", grading_status="review_required")
        pending = GradingResult(id="pending-result", answer_sheet_id=sheet.id, question_number="1", ai_score=3, ai_total_possible=5, ai_rationale="draft", part_scores_json="[]", flags_json="[]", confidence="medium", ink_status="attempted", choice_status="graded", grading_status="complete", reviewed=False)
        ambiguous = GradingResult(id="ambiguous-result", answer_sheet_id=sheet.id, question_number="2", ai_score=None, ai_total_possible=4, ai_rationale=None, part_scores_json="[]", flags_json='["ambiguous ink density"]', confidence="low", ink_status="ambiguous", choice_status="flagged_ambiguous", grading_status="complete", reviewed=False)
        later = GradingResult(id="later-result", answer_sheet_id=sheet.id, question_number="10", ai_score=1, ai_total_possible=2, ai_rationale="draft", part_scores_json="[]", flags_json="[]", confidence="high", ink_status="attempted", choice_status="graded", grading_status="complete", reviewed=True, human_confirmed_score=1)
        q2 = QuestionBankItem(id="q2-item", project_id=project_id, question_number="2", marks_possible=4, key_points="Evidence", question_text="Explain the second question.")
        db.add_all([project, sheet, pending, ambiguous, later, q2])
        db.commit()
        db.close()

        blocked = client.post(f"/projects/{project_id}/answer-sheets/{sheet_id}/report")
        assert blocked.status_code == 409, blocked.text

        db = SessionLocal()
        pending = db.get(GradingResult, "pending-result")
        pending.reviewed = True
        pending.human_confirmed_score = 4
        pending.human_reviewer_note = "Confirmed after evidence review."
        ambiguous = db.get(GradingResult, "ambiguous-result")
        ambiguous.reviewed = True
        ambiguous.human_confirmed_score = 2
        ambiguous.human_reviewer_note = "Confirmed attempted after inspecting the answer image."
        db.commit()
        db.close()

        first = client.post(f"/projects/{project_id}/answer-sheets/{sheet_id}/report")
        assert first.status_code == 200, first.text
        payload = first.json()
        assert payload["report_ready"] is True
        assert payload["report_download_url"].endswith("examiner_report.pdf")
        downloadable = client.get(payload["report_download_url"])
        assert downloadable.status_code == 200, downloadable.text
        assert downloadable.headers["content-disposition"].startswith("attachment;")
        pdf_text = "\\n".join(page.get_text() for page in fitz.open(stream=downloadable.content, filetype="pdf"))
        assert "Report Check" in pdf_text and "Examiner grading report" in pdf_text
        assert "Explain the second question." in pdf_text
        assert pdf_text.index("Q1") < pdf_text.index("Q2") < pdf_text.index("Q10"), pdf_text

        second = client.post(f"/projects/{project_id}/answer-sheets/{sheet_id}/report")
        assert second.status_code == 200, second.text
        assert second.json()["report_download_url"] == payload["report_download_url"]

        report_path = Path(os.environ["RUBRICEYE_DATA_DIR"]) / "projects" / project_id / "answer_sheets" / sheet_id / "examiner_report.pdf"
        assert report_path.exists()
        document = fitz.open(report_path)
        text = "\\n".join(page.get_text() for page in document)
        document.close()
        assert "Confirmed total" not in text
        assert "Q1" in text and "Q2" in text and "Q10" in text and "Confirmed after evidence review." in text and "Confirmed attempted" in text
        assert text.index("Q1") < text.index("Q2") < text.index("Q10"), text
    print("Report lifecycle regression passed: incomplete graded/ambiguous review blocks generation and completed structured PDFs are durable/idempotent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
