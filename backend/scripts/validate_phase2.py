#!/usr/bin/env python3
"""Manual/automated Phase 2 API validation script.

Requires a real RUBRICEYE_DASHSCOPE_API_KEY — this makes real, billed Qwen-VL-Max
calls (a handful, ~$0.01-0.05 total for this small fixture). See HANDOVER.md for
the project's known per-booklet cost baseline.

Usage:
    PYTHONPATH=backend RUBRICEYE_DASHSCOPE_API_KEY=<key> backend/venv/bin/python backend/scripts/validate_phase2.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

api_key = os.environ.get("RUBRICEYE_DASHSCOPE_API_KEY")
if not api_key:
    print("ERROR: RUBRICEYE_DASHSCOPE_API_KEY is not set.")
    print("This script makes real, billed API calls and cannot run without a key.")
    sys.exit(1)

os.environ["RUBRICEYE_DATA_DIR"] = "/tmp/rubriceye_phase2_test"
if Path(os.environ["RUBRICEYE_DATA_DIR"]).exists():
    shutil.rmtree(os.environ["RUBRICEYE_DATA_DIR"])

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "test_fixtures_phase2"

EXPECTED_ITEMS = [
    ("1a", 6, "Correct definition (3 marks) and correct example (3 marks)."),
    ("1b", 4, "Correct method, 4 marks."),
    ("2", 5, "Full correct explanation required for 5 marks."),
    ("3", 5, "Full correct explanation required for 5 marks."),
    ("4", 5, "Full correct explanation required for 5 marks."),
]


def _ensure_question_bank(client: TestClient, project_id: str) -> None:
    """Auto-extraction is best-effort; force a known-good set the same way
    validate_phase1.py falls back to hardcoded template regions if derivation
    doesn't produce a usable result."""
    existing = {item["question_number"]: item for item in client.get(f"/projects/{project_id}/question-bank").json()["items"]}
    for question_number, marks, key_points in EXPECTED_ITEMS:
        if question_number in existing:
            item = existing[question_number]
            if item["marks_possible"] != marks or not item["key_points"]:
                resp = client.patch(
                    f"/projects/{project_id}/question-bank/{question_number}",
                    json={"marks_possible": marks, "key_points": key_points},
                )
                assert resp.status_code == 200, resp.text
        else:
            resp = client.post(
                f"/projects/{project_id}/question-bank",
                params={"question_number": question_number, "marks_possible": marks, "key_points": key_points},
            )
            assert resp.status_code == 201, resp.text


def _ensure_template_regions(client: TestClient, project_id: str) -> None:
    # This fixture's tightly-packed boxes cause the OCR+CV auto-derivation to
    # over-detect (9+ noisy regions) rather than cleanly finding 5 -- force the
    # known-good layout unconditionally instead of conditionally trusting it.
    #
    # Bboxes are PIXEL space (matching the 200-DPI rendered page images --
    # template_derivation.py detects boxes directly on the pixel image), NOT PDF-point
    # space, even though the fixture PDF itself is authored in points. Scale by 200/72.
    SCALE = 200 / 72

    def px(pt_box: list[int]) -> list[int]:
        return [round(v * SCALE) for v in pt_box]

    regions = [
        {"page_number": 1, "question_number": "1", "part_label": "a", "bbox": px([72, 90, 520, 200])},
        {"page_number": 1, "question_number": "1", "part_label": "b", "bbox": px([72, 220, 520, 330])},
        {"page_number": 1, "question_number": "2", "part_label": "", "bbox": px([72, 350, 520, 460])},
        {"page_number": 1, "question_number": "3", "part_label": "", "bbox": px([72, 480, 520, 590])},
        {"page_number": 1, "question_number": "4", "part_label": "", "bbox": px([72, 610, 520, 720])},
    ]
    update_resp = client.put(f"/projects/{project_id}/template-map", json={"regions": regions})
    assert update_resp.status_code == 200, update_resp.text
    confirm_resp = client.post(f"/projects/{project_id}/template-map/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["confirmed"] is True


def main() -> int:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"

        with open(FIXTURES / "rubric.pdf", "rb") as rubric, open(
            FIXTURES / "question_paper.pdf", "rb"
        ) as qp, open(FIXTURES / "blank_booklet.pdf", "rb") as blank:
            create_resp = client.post(
                "/projects",
                data={"name": "Phase 2 Test Project"},
                files={
                    "rubric": ("rubric.pdf", rubric, "application/pdf"),
                    "question_paper": ("question_paper.pdf", qp, "application/pdf"),
                    "blank_booklet": ("blank_booklet.pdf", blank, "application/pdf"),
                },
            )
        assert create_resp.status_code == 201, create_resp.text
        project_id = create_resp.json()["id"]

        _ensure_template_regions(client, project_id)
        _ensure_question_bank(client, project_id)

        # Edge Case H: extracted total (6+4+5+5+5=25) matches the paper's stated
        # total (25) in this fixture, so no mismatch warning is expected.
        confirm_qb = client.post(f"/projects/{project_id}/question-bank/confirm")
        assert confirm_qb.status_code == 200, confirm_qb.text
        confirm_qb_body = confirm_qb.json()
        assert confirm_qb_body["confirmed"] is True
        assert confirm_qb_body["total_marks_extracted"] == 25
        assert confirm_qb_body["marks_mismatch_warning"] is None, confirm_qb_body["marks_mismatch_warning"]

        compulsory_resp = client.post(
            f"/projects/{project_id}/question-groups",
            json={"group_name": "Q1 (Compulsory)", "selection_type": "compulsory", "question_numbers": ["1a", "1b"]},
        )
        assert compulsory_resp.status_code == 201, compulsory_resp.text

        choice_resp = client.post(
            f"/projects/{project_id}/question-groups",
            json={
                "group_name": "Q2-Q4 (Choose 2 of 3)",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["2", "3", "4"],
                "n_required": 2,
            },
        )
        assert choice_resp.status_code == 201, choice_resp.text

        with open(FIXTURES / "answer_sheet.pdf", "rb") as answer_pdf:
            upload_resp = client.post(
                f"/projects/{project_id}/answer-sheets",
                data={"roll_number": "P2-001"},
                files={"pdf": ("answer_sheet.pdf", answer_pdf, "application/pdf")},
            )
        assert upload_resp.status_code == 201, upload_resp.text
        sheet_id = upload_resp.json()["id"]

        grade_resp = client.post(f"/projects/{project_id}/answer-sheets/{sheet_id}/grade")
        assert grade_resp.status_code == 200, grade_resp.text
        grade_body = grade_resp.json()
        print("=== GRADE TRIGGER RESPONSE ===")
        print(json.dumps(grade_body, indent=2))

        # Q1's two parts are batched into a single compulsory-group API call, but
        # still produce two separate GradingResult rows.
        assert set(grade_body["graded"]) >= {"1a", "1b"}, grade_body["graded"]
        # All three of Q2/Q3/Q4 are attempted in the fixture; only the first 2 in
        # ascending order should be graded, the third skipped beyond N.
        assert grade_body["skipped_beyond_n"] == ["4"], grade_body

        results_resp = client.get(f"/projects/{project_id}/answer-sheets/{sheet_id}/results")
        assert results_resp.status_code == 200, results_resp.text
        results_body = results_resp.json()
        assert len(results_body["results"]) == 5, results_body["results"]

        # Edge Case G: section roll-up computed on read.
        section_names = {s["section_name"] for s in results_body["summary"]["sections"]}
        assert section_names == {"Q1 (Compulsory)", "Q2-Q4 (Choose 2 of 3)"}, section_names
        assert results_body["summary"]["grand_total_possible"] == 25, results_body["summary"]

        confirm_resp = client.post(
            f"/projects/{project_id}/answer-sheets/{sheet_id}/results/1a/confirm",
            json={"human_confirmed_score": 5, "human_reviewer_note": "Verified by validation script."},
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        assert confirm_resp.json()["reviewed"] is True

        # Edge Case C: idempotency — re-triggering a COMPLETE sheet must not
        # duplicate rows or re-call the API, and must return the same outcome.
        regrade_resp = client.post(f"/projects/{project_id}/answer-sheets/{sheet_id}/grade")
        assert regrade_resp.status_code == 200, regrade_resp.text
        regrade_body = regrade_resp.json()
        assert sorted(regrade_body["graded"]) == sorted(grade_body["graded"])
        results_after_regrade = client.get(f"/projects/{project_id}/answer-sheets/{sheet_id}/results").json()
        assert len(results_after_regrade["results"]) == 5, "idempotency violated: row count changed on retry"

    print("\nPhase 2 API validation passed.")
    print(json.dumps({"project_id": project_id, "answer_sheet_id": sheet_id}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
