#!/usr/bin/env python3
"""Verify bounded PDF validation rejects malformed inputs before filesystem side effects."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(tempfile.mkdtemp(prefix="rubriceye_pdf_input_"))
os.environ["RUBRICEYE_DATA_DIR"] = str(ROOT / "data")
os.environ["RUBRICEYE_DASHSCOPE_API_KEY"] = ""

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.pdf_validation import validate_pdf_bytes  # noqa: E402
from real_fixture_paths import BLANK, QUESTION_PAPER, RUBRIC, answer_books  # noqa: E402


def _assert_http_error(response, status: int, fragment: str):
    assert response.status_code == status, response.text
    assert fragment in response.json()["detail"], response.text


def main() -> int:
    try:
        _assert_http_error_response = None
        for data, status, fragment in (
            (b"not-a-pdf", 400, "not a valid PDF"),
            (b"%PDF-1.7\ncorrupt", 400, "could not be opened"),
            (b"%PDF-" + b"x" * (settings.max_pdf_bytes + 1), 413, "PDF limit"),
        ):
            try:
                validate_pdf_bytes(data, "Fixture")
            except Exception as exc:
                assert getattr(exc, "status_code", None) == status, exc
                assert fragment in str(getattr(exc, "detail", exc)), exc
            else:
                raise AssertionError(f"Expected local validation failure for {fragment}")

        with TestClient(app) as client:
            invalid_project = client.post(
                "/projects",
                data={"name": "Invalid PDF Check"},
                files={
                    "rubric": ("rubric.pdf", b"not-a-pdf", "application/pdf"),
                    "question_paper": ("paper.pdf", b"not-a-pdf", "application/pdf"),
                    "blank_booklet": ("blank.pdf", b"not-a-pdf", "application/pdf"),
                },
            )
            _assert_http_error(invalid_project, 400, "not a valid PDF")
            assert not list((ROOT / "data" / "projects").glob("*/")), "invalid project created an artifact"

            fixtures = answer_books()
            with RUBRIC.open("rb") as rubric, QUESTION_PAPER.open("rb") as question_paper, BLANK.open("rb") as blank:
                created = client.post(
                    "/projects",
                    data={"name": "Answer Input Check"},
                    files={
                        "rubric": (RUBRIC.name, rubric, "application/pdf"),
                        "question_paper": (QUESTION_PAPER.name, question_paper, "application/pdf"),
                        "blank_booklet": (BLANK.name, blank, "application/pdf"),
                    },
                )
            assert created.status_code == 201, created.text
            project_id = created.json()["id"]
            assert client.post(f"/projects/{project_id}/template-map/confirm").status_code == 200
            invalid_answer = client.post(
                f"/projects/{project_id}/answer-sheets",
                data={"roll_number": "bad-pdf"},
                files={"pdf": ("answer.pdf", b"not-a-pdf", "application/pdf")},
            )
            _assert_http_error(invalid_answer, 400, "not a valid PDF")
            assert client.get(f"/projects/{project_id}/answer-sheets").json() == []
            answer_root = ROOT / "data" / "projects" / project_id / "answer_sheets"
            assert not answer_root.exists() or not list(answer_root.iterdir()), "invalid answer created an artifact"

        print("PDF input hardening regression passed: bad magic, corrupt bytes, oversized bytes, invalid project upload, and invalid answer upload are rejected without orphan artifacts.")
        return 0
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
