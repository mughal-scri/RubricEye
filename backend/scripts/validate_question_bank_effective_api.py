#!/usr/bin/env python3
"""Verify project creation -> question-bank confirmation -> inferred effective structure."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["RUBRICEYE_DATA_DIR"] = tempfile.mkdtemp(prefix="rubriceye_qb_api_")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def main() -> int:
    from real_fixture_paths import BLANK, QUESTION_PAPER, RUBRIC

    files = {
        "rubric": ("rubric.pdf", RUBRIC.read_bytes(), "application/pdf"),
        "question_paper": ("question_paper.pdf", QUESTION_PAPER.read_bytes(), "application/pdf"),
        "blank_booklet": ("blank_booklet.pdf", BLANK.read_bytes(), "application/pdf"),
    }
    with TestClient(app) as client:
        created = client.post("/projects", data={"name": "Effective Total API Check"}, files=files)
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]

        bank = client.get(f"/projects/{project_id}/question-bank")
        assert bank.status_code == 200, bank.text
        assert len(bank.json()["items"]) > 0, bank.text

        confirmed = client.post(f"/projects/{project_id}/question-bank/confirm")
        assert confirmed.status_code == 200, confirmed.text
        payload = confirmed.json()
        assert payload["total_marks_extracted"] == 58, payload
        assert payload["effective_total"] == 35, payload
        assert payload["structure_status"] == "resolved", payload
        assert payload["marks_mismatch_warning"] is None, payload

        groups = client.get(f"/projects/{project_id}/question-groups")
        assert groups.status_code == 200, groups.text
        group_payload = groups.json()
        assert len(group_payload) == 2, group_payload
        q2 = next(group for group in group_payload if group["n_required"] == 5 and len(group["selection_units"]) == 7)
        section_c = next(group for group in group_payload if group["n_required"] == 1 and group["selection_units"] == [["3a", "3b"], ["4a", "4b"]])
        assert q2["n_required"] == 5 and len(q2["selection_units"]) == 7, q2
        assert section_c["n_required"] == 1 and section_c["selection_units"] == [["3a", "3b"], ["4a", "4b"]], section_c

        project = client.get(f"/projects/{project_id}")
        assert project.status_code == 200, project.text
        project_payload = project.json()
        assert project_payload["question_bank_raw_total"] == 58, project_payload
        assert project_payload["question_bank_stated_total"] == 35, project_payload
        assert project_payload["question_bank_effective_total"] == 35, project_payload
        assert project_payload["question_bank_structure_status"] == "resolved", project_payload

    print("Question-bank API regression passed: inferred groups persist and raw 58 marks resolve to effective 35 without a false mismatch warning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
