#!/usr/bin/env python3
"""Validation script for Unlock-to-re-edit workflows and Project Deletion."""

import json
import os
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["RUBRICEYE_DATA_DIR"] = "/tmp/rubriceye_unlock_delete_test"
if Path(os.environ["RUBRICEYE_DATA_DIR"]).exists():
    shutil.rmtree(os.environ["RUBRICEYE_DATA_DIR"])

from app.main import app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "test_fixtures"


def main() -> int:
    with TestClient(app) as client:
        # 1. Create project
        with open(FIXTURES / "rubric.pdf", "rb") as rubric, open(
            FIXTURES / "question_paper.pdf", "rb"
        ) as qp, open(FIXTURES / "blank_booklet.pdf", "rb") as blank:
            create_resp = client.post(
                "/projects",
                data={"name": "Unlock & Delete Test Project"},
                files={
                    "rubric": ("rubric.pdf", rubric, "application/pdf"),
                    "question_paper": ("question_paper.pdf", qp, "application/pdf"),
                    "blank_booklet": ("blank_booklet.pdf", blank, "application/pdf"),
                },
            )
        assert create_resp.status_code == 201, create_resp.text
        project = create_resp.json()
        project_id = project["id"]
        print(f"✓ Project created: {project_id}")

        # 2. Confirm Template Map & Question Bank
        confirm_tm_resp = client.post(f"/projects/{project_id}/template-map/confirm")
        assert confirm_tm_resp.status_code == 200, confirm_tm_resp.text
        assert confirm_tm_resp.json()["confirmed"] is True
        print("✓ Template map confirmed")

        # Populate question bank if auto-extractor yielded zero items
        qb_list = client.get(f"/projects/{project_id}/question-bank").json()
        if not qb_list["items"]:
            client.post(f"/projects/{project_id}/question-bank?question_number=1&marks_possible=5")

        confirm_qb_resp = client.post(f"/projects/{project_id}/question-bank/confirm")
        assert confirm_qb_resp.status_code == 200, confirm_qb_resp.text
        assert confirm_qb_resp.json()["confirmed"] is True
        print("✓ Question bank confirmed")

        # 3. Test Unlock Template Map
        unlock_tm_resp = client.post(f"/projects/{project_id}/template-map/unlock")
        assert unlock_tm_resp.status_code == 200, unlock_tm_resp.text
        assert unlock_tm_resp.json()["confirmed"] is False
        assert unlock_tm_resp.json()["status"] == "needs_review"
        print("✓ Template map unlocked for re-editing")

        # Re-confirm template map
        client.post(f"/projects/{project_id}/template-map/confirm")

        # 4. Test Unlock Question Bank
        unlock_qb_resp = client.post(f"/projects/{project_id}/question-bank/unlock")
        assert unlock_qb_resp.status_code == 200, unlock_qb_resp.text
        assert unlock_qb_resp.json()["confirmed"] is False
        print("✓ Question bank unlocked for re-editing")

        # Re-confirm question bank
        client.post(f"/projects/{project_id}/question-bank/confirm")

        # 5. Test Project Deletion
        del_resp = client.delete(f"/projects/{project_id}")
        assert del_resp.status_code == 204, del_resp.text
        print("✓ Project deleted via API (204 No Content)")

        # Verify project no longer exists in GET /projects/{id}
        get_resp = client.get(f"/projects/{project_id}")
        assert get_resp.status_code == 404
        print("✓ Confirmed project 404 after deletion")

    print("\nALL UNLOCK & DELETE VALIDATION TESTS PASSED PERFECTLY!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
