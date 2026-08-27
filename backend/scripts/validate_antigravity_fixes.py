#!/usr/bin/env python3
"""No-cost regression checks for the Antigravity fix-instructions report."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np

os.environ["RUBRICEYE_DATA_DIR"] = tempfile.mkdtemp(prefix="rubriceye_antigravity_fixes_")

from fastapi.testclient import TestClient  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.models import AnswerSheet, GradingResult, Project, QuestionBankItem, TemplateMapPage  # noqa: E402
from app.services import storage  # noqa: E402
from app.services.segmentation import safe_region_filename_key  # noqa: E402
from app.main import app  # noqa: E402


def make_project(db, project_id: str, *, confirmed_map: bool = False) -> Project:
    project_dir = storage.project_dir(project_id)
    for name in ("rubric.pdf", "question_paper.pdf", "blank_booklet.pdf"):
        (project_dir / name).write_bytes(b"%PDF-1.4\n")
    project = Project(
        id=project_id,
        name=project_id,
        rubric_file_path=str(project_dir / "rubric.pdf"),
        question_paper_file_path=str(project_dir / "question_paper.pdf"),
        blank_booklet_file_path=str(project_dir / "blank_booklet.pdf"),
        template_map_confirmed=confirmed_map,
        template_map_status="ready" if confirmed_map else "pending",
        rubric_locked=True,
        question_bank_confirmed=False,
    )
    db.add(project)
    return project


def test_reconciliation(client: TestClient, db) -> None:
    project = make_project(db, "mismatch-project", confirmed_map=True)
    db.add(TemplateMapPage(project_id=project.id, page_number=1, page_image_path="/tmp/page.png", regions_json=json.dumps([{"question_number": "2", "part_label": "i", "bbox": [0, 0, 10, 10]}])))
    db.add(QuestionBankItem(project_id=project.id, question_number="2ii", marks_possible=4, key_points="criterion"))
    db.commit()
    response = client.post(f"/projects/{project.id}/question-bank/confirm")
    assert response.status_code == 409, response.text
    assert "2ii" in response.text and "confirmed template map" in response.text, response.text
    db.refresh(project)
    assert project.question_bank_confirmed is False


def test_sheet_lifecycle_and_crop(client: TestClient, db) -> None:
    project = make_project(db, "sheet-project", confirmed_map=False)
    project_dir = storage.project_dir(project.id)
    sheet_id = "sheet-1"
    sheet_dir = storage.answer_sheet_dir(project.id, sheet_id)
    page_path = sheet_dir / "page_001.png"
    image = np.full((160, 160, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (10, 10), (80, 80), (0, 0, 0), -1)
    cv2.imwrite(str(page_path), image)
    regions_dir = sheet_dir / "regions"
    regions_dir.mkdir(parents=True, exist_ok=True)
    old_crop = image[10:50, 10:50]
    crop_path = regions_dir / f"{safe_region_filename_key('2i')}_p1.png"
    cv2.imwrite(str(crop_path), old_crop)
    sheet = AnswerSheet(
        id=sheet_id,
        project_id=project.id,
        roll_number="A-1",
        original_pdf_path=str(sheet_dir / "original.pdf"),
        page_image_paths_json=json.dumps([str(page_path)]),
        question_region_map_json=json.dumps({"2i": [{"page_index": 0, "bbox": [10, 10, 50, 50], "nominal_bbox": [10, 10, 50, 50]}]}),
    )
    db.add(sheet)
    db.flush()
    db.add(GradingResult(answer_sheet_id=sheet.id, question_number="2i", ai_score=3, ai_total_possible=4, grading_status="complete", reviewed=True, choice_status="graded", part_scores_json="[]", flags_json="[]"))
    db.commit()

    assert client.get(f"/projects/{project.id}/answer-sheets").json()[0]["id"] == sheet_id
    assert client.delete(f"/projects/{project.id}/answer-sheets/{sheet_id}").status_code == 204
    assert client.get(f"/projects/{project.id}/answer-sheets").json() == []
    assert client.get(f"/projects/{project.id}/answer-sheets/trash").json()[0]["id"] == sheet_id
    assert client.get(f"/projects/{project.id}/answer-sheets/{sheet_id}").status_code == 404
    assert client.post(f"/projects/{project.id}/answer-sheets/{sheet_id}/restore").status_code == 200

    before = crop_path.read_bytes()
    response = client.put(f"/projects/{project.id}/answer-sheets/{sheet_id}/regions/2i", json={"bbox": [5, 5, 100, 100], "page_index": 0})
    assert response.status_code == 200, response.text
    assert crop_path.read_bytes() != before
    db.refresh(sheet)
    result = db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet_id).one()
    assert json.loads(sheet.question_region_map_json)["2i"][0]["bbox"] == [5, 5, 100, 100]
    assert result.grading_status == "pending" and result.reviewed is False and result.ai_score is None

    assert client.delete(f"/projects/{project.id}/answer-sheets/{sheet_id}").status_code == 204
    assert client.delete(f"/projects/{project.id}/answer-sheets/{sheet_id}/permanent").status_code == 204
    assert not sheet_dir.exists()
    assert client.get(f"/projects/{project.id}/answer-sheets/trash").json() == []


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        with TestClient(app) as client:
            test_reconciliation(client, db)
            test_sheet_lifecycle_and_crop(client, db)
    finally:
        db.close()
    print("Antigravity fixes regression passed: confirmation-time reconciliation, answer-sheet Trash lifecycle, scoped crop recrop, and stale-score reset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
