#!/usr/bin/env python3
"""Verify original answer-book uploads remain local/privacy-safe without manual cover removal."""

from __future__ import annotations

import os
import shutil
import tempfile

import fitz
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

            mismatch_path = ROOT / "missing-interior-page.pdf"
            with fitz.open(ANSWER_BOOKS[0]) as mismatch_document:
                mismatch_document.delete_page(5)
                mismatch_document.save(mismatch_path)
            with mismatch_path.open("rb") as handle:
                mismatch_response = client.post(
                    f"/projects/{project_id}/answer-sheets",
                    data={"roll_number": "missing-interior-page"},
                    files={"pdf": (mismatch_path.name, handle, "application/pdf")},
                )
            assert mismatch_response.status_code == 409, mismatch_response.text
            mismatch_detail = mismatch_response.json()["detail"]
            assert "9 pages" in mismatch_detail and "10" in mismatch_detail, mismatch_detail
            sheets = client.get(f"/projects/{project_id}/answer-sheets").json()
            assert all(sheet["roll_number"] != "missing-interior-page" for sheet in sheets), sheets
            print("missing-page parity guard rejected 9-page booklet against confirmed 10-page template")

            reordered_path = ROOT / "reordered-interior-pages.pdf"
            with fitz.open(ANSWER_BOOKS[0]) as reordered_document:
                page_order = list(range(reordered_document.page_count))
                page_order[4], page_order[5] = page_order[5], page_order[4]
                reordered_document.select(page_order)
                reordered_document.save(reordered_path)
            with reordered_path.open("rb") as handle:
                reordered_response = client.post(
                    f"/projects/{project_id}/answer-sheets",
                    data={"roll_number": "reordered-interior-pages"},
                    files={"pdf": (reordered_path.name, handle, "application/pdf")},
                )
            assert reordered_response.status_code == 409, reordered_response.text
            assert "does not match the confirmed template" in reordered_response.json()["detail"], reordered_response.text
            sheets = client.get(f"/projects/{project_id}/answer-sheets").json()
            assert all(sheet["roll_number"] != "reordered-interior-pages" for sheet in sheets), sheets
            print("same-count interior reorder rejected by local page-label correspondence check")
        print("Original-upload privacy, segmentation, and page-parity regression passed: no model calls used.")
        return 0
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
