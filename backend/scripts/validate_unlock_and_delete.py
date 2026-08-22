#!/usr/bin/env python3
"""No-billed-call regression for unlock and soft-delete behavior."""

from __future__ import annotations

import io
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="rubriceye_trash_test_"))
os.environ["RUBRICEYE_DATA_DIR"] = str(ROOT / "data")
os.environ["RUBRICEYE_DASHSCOPE_API_KEY"] = ""

import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def pdf_bytes(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 100), text, fontsize=16)
    payload = document.tobytes()
    document.close()
    return payload


def files():
    return {
        "rubric": ("rubric.pdf", io.BytesIO(pdf_bytes("Question 1 [5]")), "application/pdf"),
        "question_paper": ("question_paper.pdf", io.BytesIO(pdf_bytes("Maximum Marks: 5\nQuestion 1")), "application/pdf"),
        "blank_booklet": ("blank_booklet.pdf", io.BytesIO(pdf_bytes("Blank booklet")), "application/pdf"),
    }


def main() -> int:
    try:
        with TestClient(app) as client:
            created = client.post("/projects", data={"name": "Unlock and Trash Test"}, files=files())
            assert created.status_code == 201, created.text
            project_id = created.json()["id"]

            template_confirm = client.post(f"/projects/{project_id}/template-map/confirm")
            assert template_confirm.status_code == 200, template_confirm.text
            question_bank = client.get(f"/projects/{project_id}/question-bank").json()
            if not question_bank["items"]:
                added = client.post(f"/projects/{project_id}/question-bank", params={"question_number": "1", "marks_possible": 5, "key_points": "Criterion"})
                assert added.status_code == 201, added.text
            question_confirm = client.post(f"/projects/{project_id}/question-bank/confirm")
            assert question_confirm.status_code == 200, question_confirm.text

            unlocked_template = client.post(f"/projects/{project_id}/template-map/unlock")
            assert unlocked_template.status_code == 200, unlocked_template.text
            assert unlocked_template.json()["confirmed"] is False
            assert client.post(f"/projects/{project_id}/template-map/confirm").status_code == 200

            unlocked_bank = client.post(f"/projects/{project_id}/question-bank/unlock")
            assert unlocked_bank.status_code == 200, unlocked_bank.text
            assert unlocked_bank.json()["confirmed"] is False
            assert client.post(f"/projects/{project_id}/question-bank/confirm").status_code == 200

            assert client.delete(f"/projects/{project_id}").status_code == 204
            assert client.get(f"/projects/{project_id}").status_code == 404
            trash = client.get("/projects/trash")
            assert trash.status_code == 200, trash.text
            assert any(item["id"] == project_id for item in trash.json())

            restored = client.post(f"/projects/{project_id}/restore")
            assert restored.status_code == 200, restored.text
            assert client.get(f"/projects/{project_id}").status_code == 200

            assert client.delete(f"/projects/{project_id}").status_code == 204
            assert client.delete(f"/projects/{project_id}/hard").status_code == 204
            assert client.get(f"/projects/{project_id}").status_code == 404
            assert not any(item["id"] == project_id for item in client.get("/projects/trash").json())

        print("Unlock and soft-delete regression passed: no billed model calls used.")
        return 0
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
