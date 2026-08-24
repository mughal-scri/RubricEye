#!/usr/bin/env python3
"""Verify Rubric Studio lifecycle without making a provider call."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz

os.environ["RUBRICEYE_DATA_DIR"] = tempfile.mkdtemp(prefix="rubriceye_studio_")

from fastapi.testclient import TestClient  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Project  # noqa: E402
from app.services.question_grouping import sort_question_labels  # noqa: E402
from app.services.rubric_studio import generate_draft  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "test_fixtures_roman"


def fake_response(extra: bool = False) -> SimpleNamespace:
    criteria = [
        {"question_number": f"2{part}", "marks_possible": 4, "key_points": f"Award for the required evidence in part {part}.", "section_label": "Section A", "question_text": f"Explain part {part}.", "provenance": f"Question 2({part}) wording", "confidence": "high" if part in {"i", "ii"} else "medium"}
        for part in ["i", "ii", "iii", "iv", "v", "vi", "vii"]
    ]
    if extra:
        criteria = criteria[:1]
        criteria.append({"question_number": "99", "marks_possible": 10, "key_points": "Hallucinated extra criterion.", "provenance": "provider-only", "confidence": "high"})
    payload = {"criteria": criteria}
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])


def assert_pdf(client: TestClient, url: str, expected_text: str) -> None:
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;"), response.headers
    document = fitz.open(stream=response.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in document)
    document.close()
    assert expected_text in text, text


def main() -> int:
    assert sort_question_labels(["10", "2", "2ii", "2i", "2a"]) == ["2", "2a", "2i", "2ii", "10"]
    assert sort_question_labels([f"5{part}" for part in "abcdefghij"]) == [f"5{part}" for part in "abcdefghij"]
    assert sort_question_labels([f"2{part}" for part in ["vii", "i", "v", "ii", "vi", "iii", "iv"]]) == [f"2{part}" for part in ["i", "ii", "iii", "iv", "v", "vi", "vii"]]
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: fake_response(extra=True))))
    with patch("app.services.rubric_studio.grading._get_client", return_value=fake_client), patch(
        "app.services.rubric_studio._expected_items", return_value={"2i": 4}
    ):
        diagnostic = generate_draft(str(FIXTURES / "question_paper.pdf"))
    assert diagnostic.status == "draft_ready", diagnostic
    assert diagnostic.warning and "1 provider criterion(s)" in diagnostic.warning and "99" in diagnostic.warning and "preserved" in diagnostic.warning, diagnostic
    assert any(criterion["question_number"] == "99" and criterion["rubric_confidence"] == "low" for criterion in diagnostic.criteria), diagnostic.criteria

    canonical_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"criteria": [{"question_number": "Q.2(i)", "marks_possible": 4, "key_points": "Canonical criterion", "confidence": "high"}]}))) ]))))
    with patch("app.services.rubric_studio.grading._get_client", return_value=canonical_client), patch(
        "app.services.rubric_studio._expected_items", return_value={"2i": 4}
    ):
        canonical = generate_draft(str(FIXTURES / "question_paper.pdf"))
    assert canonical.status == "draft_ready" and canonical.criteria[0]["question_number"] == "2i", canonical

    oversized_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(AssertionError("truncated paper must not call provider")))))
    with patch("app.services.rubric_studio.grading._get_client", return_value=oversized_client), patch.object(settings, "studio_max_text_chars", 20):
        oversized = generate_draft(str(FIXTURES / "question_paper.pdf"))
    assert oversized.status == "manual_required" and "exceeds" in (oversized.warning or ""), oversized
    files = {
        "question_paper": ("question_paper.pdf", (FIXTURES / "question_paper.pdf").read_bytes(), "application/pdf"),
        "blank_booklet": ("blank_booklet.pdf", (FIXTURES / "blank_booklet.pdf").read_bytes(), "application/pdf"),
        "rubric": ("rubric.pdf", (FIXTURES / "rubric.pdf").read_bytes(), "application/pdf"),
    }
    with TestClient(app) as client:
        with patch("app.services.rubric_studio.grading._get_client", return_value=None):
            preview = client.post("/projects/rubric-studio/preview", files={"question_paper": files["question_paper"]})
            assert preview.status_code == 200, preview.text
            assert preview.json()["status"] == "manual_required", preview.text

        # The project-level Studio lifecycle is exercised from a persisted, pending Studio project.
        db = SessionLocal()
        project_id = "studio-lifecycle"
        project_dir = Path(os.environ["RUBRICEYE_DATA_DIR"]) / "projects" / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        for key in ("question_paper", "blank_booklet"):
            (project_dir / f"{key}.pdf").write_bytes(files[key][1])
        project = Project(id=project_id, name="Studio Lifecycle", rubric_file_path=str(project_dir / "rubric.pdf"), question_paper_file_path=str(project_dir / "question_paper.pdf"), blank_booklet_file_path=str(project_dir / "blank_booklet.pdf"), rubric_source_mode="studio", rubric_studio_status="needs_generation", rubric_locked=False)
        db.add(project)
        db.commit()
        db.close()

        with patch("app.services.rubric_studio.grading._get_client", return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: fake_response())))):
            generated = client.post(f"/projects/{project_id}/rubric-studio/generate")
            assert generated.status_code == 200, generated.text
            generated_payload = generated.json()
            assert generated_payload["status"] == "draft_ready", generated_payload
            assert len(generated_payload["criteria"]) == 7, generated_payload
            assert generated_payload["criteria"][0]["rubric_provenance"] == "Question 2(i) wording", generated_payload
            assert generated_payload["criteria"][0]["section_label"] == "Section A", generated_payload
            assert generated_payload["criteria"][0]["question_text"] == "Explain part i.", generated_payload
            assert generated_payload["generated_rubric_download_url"].endswith("rubric.pdf"), generated_payload
            assert_pdf(client, generated_payload["generated_rubric_download_url"], "Studio Lifecycle")

        # Editing marks/text is enough; the examiner does not confirm every question separately.
        updated = client.patch(f"/projects/{project_id}/rubric-studio/2i", json={"marks_possible": 5, "key_points": "Edited examiner criterion."})
        assert updated.status_code == 200, updated.text
        reloaded = client.get(f"/projects/{project_id}/rubric-studio")
        assert reloaded.status_code == 200, reloaded.text
        assert reloaded.json()["criteria"][0]["section_label"] == "Section A", reloaded.text
        assert reloaded.json()["criteria"][0]["question_text"] == "Explain part i.", reloaded.text

        approved = client.post(f"/projects/{project_id}/rubric-studio/approve")
        assert approved.status_code == 200, approved.text
        approved_payload = approved.json()
        assert approved_payload["status"] == "approved", approved_payload
        assert approved_payload["all_criteria_reviewed"] is True, approved_payload
        assert_pdf(client, approved_payload["generated_rubric_download_url"], "Edited examiner criterion.")
        assert_pdf(client, approved_payload["generated_rubric_download_url"], "Explain part i.")

        project_response = client.get(f"/projects/{project_id}")
        assert project_response.status_code == 200, project_response.text
        assert project_response.json()["rubric_locked"] is True, project_response.text
        bank = client.get(f"/projects/{project_id}/question-bank")
        assert bank.status_code == 200 and all(item["rubric_provenance"] for item in bank.json()["items"]), bank.text

        export = client.post("/projects/rubric-studio/export", json={"project_name": "Standalone Export", "criteria": approved_payload["criteria"]})
        assert export.status_code == 200, export.text
        assert_pdf(client, export.json()["download_url"], "Standalone Export")

        final_create = client.post(
            "/projects",
            data={"name": "Studio Final Submission", "rubric_mode": "studio", "rubric_draft_json": json.dumps({"criteria": approved_payload["criteria"]}), "rubric_draft_reviewed": "true"},
            files=files,
        )
        assert final_create.status_code == 201, final_create.text
        final_project = final_create.json()
        assert final_project["rubric_locked"] is True, final_project
        assert final_project["rubric_studio_status"] == "approved", final_project
        assert final_project["rubric_download_url"].endswith("rubric.pdf"), final_project
        project_studio = client.get(f"/projects/{final_project['id']}/rubric-studio")
        assert project_studio.status_code == 200, project_studio.text
        assert project_studio.json()["status"] == "approved", project_studio.text
        assert project_studio.json()["all_criteria_reviewed"] is True, project_studio.text
        assert_pdf(client, final_project["rubric_download_url"], "Studio Final Submission")
        final_bank = client.get(f"/projects/{final_project['id']}/question-bank")
        assert final_bank.status_code == 200 and len(final_bank.json()["items"]) == 7, final_bank.text

    print("Rubric Studio regression passed: no-key fallback, mocked generation, ordered editing, direct PDF export, approval without per-question confirmations, staged submission, and Question Bank persistence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
