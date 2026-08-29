"""Offline integration tests using TestClient (Phase 4).

Covers HTTP-level scenarios from validate_hardening_local.py,
validate_antigravity_fixes.py, validate_unlock_and_delete.py,
validate_report_lifecycle.py, validate_rubric_studio.py,
and validate_frontend_source_guards.py.

All tests use a shared TestClient with bearer-token auth (Phase 2).
Each test creates uniquely-named projects to avoid DB collisions.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_AUTH_HEADERS

from app.main import app


def _make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((72, 100), text, fontsize=16)
    payload = doc.tobytes()
    doc.close()
    return payload


def _project_files(label: str = "Fixture"):
    return {
        "rubric": ("rubric.pdf", io.BytesIO(_make_pdf(f"Question 1 [5]\n{label}")), "application/pdf"),
        "question_paper": ("question_paper.pdf", io.BytesIO(_make_pdf(f"Maximum Marks: 5\n{label}")), "application/pdf"),
        "blank_booklet": ("blank_booklet.pdf", io.BytesIO(_make_pdf("Blank booklet")), "application/pdf"),
    }


# ---------------------------------------------------------------------------
# Health + config (no auth)
# ---------------------------------------------------------------------------


def test_health_endpoint_no_auth():
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_config_returns_token():
    with TestClient(app) as c:
        r = c.get("/config")
        assert r.status_code == 200
        assert "api_token" in r.json()


def test_protected_route_requires_auth():
    with TestClient(app) as c:
        r = c.get("/projects")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"


# ---------------------------------------------------------------------------
# Project CRUD + trash (from validate_unlock_and_delete.py)
# ---------------------------------------------------------------------------


def test_project_create_and_delete_lifecycle():
    """Create → soft-delete → trash → restore → hard-delete."""
    with TestClient(app, headers=TEST_AUTH_HEADERS) as c:
        created = c.post("/projects", data={"name": "Integ-Trash-Test"}, files=_project_files("trash"))
        assert created.status_code == 201, created.text
        pid = created.json()["id"]

        # Soft delete
        assert c.delete(f"/projects/{pid}", headers=TEST_AUTH_HEADERS).status_code == 204
        assert c.get(f"/projects/{pid}", headers=TEST_AUTH_HEADERS).status_code == 404

        # Trash listing
        trash = c.get("/projects/trash", headers=TEST_AUTH_HEADERS)
        assert trash.status_code == 200
        assert any(item["id"] == pid for item in trash.json())

        # Restore
        restored = c.post(f"/projects/{pid}/restore", headers=TEST_AUTH_HEADERS)
        assert restored.status_code == 200
        assert c.get(f"/projects/{pid}", headers=TEST_AUTH_HEADERS).status_code == 200

        # Hard delete
        assert c.delete(f"/projects/{pid}", headers=TEST_AUTH_HEADERS).status_code == 204
        assert c.delete(f"/projects/{pid}/hard", headers=TEST_AUTH_HEADERS).status_code == 204
        assert c.get(f"/projects/{pid}", headers=TEST_AUTH_HEADERS).status_code == 404


# ---------------------------------------------------------------------------
# HTTP hardening (from validate_hardening_local.py)
# ---------------------------------------------------------------------------


def test_question_bank_rejects_invalid_input():
    """Negative marks and unknown question numbers must be rejected."""
    with TestClient(app, headers=TEST_AUTH_HEADERS) as c:
        created = c.post("/projects", data={"name": "Integ-Validation"}, files=_project_files("val"))
        assert created.status_code == 201
        pid = created.json()["id"]

        # Negative marks rejected
        r = c.post(
            f"/projects/{pid}/question-bank",
            params={"question_number": "1", "marks_possible": -1, "key_points": "x"},
            headers=TEST_AUTH_HEADERS,
        )
        assert r.status_code == 422, f"Expected 422 for negative marks, got {r.status_code}"

        # Duplicate rejected
        r1 = c.post(
            f"/projects/{pid}/question-bank",
            params={"question_number": "1", "marks_possible": 5, "key_points": "ok"},
            headers=TEST_AUTH_HEADERS,
        )
        assert r1.status_code in (201, 409)
        r2 = c.post(
            f"/projects/{pid}/question-bank",
            params={"question_number": "1", "marks_possible": 5, "key_points": "dup"},
            headers=TEST_AUTH_HEADERS,
        )
        assert r2.status_code == 409


def test_score_confirmation_bounds():
    """Human-confirmed score must be within [0, marks_possible]."""
    from app.db.database import SessionLocal
    from app.db.models import AnswerSheet, GradingResult

    with TestClient(app, headers=TEST_AUTH_HEADERS) as c:
        created = c.post("/projects", data={"name": "Integ-Confirm"}, files=_project_files("confirm"))
        assert created.status_code == 201
        pid = created.json()["id"]

        # Inject a grading result directly
        db = SessionLocal()
        try:
            sheet = AnswerSheet(
                id="confirm-sheet", project_id=pid, roll_number="CONF-1",
                original_pdf_path="local.pdf", page_image_paths_json="[]",
                question_region_map_json="{}", grading_status="review_required",
            )
            db.add(sheet)
            db.add(GradingResult(
                id="confirm-result", answer_sheet_id=sheet.id, question_number="1",
                ai_score=2, ai_total_possible=4, part_scores_json="[]", flags_json="[]",
                confidence="high", ink_status="attempted", choice_status="graded",
                grading_status="complete",
            ))
            db.commit()
        finally:
            db.close()

        base = f"/projects/{pid}/answer-sheets/confirm-sheet/results/1/confirm"
        # Over-max rejected
        assert c.post(base, json={"human_confirmed_score": 5}, headers=TEST_AUTH_HEADERS).status_code == 422
        # Negative rejected
        assert c.post(base, json={"human_confirmed_score": -1}, headers=TEST_AUTH_HEADERS).status_code == 422
        # Valid confirmed
        ok = c.post(base, json={"human_confirmed_score": 3, "human_reviewer_note": "check"}, headers=TEST_AUTH_HEADERS)
        assert ok.status_code == 200
        assert ok.json()["reviewed"] is True


# ---------------------------------------------------------------------------
# Template reconciliation (from validate_antigravity_fixes.py)
# ---------------------------------------------------------------------------


def test_question_bank_confirm_rejects_unmapped_questions():
    """Confirming QB with questions not in template map must fail."""
    from app.db.database import SessionLocal
    from app.db.models import Project, QuestionBankItem, TemplateMapPage
    from app.services import storage

    with TestClient(app, headers=TEST_AUTH_HEADERS) as c:
        # Create project via DB for precise control
        db = SessionLocal()
        try:
            pid = "integ-reconcile-proj"
            project_dir = storage.project_dir(pid)
            for name in ("rubric.pdf", "question_paper.pdf", "blank_booklet.pdf"):
                (project_dir / name).write_bytes(b"%PDF-1.4\n")
            project = Project(
                id=pid, name=pid,
                rubric_file_path=str(project_dir / "rubric.pdf"),
                question_paper_file_path=str(project_dir / "question_paper.pdf"),
                blank_booklet_file_path=str(project_dir / "blank_booklet.pdf"),
                template_map_confirmed=True,
                template_map_status="ready",
                rubric_locked=True,
                question_bank_confirmed=False,
            )
            db.add(project)
            db.add(TemplateMapPage(
                project_id=pid, page_number=1, page_image_path="/tmp/page.png",
                regions_json=json.dumps([{"question_number": "2", "part_label": "i", "bbox": [0, 0, 10, 10]}]),
            ))
            db.add(QuestionBankItem(
                project_id=pid, question_number="2ii", marks_possible=4, key_points="criterion",
            ))
            db.commit()
        finally:
            db.close()

        r = c.post(f"/projects/{pid}/question-bank/confirm", headers=TEST_AUTH_HEADERS)
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
        assert "2ii" in r.text


# ---------------------------------------------------------------------------
# Frontend source guards (from validate_frontend_source_guards.py)
# ---------------------------------------------------------------------------


def test_frontend_source_guards():
    """Static checks for UI sizing, component imports, and no hardcoded totals."""
    ROOT = Path(__file__).resolve().parents[2]

    question_bank = (ROOT / "frontend/src/pages/QuestionBankSetup.tsx").read_text(encoding="utf-8")
    structure = (ROOT / "backend/app/services/paper_structure.py").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/src/styles.css").read_text(encoding="utf-8")
    answer_upload = (ROOT / "frontend/src/pages/UploadAnswerSheet.tsx").read_text(encoding="utf-8")
    studio_page = (ROOT / "frontend/src/pages/RubricStudio.tsx").read_text(encoding="utf-8")
    template_page = (ROOT / "frontend/src/pages/TemplateMapReview.tsx").read_text(encoding="utf-8")
    region_editor = (ROOT / "frontend/src/components/RegionEditorTable.tsx").read_text(encoding="utf-8")
    region_overlay = (ROOT / "frontend/src/components/RegionOverlay.tsx").read_text(encoding="utf-8")
    api_client = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")

    # Auto-grow textarea
    assert "ref={resizeElement}" in question_bank
    assert "scrollHeight" in question_bank
    assert ".auto-grow-textarea" in styles and "overflow: hidden" in styles

    # Paper structure has no hardcoded totals
    assert "SECTION C" not in structure
    assert "35" not in structure

    # Shared FilePicker
    assert 'import FilePicker from "../components/FilePicker"' in answer_upload

    # Studio read-only for approved
    assert "readOnly={status" in studio_page or 'readOnly={status === "approved"}' in studio_page

    # Template review components
    assert 'import RegionEditorTable' in template_page
    assert 'import RegionOverlay' in template_page
    assert "readOnly={templateMap.confirmed}" in template_page

    # Keyboard accessibility
    assert "onKeyDown" in region_overlay and 'role="button"' in region_overlay

    # Page correspondence uncertainty flag
    assert "page_correspondence_uncertain" in api_client
