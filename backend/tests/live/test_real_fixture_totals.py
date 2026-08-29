"""Real-fixture end-to-end regression test for grading totals.

Runs the actual worst-case TestData file through the full pipeline
(project creation → template map → question bank → answer sheet upload →
grading → totals) and asserts possible == 35, confirming no_regions
items are excluded from the denominator.

This is the regression test called out in PhasePlan.md as "NOT YET VERIFIED":
    "No test exercises the actual worst-case TestData file end to end."

Gated by RUBRICEYE_LIVE_API=1 because it makes real DashScope API calls.
Run SEPARATELY from offline tests:
    cd backend && RUBRICEYE_LIVE_API=1 python -m pytest tests/live/ -v -s
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Environment must be configured BEFORE any app import so pydantic-settings
# picks up the temp data dir. This matches the pattern used by every
# validate_*.py script in backend/scripts/.
# ---------------------------------------------------------------------------
_LIVE = os.environ.get("RUBRICEYE_LIVE_API", "").strip() == "1"
_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="rubriceye_real_totals_"))
os.environ["RUBRICEYE_DATA_DIR"] = str(_TEMP_ROOT / "data")
# Phase 2: set a deterministic token for tests so the auth dependency
# accepts requests from TestClient without hitting /config first.
os.environ["RUBRICEYE_API_TOKEN"] = "test-token-for-live-fixture-test"

# Resolve real fixture paths: default to <project_root>/fixtures/real
# when not explicitly configured via environment variables.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if "RUBRICEYE_REAL_FIXTURES_DIR" not in os.environ:
    os.environ["RUBRICEYE_REAL_FIXTURES_DIR"] = str(_PROJECT_ROOT / "fixtures" / "real")

from app.main import app  # noqa: E402
from real_fixture_paths import BLANK, QUESTION_PAPER, RUBRIC, answer_books  # noqa: E402


def _strip_cover(source: Path, target: Path) -> None:
    """Remove the cover page (page 0) from a real answer booklet."""
    source_doc = pymupdf.open(source)
    output = pymupdf.open()
    for page_index in range(1, len(source_doc)):
        output.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
    output.save(target)
    output.close()
    source_doc.close()


def _create_and_prepare_project(client: TestClient, root: Path) -> str:
    """Create a project, confirm template map, and confirm question bank.

    Returns the project_id. Asserts all preparation steps succeed and the
    effective total resolves to 35 (matching the paper's stated total).
    The blank booklet's cover page is stripped before upload so the derived
    template matches the 9-page answer booklets.
    """
    blank_without_cover = root / "blank_without_cover.pdf"
    _strip_cover(BLANK, blank_without_cover)

    with RUBRIC.open("rb") as rubric, QUESTION_PAPER.open("rb") as qp, blank_without_cover.open("rb") as blank:
        response = client.post(
            "/projects",
            data={"name": "Real Fixture Totals Regression"},
            files={
                "rubric": (RUBRIC.name, rubric, "application/pdf"),
                "question_paper": (QUESTION_PAPER.name, qp, "application/pdf"),
                "blank_booklet": (blank_without_cover.name, blank, "application/pdf"),
            },
        )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    assert response.json()["template_map_status"] == "ready", response.json()

    # Confirm template map
    confirmed_tm = client.post(f"/projects/{project_id}/template-map/confirm")
    assert confirmed_tm.status_code == 200, confirmed_tm.text

    # Confirm question bank — effective_total must be 35
    confirmed_qb = client.post(f"/projects/{project_id}/question-bank/confirm")
    assert confirmed_qb.status_code == 200, confirmed_qb.text
    qb_payload = confirmed_qb.json()
    assert qb_payload["effective_total"] == 35, (
        f"Question bank effective_total should be 35, got {qb_payload['effective_total']}"
    )

    return project_id


def _upload_answer_sheet(client: TestClient, project_id: str, answer_book: Path, root: Path) -> str:
    """Upload a single real answer book (cover stripped) and return the sheet_id."""
    sanitized = root / f"{answer_book.stem}_without_cover.pdf"
    _strip_cover(answer_book, sanitized)
    with sanitized.open("rb") as handle:
        response = client.post(
            f"/projects/{project_id}/answer-sheets",
            data={"roll_number": answer_book.stem},
            files={"pdf": (sanitized.name, handle, "application/pdf")},
        )
    assert response.status_code == 201, f"{answer_book.name}: {response.text}"
    return response.json()["id"]


@pytest.mark.skipif(not _LIVE, reason="Requires RUBRICEYE_LIVE_API=1 (real DashScope API calls)")
def test_real_fixture_totals_possible_equals_35():
    """Full pipeline with real fixtures: confirm possible == 35 after grading.

    The worst-case paper has a choose-5-of-7 section (Q2) and a choose-1-of-2
    section (Section C). The first-N filter must respect choice limits even
    for ambiguous-ink items, otherwise ALL items leak through and inflate
    the denominator from 35 to 58.

    Regression: first_n_filter ambiguous items bypassing choice limits.
    """
    try:
        with TestClient(app, headers={"Authorization": "Bearer test-token-for-live-fixture-test"}) as client:
            project_id = _create_and_prepare_project(client, _TEMP_ROOT)

            # Use the first available real answer book
            answer_books_list = answer_books()
            answer_book = answer_books_list[0]
            sheet_id = _upload_answer_sheet(client, project_id, answer_book, _TEMP_ROOT)

            # Trigger grading — returns 202 with a job_id (Phase 1 async)
            grade_response = client.post(
                f"/projects/{project_id}/answer-sheets/{sheet_id}/grade"
            )
            assert grade_response.status_code == 202, (
                f"Grading enqueue failed: {grade_response.text}"
            )
            job_id = grade_response.json()["job_id"]

            # Poll the job until it reaches a terminal state
            if job_id != "already-processed":
                deadline = time.monotonic() + 600  # 10-minute budget
                while True:
                    job_resp = client.get(f"/jobs/{job_id}")
                    assert job_resp.status_code == 200, job_resp.text
                    job_status = job_resp.json()["status"]
                    if job_status in ("complete", "failed"):
                        if job_status == "failed":
                            pytest.fail(
                                f"Grading job failed: {job_resp.json().get('error')}"
                            )
                        break
                    assert time.monotonic() < deadline, "Grading job timed out (600s)"
                    time.sleep(3)

            # Fetch results and assert totals
            results_response = client.get(
                f"/projects/{project_id}/answer-sheets/{sheet_id}/results"
            )
            assert results_response.status_code == 200, results_response.text
            summary = results_response.json()["summary"]

            possible = summary["grand_total_possible"]
            awarded = summary["grand_total_awarded"]

            # Diagnostic on failure: print per-result statuses
            if possible != 35:
                all_results = results_response.json()["results"]
                for r in sorted(all_results, key=lambda x: x["question_number"]):
                    print(
                        f"  Q{r['question_number']:>5s}: choice={r['choice_status']:<20s} "
                        f"grading={r['grading_status']:<10s} "
                        f"possible={r.get('ai_total_possible', '?')}"
                    )

            assert possible == 35, (
                f"CRITICAL: grand_total_possible should be 35 (stated on paper), "
                f"got {possible}. The first-N filter must exclude items beyond "
                f"the choice limit (including ambiguous-ink items)."
            )
            assert 0 <= awarded <= possible, (
                f"Awarded {awarded} is out of range [0, {possible}]"
            )

            # Phase 3 audit trail: every VL-graded result must carry model + prompt metadata.
            # Only choice_status="graded" items actually hit the VL model; skipped_blank,
            # skipped_beyond_n, flagged_ambiguous get grading_status="complete" without a model call.
            all_results = results_response.json()["results"]
            vl_graded = [
                r for r in all_results if r.get("choice_status") == "graded"
            ]
            if vl_graded:
                for r in vl_graded:
                    assert r.get("model_name"), (
                        f"Q{r['question_number']}: model_name missing (Phase 3 audit trail)"
                    )
                    assert r.get("prompt_version"), (
                        f"Q{r['question_number']}: prompt_version missing (Phase 3 audit trail)"
                    )
                    assert r.get("request_payload_summary"), (
                        f"Q{r['question_number']}: request_payload_summary missing (Phase 3 audit trail)"
                    )
                print(
                    f"Phase 3 audit trail verified: {len(vl_graded)} VL-graded results "
                    f"carry model_name='{vl_graded[0]['model_name']}', "
                    f"prompt_version='{vl_graded[0]['prompt_version']}'"
                )
            else:
                # All items were skipped_blank/ambiguous — no VL calls made.
                # Phase 3 audit trail is verified by offline mocked tests instead.
                print("Phase 3 audit trail: no VL-graded items (all blank/ambiguous) — "
                      "audit fields verified via offline tests in test_grading_pipeline.py")
            for section in summary.get("sections", []):
                print(
                    f"  Section '{section['section_name']}': "
                    f"{section['section_total_awarded']} / {section['section_total_possible']}"
                )
            print(f"Real fixture totals regression passed: {awarded} / {possible}")
    finally:
        shutil.rmtree(_TEMP_ROOT, ignore_errors=True)
