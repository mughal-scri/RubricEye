from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Project, QuestionBankItem
from app.schemas.models import RubricStudioCriterionDraft, RubricStudioCriterionResponse, RubricStudioCriterionUpdate, RubricStudioExportRequest, RubricStudioExportResponse, RubricStudioPreviewResponse, RubricStudioResponse
from app.config import settings
from app.services import storage
from app.services.rubric_pdf import render_rubric_pdf
from app.services.pdf_validation import read_validated_upload
from app.services.rubric_studio import StudioGenerationResult, generate_draft, materialize_draft
from app.services.question_grouping import question_sort_key
from app.routes.projects import _run_question_bank_extraction

router = APIRouter(prefix="/projects", tags=["rubric-studio"])


@router.post("/rubric-studio/export", response_model=RubricStudioExportResponse)
def export_rubric_studio(payload: RubricStudioExportRequest) -> RubricStudioExportResponse:
    if not payload.criteria:
        raise HTTPException(status_code=400, detail="At least one rubric criterion is required before exporting.")
    incomplete = [criterion.question_number for criterion in payload.criteria if criterion.marks_possible is None or not (criterion.key_points or "").strip()]
    if incomplete:
        raise HTTPException(status_code=409, detail=f"Complete the rubric criteria before exporting: {', '.join(incomplete)}.")
    export_id = str(uuid.uuid4())
    destination = settings.data_dir / "rubric_studio_exports" / f"{export_id}.pdf"
    render_rubric_pdf(destination, project_name=payload.project_name, source_label="Rubric Studio · examiner-edited draft", criteria=[criterion.model_dump() for criterion in payload.criteria])
    return RubricStudioExportResponse(download_url=f"/files/rubric_studio_exports/{export_id}.pdf")


@router.post("/rubric-studio/preview", response_model=RubricStudioPreviewResponse)
async def preview_rubric_studio(question_paper: UploadFile = File(...)) -> RubricStudioPreviewResponse:
    with tempfile.TemporaryDirectory(prefix="rubriceye_studio_preview_") as temporary_dir:
        path = Path(temporary_dir) / "question_paper.pdf"
        path.write_bytes(await read_validated_upload(question_paper, "Question paper"))
        result = generate_draft(str(path))
    generated_url = None
    if result.criteria:
        preview_id = str(uuid.uuid4())
        preview_path = settings.data_dir / "rubric_studio_previews" / f"{preview_id}.pdf"
        render_rubric_pdf(preview_path, project_name="RubricEye Studio Preview", source_label="Rubric Studio · provisional draft", criteria=result.criteria)
        generated_url = f"/files/rubric_studio_previews/{preview_id}.pdf"
    return RubricStudioPreviewResponse(status=result.status, criteria=[RubricStudioCriterionDraft(**criterion) for criterion in result.criteria], warning=result.warning, generated_rubric_download_url=generated_url)


def _project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _items(project_id: str, db: Session) -> list[QuestionBankItem]:
    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    labels = [item.question_number for item in items]
    return sorted(items, key=lambda item: (*question_sort_key(item.question_number, labels), item.id))


def _criteria(items: list[QuestionBankItem]) -> list[RubricStudioCriterionResponse]:
    return [RubricStudioCriterionResponse(id=item.id, question_number=item.question_number, marks_possible=item.marks_possible, key_points=item.key_points, section_label=item.section_label, question_text=item.question_text, rubric_provenance=item.rubric_provenance, rubric_confidence=item.rubric_confidence, rubric_reviewed=item.rubric_reviewed) for item in items]


def _response(project: Project, db: Session, warning: str | None = None) -> RubricStudioResponse:
    items = _items(project.id, db)
    return RubricStudioResponse(
        project_id=project.id,
        status=project.rubric_studio_status,
        source_mode=project.rubric_source_mode,
        criteria=_criteria(items),
        warning=warning,
        manual_upload_available=True,
        all_criteria_reviewed=bool(items) and all(item.rubric_reviewed for item in items),
        generated_rubric_download_url=(f"/files/projects/{project.id}/rubric.pdf" if Path(project.rubric_file_path).suffix.lower() == ".pdf" and Path(project.rubric_file_path).exists() else None),
    )


def _write_draft(project: Project, result: StudioGenerationResult, db: Session) -> None:
    path = Path(project.rubric_file_path)
    storage.atomic_write_json(storage.project_dir(project.id) / "rubric_studio_draft.json", {"status": result.status, "criteria": result.criteria, "warning": result.warning})
    render_rubric_pdf(path, project_name=project.name, source_label="Rubric Studio · provisional draft", criteria=result.criteria)
    db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project.id).delete()
    for criterion in result.criteria:
        db.add(QuestionBankItem(
            id=str(uuid.uuid4()),
            project_id=project.id,
            question_number=criterion["question_number"],
            marks_possible=criterion["marks_possible"],
            key_points=criterion["key_points"],
            section_label=criterion.get("section_label"),
            question_text=criterion.get("question_text"),
            rubric_provenance=criterion["rubric_provenance"],
            rubric_confidence=criterion["rubric_confidence"],
            rubric_reviewed=False,
        ))
    project.rubric_studio_status = result.status
    project.rubric_locked = False
    project.question_bank_confirmed = False
    db.commit()


@router.get("/{project_id}/rubric-studio", response_model=RubricStudioResponse)
def get_rubric_studio(project_id: str, db: Session = Depends(get_db)) -> RubricStudioResponse:
    project = _project_or_404(project_id, db)
    if project.rubric_source_mode != "studio":
        raise HTTPException(status_code=409, detail="This project uses an uploaded rubric rather than Rubric Studio.")
    return _response(project, db)


@router.post("/{project_id}/rubric-studio/generate", response_model=RubricStudioResponse)
def generate_rubric_studio(project_id: str, db: Session = Depends(get_db)) -> RubricStudioResponse:
    project = _project_or_404(project_id, db)
    if project.rubric_source_mode != "studio":
        raise HTTPException(status_code=409, detail="Rubric Studio is not selected for this project.")
    if project.rubric_studio_status == "approved":
        raise HTTPException(status_code=409, detail="The approved rubric is locked; start a new project to regenerate it.")
    result = generate_draft(project.question_paper_file_path)
    if result.status in {"draft_ready", "partial"}:
        _write_draft(project, result, db)
    else:
        project.rubric_studio_status = result.status
        db.commit()
    return _response(project, db, result.warning)


@router.patch("/{project_id}/rubric-studio/{question_number}", response_model=RubricStudioCriterionResponse)
def update_rubric_criterion(project_id: str, question_number: str, payload: RubricStudioCriterionUpdate, db: Session = Depends(get_db)) -> RubricStudioCriterionResponse:
    project = _project_or_404(project_id, db)
    if project.rubric_source_mode != "studio" or project.rubric_locked:
        raise HTTPException(status_code=409, detail="This rubric is not editable.")
    item = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id, QuestionBankItem.question_number == question_number).one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Rubric criterion not found.")
    if payload.marks_possible is not None and payload.marks_possible < 0:
        raise HTTPException(status_code=422, detail="marks_possible must be non-negative.")
    if payload.marks_possible is not None:
        item.marks_possible = payload.marks_possible
    if payload.key_points is not None:
        item.key_points = payload.key_points
    if payload.section_label is not None:
        item.section_label = payload.section_label.strip() or None
    if payload.question_text is not None:
        item.question_text = payload.question_text.strip() or None
    if payload.rubric_reviewed is not None:
        item.rubric_reviewed = payload.rubric_reviewed
    db.commit()
    db.refresh(item)
    current_items = _items(project_id, db)
    render_rubric_pdf(Path(project.rubric_file_path), project_name=project.name, source_label="Rubric Studio · examiner-edited draft", criteria=[criterion.model_dump() for criterion in _criteria(current_items)])
    return _criteria([item])[0]


@router.post("/{project_id}/rubric-studio/approve", response_model=RubricStudioResponse)
def approve_rubric_studio(project_id: str, db: Session = Depends(get_db)) -> RubricStudioResponse:
    project = _project_or_404(project_id, db)
    if project.rubric_source_mode != "studio":
        raise HTTPException(status_code=409, detail="Rubric Studio is not selected for this project.")
    items = _items(project_id, db)
    if project.rubric_studio_status not in {"draft_ready", "partial"}:
        raise HTTPException(status_code=409, detail="This draft is incomplete. Generate a complete draft or use the manual rubric upload path.")
    incomplete = [item.question_number for item in items if not item.key_points or item.marks_possible is None]
    if incomplete:
        raise HTTPException(status_code=409, detail=f"Every generated criterion needs marks and criteria text before approval: {', '.join(incomplete)}.")
    for item in items:
        item.rubric_reviewed = True
    project.rubric_locked = True
    project.rubric_studio_status = "approved"
    project.question_bank_confirmed = False
    project.question_bank_marks_warning = None
    db.commit()
    return _response(project, db)


@router.post("/{project_id}/rubric-studio/manual-upload", response_model=RubricStudioResponse)
async def use_manual_rubric(project_id: str, rubric: UploadFile = File(...), db: Session = Depends(get_db)) -> RubricStudioResponse:
    project = _project_or_404(project_id, db)
    if project.rubric_source_mode != "studio":
        raise HTTPException(status_code=409, detail="Manual rubric fallback is available only from the Rubric Studio branch.")
    path = storage.project_dir(project_id) / "rubric.pdf"
    storage.save_upload(path, await read_validated_upload(rubric, "Rubric"))
    project.rubric_file_path = str(path)
    project.rubric_source_mode = "uploaded"
    project.rubric_studio_status = "manual_upload"
    project.rubric_locked = True
    project.question_bank_confirmed = False
    db.commit()
    warning = None
    try:
        _run_question_bank_extraction(db, project)
    except Exception as exc:  # noqa: BLE001 — manual upload remains available even if extraction is empty/failed
        project = db.get(Project, project_id)
        project.question_bank_marks_warning = "Official rubric saved, but automatic extraction failed. Add the criteria manually in Question Bank."
        db.commit()
        warning = "The official rubric was saved, but automatic extraction did not complete. Add or review criteria manually in Question Bank."
    project = db.get(Project, project_id)
    return _response(project, db, warning)
