#!/usr/bin/env python3
"""Validate template derivation against the real blank booklet without model calls."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="rubriceye_real_template_"))
os.environ["RUBRICEYE_DATA_DIR"] = str(ROOT / "data")
os.environ["RUBRICEYE_DASHSCOPE_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

from real_fixture_paths import BLANK, QUESTION_PAPER, RUBRIC
EXPECTED = {"2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii", "3a", "3b", "4a", "4b"}


def main() -> int:
    try:
        with TestClient(app) as client:
            with RUBRIC.open("rb") as rubric, QUESTION_PAPER.open("rb") as question_paper, BLANK.open("rb") as blank:
                response = client.post(
                    "/projects",
                    data={"name": "Real Template Derivation Check"},
                    files={
                        "rubric": (RUBRIC.name, rubric, "application/pdf"),
                        "question_paper": (QUESTION_PAPER.name, question_paper, "application/pdf"),
                        "blank_booklet": (BLANK.name, blank, "application/pdf"),
                    },
                )
            assert response.status_code == 201, response.text
            project = response.json()
            assert project["template_map_status"] == "ready", project
            project_id = project["id"]
            template = client.get(f"/projects/{project_id}/template-map")
            assert template.status_code == 200, template.text
            regions = [
                f"{region['question_number']}{region.get('part_label', '')}"
                for page in template.json()["pages"]
                for region in page["regions"]
            ]
            actual = set(regions)
            assert actual == EXPECTED, {"expected": sorted(EXPECTED), "actual": sorted(actual), "regions": regions}
            assert len(regions) == len(EXPECTED), regions
            assert len(set(regions)) == len(regions), regions
            for page in template.json()["pages"]:
                for region in page["regions"]:
                    x1, y1, x2, y2 = region["bbox"].values()
                    assert x2 > x1 and y2 > y1, region
            print("Real blank-booklet template derivation passed: 11 semantic regions, no model calls used.")
            print({"project_id": project_id, "regions": regions})
            return 0
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
