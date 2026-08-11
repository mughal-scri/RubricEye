from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import Project, QuestionBankItem, TemplateMapPage
from app.schemas.models import ProjectDetail, ProjectSummary
from app.services import storage
from app.services.pdf_pipeline import pdf_to_ordered_images
from app.services.question_bank_extractor import extract_question_bank
from app.services.template_derivation import derive_template_map, regions_to_json

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_to_summary(project: Project) -> ProjectSummary:
    return ProjectSummary.model_validate(project)


def _project_to_detail(project: Project) -> ProjectDetail:
    return ProjectDetail.model_validate(project)


def _validate_pdf(upload: UploadFile, field_name: str) -> None:
    if not upload.filename or not upload.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a PDF file.")


def _run_template_derivation(db: Session, project: Project) -> None:
    project_dir = storage.project_dir(project.id)
    blank_images_dir = storage.blank_booklet_images_dir(project.id)
    page_paths = pdf_to_ordered_images(project.blank_booklet_file_path, str(blank_images_dir))

    db.query(TemplateMapPage).filter(TemplateMapPage.project_id == project.id).delete()
    db.commit()

    result = derive_template_map(page_paths)
    project.alignment_reference_json = json.dumps(result.alignment_reference)
    project.template_map_status = "ready" if result.confidence != "low" else "needs_review"
    storage.atomic_write_json(project_dir / "alignment_reference.json", result.alignment_reference)

    for page_number, path in enumerate(page_paths, start=1):
        regions = result.pages.get(page_number, [])
        db_page = TemplateMapPage(
            project_id=project.id,
            page_number=page_number,
            page_image_path=path,
            regions_json=regions_to_json(regions),
        )
        db.add(db_page)
    db.commit()


def _run_question_bank_extraction(db: Session, project: Project) -> None:
    """Phase 2 §5: auto-extract QuestionBankItem rows from the rubric PDF at creation
    time. Best-effort — always reviewed/corrected by the examiner in Question Bank
    Setup before locking (confirm_question_bank), never used unreviewed.

    Edge Case D: if the rubric has no real text layer (scanned, not typeset), this
    intentionally creates zero rows rather than garbled ones — the examiner falls
    back to manual entry via POST /{project_id}/question-bank in that case.
    """
    db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project.id).delete()
    db.commit()

    result = extract_question_bank(project.rubric_file_path)
    if not result.has_text_layer:
        project.question_bank_marks_warning = (
            "The rubric PDF appears to have no extractable text layer (likely a scan). "
            "Auto-extraction was skipped — add questions manually in Question Bank Setup."
        )
        db.commit()
        return

    for item in result.items:
        db.add(
            QuestionBankItem(
                id=str(uuid.uuid4()),
                project_id=project.id,
                question_number=item.question_number,
                marks_possible=item.marks_possible,
                key_points=item.key_points,
            )
        )
    db.commit()


@router.get("", response_model=list[ProjectSummary])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectSummary]:
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [_project_to_summary(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectDetail:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return _project_to_detail(project)


@router.post("", response_model=ProjectDetail, status_code=201)
async def create_project(
    name: str = Form(...),
    rubric: UploadFile = File(...),
    question_paper: UploadFile = File(...),
    blank_booklet: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ProjectDetail:
    _validate_pdf(rubric, "rubric")
    _validate_pdf(question_paper, "question_paper")
    _validate_pdf(blank_booklet, "blank_booklet")

    project_id = str(uuid.uuid4())
    project_dir = storage.project_dir(project_id)

    rubric_path = project_dir / "rubric.pdf"
    question_paper_path = project_dir / "question_paper.pdf"
    blank_booklet_path = project_dir / "blank_booklet.pdf"

    rubric_bytes = await rubric.read()
    question_paper_bytes = await question_paper.read()
    blank_booklet_bytes = await blank_booklet.read()

    storage.save_upload(rubric_path, rubric_bytes)
    storage.save_upload(question_paper_path, question_paper_bytes)
    storage.save_upload(blank_booklet_path, blank_booklet_bytes)

    project = Project(
        id=project_id,
        name=name.strip(),
        rubric_file_path=str(rubric_path),
        question_paper_file_path=str(question_paper_path),
        blank_booklet_file_path=str(blank_booklet_path),
        rubric_locked=True,
        template_map_confirmed=False,
        template_map_status="pending",
        question_bank_confirmed=False,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    _run_template_derivation(db, project)
    _run_question_bank_extraction(db, project)
    db.refresh(project)
    return _project_to_detail(project)


@router.put("/{project_id}/rubric")
@router.patch("/{project_id}/rubric")
def reject_rubric_update(project_id: str) -> None:
    raise HTTPException(
        status_code=403,
        detail="Rubric is locked and cannot be modified after project creation.",
    )
