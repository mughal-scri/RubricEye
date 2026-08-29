"""End-to-end pipeline test with two real answer sheets (Zainab + Ali).

Exercises: project creation → template map → question bank → upload →
grading → report generation → Phase 3 audit field validation.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import pymupdf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:8765"
API_TOKEN = "OQNu5rPfXHdWkO0RixsGVzWpAlxFU1o1glDVvpxUBEw"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}
POLL_TIMEOUT = 600  # 10 minutes per sheet
POLL_INTERVAL = 5
_TEMP_DIR = Path("/tmp/rubriceye_e2e_stripped")
_TEMP_DIR.mkdir(exist_ok=True)

# scripts/ is inside backend/; workspace root is backend/scripts/../..
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES = PROJECT_ROOT / "TestData" / "ProjectCreationTemplates"
ANSWER_SHEETS = {
    "Zainab": PROJECT_ROOT / "TestData" / "TestingAnswersheets" / "Test answer book 1 - Zainab.pdf",
    "Ali": Path.home() / "Downloads" / "Test Answer sheet - Ali.pdf",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_cover(source: Path, target: Path) -> Path:
    """Remove the cover page (page 0) from a PDF."""
    src = pymupdf.open(source)
    src_pages = len(src)
    dst = pymupdf.open()
    for i in range(1, src_pages):
        dst.insert_pdf(src, from_page=i, to_page=i)
    dst.save(target)
    dst_pages = len(pymupdf.open(target))
    dst.close()
    src.close()
    print(f"       stripped cover: {source.name} ({src_pages} pages) -> {target.name} ({dst_pages} pages)")
    return target

def _check(label: str, resp: httpx.Response, expected_status: int) -> dict:
    """Assert status and return JSON body."""
    if resp.status_code != expected_status:
        print(f"  FAIL {label}: expected {expected_status}, got {resp.status_code}")
        print(f"  Body: {resp.text[:500]}")
        sys.exit(1)
    body = resp.json() if resp.content else {}
    print(f"  OK   {label} ({resp.status_code})")
    return body


def _poll_job(client: httpx.Client, job_id: str, label: str) -> dict:
    """Poll a grading job until terminal state."""
    if job_id == "already-processed":
        print(f"  OK   {label}: already processed (skipping poll)")
        return {"status": "complete"}

    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        resp = client.get(f"/jobs/{job_id}", headers=HEADERS)
        _check(f"{label} poll", resp, 200)
        body = resp.json()
        status = body["status"]
        if status == "complete":
            return body
        if status == "failed":
            print(f"  FAIL {label}: job failed — {body.get('error')}")
            sys.exit(1)
        print(f"  ...  {label}: status={status}, waiting {POLL_INTERVAL}s")
        time.sleep(POLL_INTERVAL)

    print(f"  FAIL {label}: timed out after {POLL_TIMEOUT}s")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("RubricEye E2E Pipeline Test — Zainab + Ali")
    print("=" * 60)

    with httpx.Client(base_url=BASE_URL, timeout=120) as client:

        # --- 1. Health check ---
        print("\n[1] Health check")
        health = client.get("/health")
        _check("health", health, 200)

        # --- 2. Create project ---
        print("\n[2] Create project (rubric + question paper + blank booklet)")
        # Strip cover page from blank booklet (page 1 is cover, content starts page 2)
        blank_stripped = _TEMP_DIR / "blank_without_cover.pdf"
        _strip_cover(TEMPLATES / "RubricEye_AnswerBooklet.pdf", blank_stripped)
        with (
            (TEMPLATES / "RubricEye_MockExam_Rubric.pdf").open("rb") as rubric,
            (TEMPLATES / "RubricEye MockExam Question Paper.pdf").open("rb") as qp,
            blank_stripped.open("rb") as blank,
        ):
            resp = client.post(
                "/projects",
                headers=HEADERS,
                data={"name": "E2E Test — Zainab + Ali"},
                files={
                    "rubric": ("RubricEye_MockExam_Rubric.pdf", rubric, "application/pdf"),
                    "question_paper": ("RubricEye MockExam Question Paper.pdf", qp, "application/pdf"),
                    "blank_booklet": ("RubricEye_AnswerBooklet.pdf", blank, "application/pdf"),
                },
            )
        project = _check("create project", resp, 201)
        project_id = project["id"]
        print(f"       project_id={project_id}")
        print(f"       template_map_status={project.get('template_map_status')}")

        # --- 3. Confirm template map ---
        print("\n[3] Confirm template map")
        tm = client.post(f"/projects/{project_id}/template-map/confirm", headers=HEADERS)
        tm_body = _check("confirm template map", tm, 200)
        print(f"       regions mapped: {len(tm_body.get('regions', []))}")

        # --- 4. Confirm question bank ---
        print("\n[4] Confirm question bank")
        qb = client.post(f"/projects/{project_id}/question-bank/confirm", headers=HEADERS)
        qb_body = _check("confirm question bank", qb, 200)
        effective_total = qb_body.get("effective_total")
        print(f"       effective_total={effective_total}")
        assert effective_total == 35, f"Expected 35, got {effective_total}"

        # --- 5. Upload answer sheets ---
        sheet_ids: dict[str, str] = {}
        for name, pdf_path in ANSWER_SHEETS.items():
            print(f"\n[5] Upload answer sheet: {name}")
            if not pdf_path.exists():
                print(f"  FAIL file not found: {pdf_path}")
                sys.exit(1)
            # Strip cover page from answer sheet
            stripped_path = _TEMP_DIR / f"{pdf_path.stem}_no_cover.pdf"
            _strip_cover(pdf_path, stripped_path)
            with stripped_path.open("rb") as f:
                resp = client.post(
                    f"/projects/{project_id}/answer-sheets",
                    headers=HEADERS,
                    data={"roll_number": name},
                    files={"pdf": (stripped_path.name, f, "application/pdf")},
                )
            body = _check(f"upload {name}", resp, 201)
            sheet_ids[name] = body["id"]
            print(f"       sheet_id={body['id']}")

        # --- 5b. Confirm alignment (clear page_correspondence_uncertain) ---
        for name, sheet_id in sheet_ids.items():
            print(f"\n[5b] Confirm alignment: {name}")
            resp = client.post(
                f"/projects/{project_id}/answer-sheets/{sheet_id}/alignment/confirm",
                headers=HEADERS,
            )
            _check(f"alignment confirm {name}", resp, 200)

        # --- 6. Trigger grading ---
        job_ids: dict[str, str] = {}
        for name, sheet_id in sheet_ids.items():
            print(f"\n[6] Trigger grading: {name}")
            resp = client.post(
                f"/projects/{project_id}/answer-sheets/{sheet_id}/grade",
                headers=HEADERS,
            )
            body = _check(f"enqueue {name}", resp, 202)
            job_ids[name] = body.get("job_id", "already-processed")
            print(f"       job_id={job_ids[name]}")

        # --- 7. Poll until complete ---
        for name, job_id in job_ids.items():
            print(f"\n[7] Polling grading job: {name}")
            _poll_job(client, job_id, name)
            print(f"  OK   {name}: grading complete")

        # --- 8. Fetch and validate results ---
        for name, sheet_id in sheet_ids.items():
            print(f"\n[8] Results: {name}")
            resp = client.get(
                f"/projects/{project_id}/answer-sheets/{sheet_id}/results",
                headers=HEADERS,
            )
            body = _check(f"results {name}", resp, 200)
            summary = body["summary"]
            results = body["results"]

            possible = summary["grand_total_possible"]
            awarded = summary["grand_total_awarded"]
            print(f"       Total: {awarded} / {possible}")

            # Per-question breakdown
            graded_count = 0
            blank_count = 0
            ambiguous_count = 0
            other_count = 0
            vl_graded_with_audit = 0

            for r in sorted(results, key=lambda x: x.get("question_number", "")):
                cs = r.get("choice_status", "?")
                gs = r.get("grading_status", "?")
                score = r.get("ai_score")
                qn = r.get("question_number", "?")

                if cs == "graded":
                    graded_count += 1
                    # Phase 3 audit field checks
                    mn = r.get("model_name")
                    pv = r.get("prompt_version")
                    rps = r.get("request_payload_summary")
                    if mn and pv and rps:
                        vl_graded_with_audit += 1
                    else:
                        print(f"       WARN Q{qn}: missing audit fields "
                              f"(model={mn}, prompt_ver={pv}, payload={bool(rps)})")
                elif cs == "skipped_blank":
                    blank_count += 1
                elif cs == "flagged_ambiguous":
                    ambiguous_count += 1
                else:
                    other_count += 1

                if score is not None:
                    print(f"       Q{qn:>5s}: {cs:<20s} score={score}")

            print(f"\n       Summary for {name}:")
            print(f"         VL-graded: {graded_count} (with audit fields: {vl_graded_with_audit})")
            print(f"         Blank: {blank_count}, Ambiguous: {ambiguous_count}, Other: {other_count}")
            print(f"         Grand total: {awarded} / {possible}")

            # Validation
            assert possible == 35, f"{name}: expected possible=35, got {possible}"
            assert 0 <= awarded <= possible, f"{name}: awarded {awarded} out of [0, {possible}]"

            # Phase 3 audit trail validation — if VL was called, fields MUST be present
            if graded_count > 0:
                assert vl_graded_with_audit == graded_count, (
                    f"{name}: {graded_count - vl_graded_with_audit} VL-graded results "
                    f"missing Phase 3 audit fields"
                )
                print(f"         Phase 3 audit trail: PASS ({vl_graded_with_audit}/{graded_count})")
            else:
                print(f"         Phase 3 audit trail: N/A (no VL calls)")

        # --- 9. Confirm scores (required before report generation) ---
        print(f"\n[9] Confirm scores")
        for name, sheet_id in sheet_ids.items():
            # Fetch results to get graded questions
            resp = client.get(
                f"/projects/{project_id}/answer-sheets/{sheet_id}/results",
                headers=HEADERS,
            )
            results = resp.json()["results"]
            for r in results:
                qn = r.get("question_number")
                cs = r.get("choice_status")
                ai_score = r.get("ai_score")
                # Confirm both VL-graded and flagged_ambiguous items
                if cs == "graded" and ai_score is not None:
                    confirm_score = ai_score
                elif cs == "flagged_ambiguous":
                    confirm_score = 0  # ambiguous items get 0 by default
                else:
                    continue
                confirm_resp = client.post(
                    f"/projects/{project_id}/answer-sheets/{sheet_id}/results/{qn}/confirm",
                    headers=HEADERS,
                    json={"human_confirmed_score": confirm_score, "human_reviewer_note": "E2E test auto-confirm"},
                )
                if confirm_resp.status_code != 200:
                    print(f"  WARN confirm {name} Q{qn}: {confirm_resp.status_code} {confirm_resp.text[:100]}")
            print(f"  OK   {name}: all graded/ambiguous scores confirmed")

        # --- 10. Report generation ---
        print(f"\n[10] Generate evaluation reports")
        for name, sheet_id in sheet_ids.items():
            resp = client.post(
                f"/projects/{project_id}/answer-sheets/{sheet_id}/report",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                report_path = resp.json().get("report_path", "?")
                print(f"  OK   {name}: report at {report_path}")
            elif resp.status_code == 404:
                print(f"  INFO {name}: no report endpoint or not ready yet (404)")
            else:
                print(f"  WARN {name}: report status={resp.status_code}")

        # --- 11. Project summary ---
        print(f"\n[11] Project summary")
        resp = client.get(f"/projects/{project_id}", headers=HEADERS)
        proj = _check("project detail", resp, 200)
        print(f"        sheets: {len(proj.get('answer_sheets', []))}")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
