from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Project, QuestionBankItem, TemplateMapPage
from app.schemas.models import ProjectDetail, ProjectSummary
from app.services import storage
from app.services.pdf_pipeline import pdf_to_ordered_images
from app.services.question_bank_extractor import extract_question_bank
from app.services.template_derivation import derive_template_map, regions_to_json

router = APIRouter(prefix="/projects", tags=["projects"])
LOGGER = logging.getLogger(__name__)
TRASH_RETENTION_DAYS = 30


def _project_to_summary(project: Project) -> ProjectSummary:
    return ProjectSummary.model_validate(project)


def _project_to_detail(project: Project) -> ProjectDetail:
    return ProjectDetail.model_validate(project)


def _validate_pdf(upload: UploadFile, field_name: str) -> None:
    if not upload.filename or not upload.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a PDF file.")


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _get_deleted_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is None:
        raise HTTPException(status_code=404, detail="Project not found in Trash.")
    return project


def _cleanup_project_files(project_id: str) -> None:
    project_dir = storage.project_dir(project_id)
    try:
        if project_dir.exists():
            shutil.rmtree(project_dir)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Could not remove project directory %s: %s", project_dir, exc)


def _run_template_derivation(db: Session, project: Project) -> None:
    project_dir = storage.project_dir(project.id)
    blank_images_dir = storage.blank_booklet_images_dir(project.id)
    page_paths = pdf_to_ordered_images(project.blank_booklet_file_path, str(blank_images_dir))

    db.query(TemplateMapPage).filter(TemplateMapPage.project_id == project.id).delete()
    db.commit()

    result = derive_template_map(page_paths)
    project.alignment_reference_json = json.dumps(result.alignment_reference)
    project.template_map_status = "ready" if result.confidence != "low" else "needs_review"
    project.template_map_error = None
    storage.atomic_write_json(project_dir / "alignment_reference.json", result.alignment_reference)

    for page_number, path in enumerate(page_paths, start=1):
        regions = result.pages.get(page_number, [])
        db.add(TemplateMapPage(project_id=project.id, page_number=page_number, page_image_path=path, regions_json=regions_to_json(regions)))
    db.commit()


def _run_question_bank_extraction(db: Session, project: Project) -> None:
    """Extract draft question-bank rows; the examiner must review them before locking."""
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
        db.add(QuestionBankItem(id=str(uuid.uuid4()), project_id=project.id, question_number=item.question_number, marks_possible=item.marks_possible, key_points=item.key_points))
    db.commit()


@router.get("", response_model=list[ProjectSummary])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectSummary]:
    projects = db.query(Project).filter(Project.deleted_at.is_(None)).order_by(Project.created_at.desc()).all()
    return [_project_to_summary(project) for project in projects]


@router.get("/trash", response_model=list[ProjectSummary])
def list_trash(db: Session = Depends(get_db)) -> list[ProjectSummary]:
    """List Trash and lazily remove projects older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)
    expired = db.query(Project).filter(Project.deleted_at.is_not(None), Project.deleted_at < cutoff).all()
    expired_ids = [project.id for project in expired]
    for project in expired:
        db.delete(project)
    if expired:
        db.commit()
        for project_id in expired_ids:
            _cleanup_project_files(project_id)
    projects = db.query(Project).filter(Project.deleted_at.is_not(None)).order_by(Project.deleted_at.desc()).all()
    return [_project_to_summary(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectDetail:
    return _project_to_detail(_get_project_or_404(project_id, db))


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
    if not name.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")

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

    project = Project(id=project_id, name=name.strip(), rubric_file_path=str(rubric_path), question_paper_file_path=str(question_paper_path), blank_booklet_file_path=str(blank_booklet_path), rubric_locked=True, template_map_confirmed=False, template_map_status="pending", question_bank_confirmed=False)
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        _run_template_derivation(db, project)
    except Exception:  # noqa: BLE001
        LOGGER.exception("Template derivation failed for project %s", project_id)
        db.rollback()
        project = db.get(Project, project_id)
        if project:
            project.template_map_status = "failed"
            project.template_map_error = "Template derivation failed. Review the blank booklet and retry preparation."
            db.commit()

    try:
        _run_question_bank_extraction(db, project)
    except Exception:  # noqa: BLE001
        LOGGER.exception("Question-bank extraction failed for project %s", project_id)
        db.rollback()
        project = db.get(Project, project_id)
        if project:
            project.question_bank_marks_warning = "Question-bank extraction failed. Add questions manually before grading."
            db.commit()

    db.refresh(project)
    return _project_to_detail(project)


@router.put("/{project_id}/rubric")
@router.patch("/{project_id}/rubric")
def reject_rubric_update(project_id: str) -> None:
    raise HTTPException(status_code=403, detail="Rubric is locked and cannot be modified after project creation.")


@router.post("/{project_id}/restore", response_model=ProjectSummary)
def restore_project(project_id: str, db: Session = Depends(get_db)) -> ProjectSummary:
    project = _get_deleted_project_or_404(project_id, db)
    project.deleted_at = None
    db.commit()
    db.refresh(project)
    return _project_to_summary(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> Response:
    """Move a project to Trash; child rows and files remain recoverable."""
    project = _get_project_or_404(project_id, db)
    project.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@router.delete("/{project_id}/hard", status_code=204)
def hard_delete_project(project_id: str, db: Session = Depends(get_db)) -> Response:
    project = _get_deleted_project_or_404(project_id, db)
    project_id_value = project.id
    db.delete(project)
    db.commit()
    _cleanup_project_files(project_id_value)
    return Response(status_code=204)
