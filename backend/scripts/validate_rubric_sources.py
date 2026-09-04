#!/usr/bin/env python3
"""Verify rubric-source mode gating (upload/studio) and served rubric PDF behavior without provider calls."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import fitz

os.environ["RUBRICEYE_DATA_DIR"] = tempfile.mkdtemp(prefix="rubriceye_sources_")
# Deterministic token so this script can authenticate against its own TestClient
# (same approach as backend/tests/conftest.py); must be set before the app import.
API_TOKEN = "test-token-for-offline-tests"
os.environ["RUBRICEYE_API_TOKEN"] = API_TOKEN

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "test_fixtures_roman"
AUTH_HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}


def pdf_text(response) -> str:
    document = fitz.open(stream=response.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in document)
    document.close()
    return text


def main() -> int:
    files = {
        "rubric": ("rubric.pdf", (FIXTURES / "rubric.pdf").read_bytes(), "application/pdf"),
        "question_paper": ("question_paper.pdf", (FIXTURES / "question_paper.pdf").read_bytes(), "application/pdf"),
        "blank_booklet": ("blank_booklet.pdf", (FIXTURES / "blank_booklet.pdf").read_bytes(), "application/pdf"),
    }
    with TestClient(app) as client:
        # Text mode is no longer supported — even a well-formed text rubric must be rejected.
        text_rejected = client.post("/projects", data={"name": "Text Rubric Rejected", "rubric_mode": "text", "rubric_text": "Q2i — 4 marks"}, files=files, headers=AUTH_HEADERS)
        assert text_rejected.status_code == 400, f"Expected 400 for text mode, got {text_rejected.status_code}"
        assert "rubric_mode must be 'upload' or 'studio'" in text_rejected.text, text_rejected.text

        created = client.post("/projects", data={"name": "Upload Rubric Check", "rubric_mode": "upload"}, files=files, headers=AUTH_HEADERS)
        assert created.status_code == 201, created.text
        project = created.json()
        assert project["rubric_source_mode"] == "upload", project
        assert project["rubric_download_url"].endswith("rubric.pdf"), project
        rubric = client.get(project["rubric_download_url"], params={"token": API_TOKEN})
        assert rubric.status_code == 200, rubric.text
        assert rubric.headers["content-disposition"].startswith("attachment;"), rubric.headers
        text = pdf_text(rubric)
        assert "Rubric for part i" in text, text
        bank = client.get(f"/projects/{project['id']}/question-bank", headers=AUTH_HEADERS)
        assert bank.status_code == 200 and len(bank.json()["items"]) >= 2, bank.text

        missing = client.post("/projects", data={"name": "Missing Studio Draft", "rubric_mode": "studio"}, files=files, headers=AUTH_HEADERS)
        assert missing.status_code == 400, missing.text
        assert "reviewed Rubric Studio draft" in missing.text, missing.text

    print("Rubric-source regression passed: text mode is rejected, an uploaded rubric PDF is served back as a downloadable attachment, question-bank extraction persists, and unreviewed Studio creation is rejected before project creation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
