#!/usr/bin/env python3
"""Verify original answer-book uploads remain local/privacy-safe without manual cover removal."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(tempfile.mkdtemp(prefix="rubriceye_original_upload_"))
os.environ["RUBRICEYE_DATA_DIR"] = str(ROOT / "data")
os.environ["RUBRICEYE_DASHSCOPE_API_KEY"] = ""

from app.main import app  # noqa: E402
from real_fixture_paths import BLANK, QUESTION_PAPER, RUBRIC, answer_books

ANSWER_BOOKS = answer_books()
EXPECTED_KEYS = {"2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii", "3a", "3b", "4a", "4b"}


def main() -> int:
    try:
        with TestClient(app) as client:
            with RUBRIC.open("rb") as rubric, QUESTION_PAPER.open("rb") as question_paper, BLANK.open("rb") as blank:
                created = client.post("/projects", data={"name": "Original Upload Check"}, files={"rubric": (RUBRIC.name, rubric, "application/pdf"), "question_paper": (QUESTION_PAPER.name, question_paper, "application/pdf"), "blank_booklet": (BLANK.name, blank, "application/pdf")})
            assert created.status_code == 201, created.text
            project_id = created.json()["id"]
            assert client.post(f"/projects/{project_id}/template-map/confirm").status_code == 200
            for answer_book in ANSWER_BOOKS:
                with answer_book.open("rb") as handle:
                    response = client.post(f"/projects/{project_id}/answer-sheets", data={"roll_number": answer_book.stem}, files={"pdf": (answer_book.name, handle, "application/pdf")})
                assert response.status_code == 201, f"{answer_book.name}: {response.text}"
                detail = response.json()
                keys = set(detail["question_region_map"])
                assert keys == EXPECTED_KEYS, {"book": answer_book.name, "keys": sorted(keys)}
                assert detail["page_count"] == 10
                assert all(ref["page_index"] >= 1 for refs in detail["question_region_map"].values() for ref in refs)
                print(answer_book.name, "accepted with identity page excluded;", len(keys), "semantic regions mapped")
        print("Original-upload privacy and segmentation regression passed: no model calls used.")
        return 0
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
