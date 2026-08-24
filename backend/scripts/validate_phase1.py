#!/usr/bin/env python3
"""Manual Phase 1 API validation script."""

import json
import os
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["RUBRICEYE_DATA_DIR"] = "/tmp/rubriceye_phase1_test"
if Path(os.environ["RUBRICEYE_DATA_DIR"]).exists():
    shutil.rmtree(os.environ["RUBRICEYE_DATA_DIR"])

from app.main import app  # noqa: E402

FIXTURES = Path(os.environ.get("RUBRICEYE_PHASE1_FIXTURES_DIR", Path(__file__).resolve().parent / "test_fixtures_roman"))


def main() -> int:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"

        with open(FIXTURES / "rubric.pdf", "rb") as rubric, open(
            FIXTURES / "question_paper.pdf", "rb"
        ) as qp, open(FIXTURES / "blank_booklet.pdf", "rb") as blank:
            create_resp = client.post(
                "/projects",
                data={"name": "Phase 1 Test Project"},
                files={
                    "rubric": ("rubric.pdf", rubric, "application/pdf"),
                    "question_paper": ("question_paper.pdf", qp, "application/pdf"),
                    "blank_booklet": ("blank_booklet.pdf", blank, "application/pdf"),
                },
            )
        assert create_resp.status_code == 201, create_resp.text
        project = create_resp.json()
        project_id = project["id"]
        assert project["rubric_locked"] is True

        rubric_update = client.put(f"/projects/{project_id}/rubric")
        assert rubric_update.status_code == 403

        template_resp = client.get(f"/projects/{project_id}/template-map")
        assert template_resp.status_code == 200, template_resp.text
        template = template_resp.json()
        assert template["pages"]

        regions = []
        for page in template["pages"]:
            for region in page["regions"]:
                regions.append(
                    {
                        "page_number": page["page_number"],
                        "question_number": region["question_number"],
                        "part_label": region["part_label"],
                        "bbox": [
                            region["bbox"]["x1"],
                            region["bbox"]["y1"],
                            region["bbox"]["x2"],
                            region["bbox"]["y2"],
                        ],
                    }
                )
        if not regions:
            regions = [
                {
                    "page_number": 1,
                    "question_number": "1",
                    "part_label": "a",
                    "bbox": [72, 90, 520, 220],
                },
                {
                    "page_number": 1,
                    "question_number": "1",
                    "part_label": "b",
                    "bbox": [72, 268, 520, 398],
                },
                {
                    "page_number": 1,
                    "question_number": "2",
                    "part_label": "",
                    "bbox": [72, 448, 520, 620],
                },
            ]

        update_resp = client.put(
            f"/projects/{project_id}/template-map",
            json={"regions": regions},
        )
        assert update_resp.status_code == 200, update_resp.text

        confirm_resp = client.post(f"/projects/{project_id}/template-map/confirm")
        assert confirm_resp.status_code == 200, confirm_resp.text
        assert confirm_resp.json()["confirmed"] is True

        with open(FIXTURES / "answer_sheet.pdf", "rb") as answer_pdf:
            upload_resp = client.post(
                f"/projects/{project_id}/answer-sheets",
                data={"roll_number": "12345"},
                files={"pdf": ("answer_sheet.pdf", answer_pdf, "application/pdf")},
            )
        assert upload_resp.status_code == 201, upload_resp.text
        sheet = upload_resp.json()
        assert sheet["roll_number"] == "12345"
        assert sheet["page_count"] >= 1

    with TestClient(app) as restart_client:
        persisted = restart_client.get(f"/projects/{project_id}").json()
        assert persisted["template_map_confirmed"] is True
        assert persisted["name"] == "Phase 1 Test Project"

        sheets = restart_client.get(f"/projects/{project_id}/answer-sheets").json()
        assert len(sheets) == 1

        detail = restart_client.get(f"/projects/{project_id}/answer-sheets/{sheet['id']}").json()
        assert detail["question_region_map"]

    print("Phase 1 API validation passed.")
    print(json.dumps({"project_id": project_id, "answer_sheet_id": sheet["id"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
