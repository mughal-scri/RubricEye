#!/usr/bin/env python3
"""Validate real-booklet template mapping and segmentation without grading calls."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

ROOT = Path(tempfile.mkdtemp(prefix="rubriceye_real_segmentation_"))
os.environ["RUBRICEYE_DATA_DIR"] = str(ROOT / "data")
os.environ["RUBRICEYE_DASHSCOPE_API_KEY"] = ""

from app.main import app  # noqa: E402

from real_fixture_paths import BLANK, QUESTION_PAPER, RUBRIC, answer_books

ANSWER_BOOKS = answer_books()
EXPECTED_KEYS = {"2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii", "3a", "3b", "4a", "4b"}


def strip_cover(source: Path, target: Path) -> None:
    source_doc = pymupdf.open(source)
    output = pymupdf.open()
    for page_index in range(1, len(source_doc)):
        output.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
    output.save(target)
    output.close()
    source_doc.close()


def main() -> int:
    try:
        blank_without_cover = ROOT / "blank_without_cover.pdf"
        strip_cover(BLANK, blank_without_cover)
        with TestClient(app) as client:
            with RUBRIC.open("rb") as rubric, QUESTION_PAPER.open("rb") as question_paper, blank_without_cover.open("rb") as blank:
                created = client.post(
                    "/projects",
                    data={"name": "Real Segmentation Check"},
                    files={
                        "rubric": (RUBRIC.name, rubric, "application/pdf"),
                        "question_paper": (QUESTION_PAPER.name, question_paper, "application/pdf"),
                        "blank_booklet": (blank_without_cover.name, blank, "application/pdf"),
                    },
                )
            assert created.status_code == 201, created.text
            project_id = created.json()["id"]
            assert created.json()["template_map_status"] == "ready", created.json()
            confirmed = client.post(f"/projects/{project_id}/template-map/confirm")
            assert confirmed.status_code == 200, confirmed.text
            map_payload = confirmed.json()
            map_keys = {f"{r['question_number']}{r.get('part_label', '')}" for p in map_payload["pages"] for r in p["regions"]}
            assert map_keys == EXPECTED_KEYS, sorted(map_keys)
            print("template-map keys:", sorted(map_keys))

            for answer_book in ANSWER_BOOKS:
                sanitized = ROOT / f"{answer_book.stem}_without_cover.pdf"
                strip_cover(answer_book, sanitized)
                with sanitized.open("rb") as handle:
                    response = client.post(
                        f"/projects/{project_id}/answer-sheets",
                        data={"roll_number": answer_book.stem},
                        files={"pdf": (sanitized.name, handle, "application/pdf")},
                    )
                assert response.status_code == 201, f"{answer_book.name}: {response.text}"
                detail = response.json()
                actual_keys = set(detail["question_region_map"])
                missing = sorted(EXPECTED_KEYS - actual_keys)
                print(json.dumps({
                    "book": answer_book.name,
                    "pages": detail["page_count"],
                    "mapped_keys": sorted(actual_keys),
                    "missing_keys": missing,
                    "region_counts": {key: len(value) for key, value in detail["question_region_map"].items()},
                    "overflow_keys": sorted({key for key, refs in detail["question_region_map"].items() if any(ref.get("overflow_detected") for ref in refs)}),
                }))
                assert detail["page_count"] == 9, detail
                assert not missing, {"book": answer_book.name, "missing": missing, "actual": sorted(actual_keys)}
                assert all(detail["region_preview_urls"].get(key) for key in EXPECTED_KEYS), detail["region_preview_urls"]

        print("Real segmentation regression passed: all three sanitized answer books mapped without grading calls.")
        return 0
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
