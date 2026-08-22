#!/usr/bin/env python3
"""No-billed-call regression loop for the backend hardening pass.

This script uses local PDFs, TestClient, direct DB fixtures, and mocks for any
model-facing path. It is safe to run repeatedly and is intended to run before
any real DashScope/Qwen validation.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = Path(tempfile.mkdtemp(prefix="rubriceye_hardening_"))
os.environ["RUBRICEYE_DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["RUBRICEYE_DASHSCOPE_API_KEY"] = ""

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import AnswerSheet, GradingResult  # noqa: E402
from app.main import app  # noqa: E402
from app.services import alignment, template_derivation  # noqa: E402


def make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 100), text, fontsize=16)
    payload = document.tobytes()
    document.close()
    return payload


def project_files():
    return {
        "rubric": ("rubric.pdf", io.BytesIO(make_pdf("Question 1 [4]\nCriteria")), "application/pdf"),
        "question_paper": ("question_paper.pdf", io.BytesIO(make_pdf("Maximum Marks: 4\nQuestion 1")), "application/pdf"),
        "blank_booklet": ("blank_booklet.pdf", io.BytesIO(make_pdf("Blank booklet")), "application/pdf"),
    }


def test_template_gating() -> None:
    boxes = [[10, 10, 100, 100], [10, 120, 100, 220]]
    assert template_derivation._assign_boxes_to_labels([], boxes) == []


def test_alignment_uses_detected_points() -> None:
    image_path = TEST_ROOT / "scan.png"
    cv2.imwrite(str(image_path), np.zeros((500, 500, 3), dtype=np.uint8))
    reference = {"pages": {"1": {"horizontal_lines": [10, 110, 210], "vertical_lines": [10, 110, 210], "width": 500, "height": 500}}}
    with patch.object(alignment, "_detect_lines", return_value=([20, 220, 420], [20, 220, 420])):
        matrix = alignment.compute_alignment_matrix(str(image_path), reference, 1)
    assert matrix is not None
    transformed = alignment.transform_bbox([10, 10, 20, 20], matrix)
    assert max(abs(value - expected) for value, expected in zip(transformed, [20, 20, 40, 40])) <= 2, transformed


def test_http_hardening() -> None:
    with TestClient(app) as client:
        response = client.post("/projects", data={"name": "Hardening Project"}, files=project_files())
        assert response.status_code == 201, response.text
        project_id = response.json()["id"]

        # Unknown membership is rejected; known membership can be grouped once.
        response = client.post(f"/projects/{project_id}/question-groups", json={"group_name": "Unknown", "selection_type": "compulsory", "question_numbers": ["999"]})
        assert response.status_code == 422, response.text
        response = client.post(f"/projects/{project_id}/question-bank", params={"question_number": "1", "marks_possible": -1, "key_points": "Criterion"})
        assert response.status_code == 422, response.text
        response = client.post(f"/projects/{project_id}/question-bank", params={"question_number": "1", "marks_possible": 4, "key_points": "Criterion"})
        assert response.status_code in (201, 409), response.text
        response = client.post(f"/projects/{project_id}/question-bank", params={"question_number": "1", "marks_possible": 4, "key_points": "Duplicate"})
        assert response.status_code == 409, response.text
        response = client.post(f"/projects/{project_id}/question-groups", json={"group_name": "Section A", "selection_type": "compulsory", "question_numbers": ["1"]})
        assert response.status_code == 201, response.text
        response = client.post(f"/projects/{project_id}/question-groups", json={"group_name": "Overlap", "selection_type": "compulsory", "question_numbers": ["1"]})
        assert response.status_code == 409, response.text

        # Inject one local result so score-bound checks can run without grading API calls.
        with SessionLocal() as db:
            sheet = AnswerSheet(id="hardening-sheet", project_id=project_id, roll_number="LOCAL-1", original_pdf_path="local.pdf", page_image_paths_json="[]", question_region_map_json="{}", grading_status="review_required")
            db.add(sheet)
            db.add(GradingResult(id="hardening-result", answer_sheet_id=sheet.id, question_number="1", ai_score=2, ai_total_possible=4, part_scores_json="[]", flags_json="[]", confidence="high", ink_status="attempted", choice_status="graded", grading_status="complete"))
            db.commit()

        sheet_list = client.get(f"/projects/{project_id}/answer-sheets")
        assert sheet_list.status_code == 200, sheet_list.text
        assert sheet_list.json()[0]["grading_status"] == "review_required", sheet_list.json()
        base = f"/projects/{project_id}/answer-sheets/hardening-sheet/results/1/confirm"
        assert client.post(base, json={"human_confirmed_score": 5}).status_code == 422
        assert client.post(base, json={"human_confirmed_score": -1}).status_code == 422
        confirmed = client.post(base, json={"human_confirmed_score": 3, "human_reviewer_note": "Local check"})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["reviewed"] is True
        results = client.get(f"/projects/{project_id}/answer-sheets/hardening-sheet/results")
        assert results.status_code == 200
        assert results.json()["grading_status"] == "complete"

        # Soft delete, trash listing, restore, and permanent delete.
        assert client.delete(f"/projects/{project_id}").status_code == 204
        assert client.get(f"/projects/{project_id}").status_code == 404
        assert client.get(f"/projects/{project_id}/question-bank").status_code == 404
        assert client.get(f"/projects/{project_id}/question-groups").status_code == 404
        assert not any(item["id"] == project_id for item in client.get("/projects").json())
        assert any(item["id"] == project_id for item in client.get("/projects/trash").json())
        restored = client.post(f"/projects/{project_id}/restore")
        assert restored.status_code == 200, restored.text
        assert client.get(f"/projects/{project_id}").status_code == 200
        assert client.delete(f"/projects/{project_id}").status_code == 204
        assert client.delete(f"/projects/{project_id}/hard").status_code == 204
        assert client.get(f"/projects/{project_id}").status_code == 404

        # A preparation exception is recorded instead of escaping as a raw 500.
        with patch("app.routes.projects._run_template_derivation", side_effect=RuntimeError("simulated failure")):
            failed = client.post("/projects", data={"name": "Preparation Failure"}, files=project_files())
        assert failed.status_code == 201, failed.text
        assert failed.json()["template_map_status"] == "failed"
        assert failed.json()["template_map_error"]


def main() -> int:
    try:
        test_template_gating()
        test_alignment_uses_detected_points()
        test_http_hardening()
        print("Local backend hardening regression passed: no billed model calls used.")
        return 0
    finally:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
