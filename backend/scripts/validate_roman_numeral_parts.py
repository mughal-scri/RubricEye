#!/usr/bin/env python3
"""Regression test for the roman-numeral part-label fix.

Found during Phase 3 material review: Abdullah's real mock exam uses roman
numerals (i, ii, iii...) for Q2's seven sub-parts, not letters. The original
Phase 2 code only supported single-letter parts -- `split_base_and_part` silently
failed to parse anything past "a", which broke both the first-N ascending-order
sort and the region-key resolution for any part beyond "i" or "v" (the only two
that happened to be a single character).

This script proves the fix through the real HTTP API, not just unit-level
functions: the choice group below is submitted with its question_numbers
DELIBERATELY SHUFFLED, so a pass here can't be explained by lucky input
ordering -- the system has to actually sort "2vii, 2iii, 2i, 2v, 2ii, 2vi, 2iv"
into true ascending numeric order (i < ii < iii < iv < v < vi < vii) on its own.

Uses a MOCKED grading client -- no real API cost. Run with:
    PYTHONPATH=backend backend/venv/bin/python backend/scripts/validate_roman_numeral_parts.py
"""

import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("RUBRICEYE_DASHSCOPE_API_KEY", "fake-key-for-mock-test")
os.environ["RUBRICEYE_DATA_DIR"] = "/tmp/rubriceye_roman_test"
if Path(os.environ["RUBRICEYE_DATA_DIR"]).exists():
    shutil.rmtree(os.environ["RUBRICEYE_DATA_DIR"])

from fastapi.testclient import TestClient  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "test_fixtures_roman"
PARTS = ["i", "ii", "iii", "iv", "v", "vi", "vii"]
Y_START = 80
ROW_H = 100
SCALE = 200 / 72  # template-map bboxes are pixel-space; fixture is authored in points


def _px(box_points: list[int]) -> list[int]:
    return [round(v * SCALE) for v in box_points]


def _fake_template_fallback(page_image_paths):
    from app.services.template_types import DetectedRegion
    from app.services.template_vision_fallback import VisionDerivationResult

    regions = {
        1: [DetectedRegion(question_number="2", part_label=part, bbox=_px([72, Y_START + index * ROW_H + 10, 520, Y_START + (index + 1) * ROW_H - 15])) for index, part in enumerate(PARTS)]
    }
    return VisionDerivationResult(
        pages=regions,
        alignment_reference={"pages": {"1": {"horizontal_lines": [], "vertical_lines": [], "width": 1653, "height": 2339}}},
        confidence="medium",
    )


def _fake_create(*args, **kwargs):
    resp = MagicMock()
    payload = {
        "transcription_summary": "Attempted.",
        "part_scores": [{"part": "", "marks_awarded": 3, "marks_possible": 4, "rationale": "Good."}],
        "total_awarded": 3, "total_possible": 4, "flags": [], "confidence": "high",
    }
    resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    return resp


def main() -> int:
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = _fake_create

    with patch("app.services.grading._get_client", return_value=fake_client), patch(
        "app.services.template_derivation.extract_regions_with_vision", side_effect=_fake_template_fallback
    ):
        import app.services.grading  # noqa: F401
        import app.routes.answer_sheets as answer_sheets
        from app.main import app
        answer_sheets.compare_page_labels = lambda _page, _path: ("match", set(), set())

        with TestClient(app) as client:
            with open(FIXTURES / "rubric.pdf", "rb") as rubric, open(
                FIXTURES / "question_paper.pdf", "rb"
            ) as qp, open(FIXTURES / "blank_booklet.pdf", "rb") as blank:
                resp = client.post(
                    "/projects",
                    data={"name": "Roman Numeral Regression Test"},
                    files={
                        "rubric": ("rubric.pdf", rubric, "application/pdf"),
                        "question_paper": ("question_paper.pdf", qp, "application/pdf"),
                        "blank_booklet": ("blank_booklet.pdf", blank, "application/pdf"),
                    },
                )
            assert resp.status_code == 201, resp.text
            project_id = resp.json()["id"]

            regions = []
            for idx, part in enumerate(PARTS):
                y = Y_START + idx * ROW_H
                regions.append(
                    {
                        "page_number": 1,
                        "question_number": "2",
                        "part_label": part,
                        "bbox": _px([72, y + 10, 520, y + ROW_H - 15]),
                    }
                )
            r = client.put(f"/projects/{project_id}/template-map", json={"regions": regions})
            assert r.status_code == 200, r.text
            r = client.post(f"/projects/{project_id}/template-map/confirm")
            assert r.status_code == 200, r.text

            existing = {
                i["question_number"]: i
                for i in client.get(f"/projects/{project_id}/question-bank").json()["items"]
            }
            for part in PARTS:
                qn = f"2{part}"
                if qn in existing:
                    client.patch(
                        f"/projects/{project_id}/question-bank/{qn}",
                        json={"marks_possible": 4, "key_points": f"Rubric for part {part}."},
                    )
                else:
                    r = client.post(
                        f"/projects/{project_id}/question-bank",
                        params={"question_number": qn, "marks_possible": 4, "key_points": f"Rubric for part {part}."},
                    )
                    assert r.status_code == 201, r.text

            qb_confirm = client.post(f"/projects/{project_id}/question-bank/confirm")
            assert qb_confirm.status_code == 200, qb_confirm.text
            qb_body = qb_confirm.json()
            # 7 parts x 4 marks = 28 raw marks, while only 5 of 7 are scored;
            # the effective candidate total therefore resolves to the paper's stated
            # "Maximum Marks: 20". This also proves the wording fix fires; the old
            # regex only recognized "Total Marks" and could silently find nothing.
            assert qb_body["total_marks_on_paper"] == 20, qb_body
            assert qb_body["total_marks_extracted"] == 28, qb_body
            assert qb_body["effective_total"] == 20, qb_body
            assert qb_body["structure_status"] == "resolved", qb_body
            assert qb_body["marks_mismatch_warning"] is None, qb_body

            shuffled_question_numbers = ["2vii", "2iii", "2i", "2v", "2ii", "2vi", "2iv"]
            existing_groups = client.get(f"/projects/{project_id}/question-groups").json()
            if existing_groups:
                inferred = next(group for group in existing_groups if group["selection_type"] == "choose_n_of_m")
                assert inferred["n_required"] == 5, inferred
                assert set(inferred["question_numbers"]) == set(shuffled_question_numbers), inferred
            else:
                r = client.post(
                    f"/projects/{project_id}/question-groups",
                    json={
                        "group_name": "Q2 (Choose 5 of 7)",
                        "selection_type": "choose_n_of_m",
                        "question_numbers": shuffled_question_numbers,
                        "n_required": 5,
                    },
                )
                assert r.status_code == 201, r.text

            with open(FIXTURES / "answer_sheet.pdf", "rb") as f:
                r = client.post(
                    f"/projects/{project_id}/answer-sheets",
                    data={"roll_number": "ROMAN-1"},
                    files={"pdf": ("answer_sheet.pdf", f, "application/pdf")},
                )
            assert r.status_code == 201, r.text
            sheet_id = r.json()["id"]

            r = client.post(f"/projects/{project_id}/answer-sheets/{sheet_id}/grade")
            assert r.status_code == 200, r.text
            body = r.json()
            print(json.dumps(body, indent=2))

            assert sorted(body["graded"]) == ["2i", "2ii", "2iii", "2iv", "2v"], body["graded"]
            assert sorted(body["skipped_beyond_n"]) == ["2vi", "2vii"], body["skipped_beyond_n"]

    print("\nRoman-numeral part-label regression test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
