#!/usr/bin/env python3
"""Verify rubric-source modes and generated rubric PDF behavior without provider calls."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import fitz

os.environ["RUBRICEYE_DATA_DIR"] = tempfile.mkdtemp(prefix="rubriceye_sources_")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "test_fixtures_roman"


def pdf_text(response) -> str:
    document = fitz.open(stream=response.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in document)
    document.close()
    return text


def main() -> int:
    files = {
        "question_paper": ("question_paper.pdf", (FIXTURES / "question_paper.pdf").read_bytes(), "application/pdf"),
        "blank_booklet": ("blank_booklet.pdf", (FIXTURES / "blank_booklet.pdf").read_bytes(), "application/pdf"),
    }
    rubric_text = "Q2i — 4 marks\nAward one mark for the correct definition.\nAward three marks for the correct explanation.\n\nQ2ii — 4 marks\nAward marks for two accurate examples."
    with TestClient(app) as client:
        empty = client.post("/projects", data={"name": "Empty Text", "rubric_mode": "text", "rubric_text": "   "}, files=files)
        assert empty.status_code == 400, empty.text

        created = client.post("/projects", data={"name": "Text Rubric Check", "rubric_mode": "text", "rubric_text": rubric_text}, files=files)
        assert created.status_code == 201, created.text
        project = created.json()
        assert project["rubric_source_mode"] == "text", project
        assert project["rubric_download_url"].endswith("rubric.pdf"), project
        rubric = client.get(project["rubric_download_url"])
        assert rubric.status_code == 200, rubric.text
        assert rubric.headers["content-disposition"].startswith("attachment;"), rubric.headers
        text = pdf_text(rubric)
        assert "Text Rubric Check" in text and "Q2i" in text and "Award one mark" in text, text
        bank = client.get(f"/projects/{project['id']}/question-bank")
        assert bank.status_code == 200 and len(bank.json()["items"]) >= 2, bank.text

        missing = client.post("/projects", data={"name": "Missing Studio Draft", "rubric_mode": "studio"}, files=files)
        assert missing.status_code == 400, missing.text
        assert "reviewed Rubric Studio draft" in missing.text, missing.text

    print("Rubric-source regression passed: empty text is rejected, pasted text becomes a structured downloadable PDF, question-bank extraction persists, and unreviewed Studio creation is rejected before project creation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
