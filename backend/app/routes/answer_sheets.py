from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AnswerSheet, Project
from app.schemas.models import AnswerSheetDetail, AnswerSheetSummary, RegionRef
from app.services import storage
from app.services.cover_page_check import looks_like_identity_cover_page
from app.services.pdf_pipeline import pdf_to_ordered_images
from app.services.segmentation import build_question_region_map, load_template_map_pages

router = APIRouter(prefix="/projects", tags=["answer-sheets"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _sheet_to_summary(sheet: AnswerSheet) -> AnswerSheetSummary:
    page_paths = json.loads(sheet.page_image_paths_json or "[]")
    return AnswerSheetSummary(
        id=sheet.id,
        project_id=sheet.project_id,
        roll_number=sheet.roll_number,
        uploaded_at=sheet.uploaded_at,
        page_count=len(page_paths),
        grading_status=sheet.grading_status,
    )


def _sheet_to_detail(sheet: AnswerSheet) -> AnswerSheetDetail:
    page_paths = json.loads(sheet.page_image_paths_json or "[]")
    question_region_map = json.loads(sheet.question_region_map_json or "{}")
    region_preview_urls: dict[str, list[str]] = {}
    regions_dir = storage.answer_sheet_dir(sheet.project_id, sheet.id) / "regions"
    if regions_dir.exists():
        for key in question_region_map:
            previews = sorted(regions_dir.glob(f"{key}_p*.png"))
            region_preview_urls[key] = [
                f"/files/projects/{sheet.project_id}/answer_sheets/{sheet.id}/regions/{path.name}"
                for path in previews
            ]

    mapped = {
        key: [RegionRef(page_index=ref["page_index"], bbox=ref["bbox"]) for ref in refs]
        for key, refs in question_region_map.items()
    }
    return AnswerSheetDetail(
        id=sheet.id,
        project_id=sheet.project_id,
        roll_number=sheet.roll_number,
        uploaded_at=sheet.uploaded_at,
        page_count=len(page_paths),
        grading_status=sheet.grading_status,
        page_image_urls=[
            f"/files/projects/{sheet.project_id}/answer_sheets/{sheet.id}/page_{idx + 1:03d}.png"
            for idx in range(len(page_paths))
        ],
        question_region_map=mapped,
        region_preview_urls=region_preview_urls,
    )


@router.get("/{project_id}/answer-sheets", response_model=list[AnswerSheetSummary])
def list_answer_sheets(project_id: str, db: Session = Depends(get_db)) -> list[AnswerSheetSummary]:
    _get_project_or_404(project_id, db)
    sheets = (
        db.query(AnswerSheet)
        .filter(AnswerSheet.project_id == project_id)
        .order_by(AnswerSheet.uploaded_at.desc())
        .all()
    )
    return [_sheet_to_summary(sheet) for sheet in sheets]


@router.get("/{project_id}/answer-sheets/{answer_sheet_id}", response_model=AnswerSheetDetail)
def get_answer_sheet(
    project_id: str,
    answer_sheet_id: str,
    db: Session = Depends(get_db),
) -> AnswerSheetDetail:
    _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")
    return _sheet_to_detail(sheet)


@router.post("/{project_id}/answer-sheets", response_model=AnswerSheetDetail, status_code=201)
async def upload_answer_sheet(
    project_id: str,
    roll_number: str = Form(...),
    pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> AnswerSheetDetail:
    project = _get_project_or_404(project_id, db)
    if not project.template_map_confirmed:
        raise HTTPException(
            status_code=409,
            detail="Template map must be confirmed before uploading answer sheets.",
        )
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Answer sheet must be a PDF file.")
    if not roll_number.strip():
        raise HTTPException(status_code=400, detail="Roll number is required.")

    answer_sheet_id = str(uuid.uuid4())
    sheet_dir = storage.answer_sheet_dir(project_id, answer_sheet_id)
    pdf_path = sheet_dir / "original.pdf"
    pdf_bytes = await pdf.read()
    storage.save_upload(pdf_path, pdf_bytes)

    page_paths = pdf_to_ordered_images(str(pdf_path), str(sheet_dir))
    if not page_paths:
        raise HTTPException(status_code=400, detail="PDF contains no pages.")

    is_identity_page, reason = looks_like_identity_cover_page(page_paths[0])
    if is_identity_page:
        raise HTTPException(
            status_code=422,
            detail=f"Upload rejected: {reason} Remove identity pages before scanning.",
        )

    project_dir = storage.project_dir(project_id)
    alignment_reference = {}
    alignment_path = project_dir / "alignment_reference.json"
    if alignment_path.exists():
        alignment_reference = json.loads(alignment_path.read_text(encoding="utf-8"))
    elif project.alignment_reference_json:
        alignment_reference = json.loads(project.alignment_reference_json)

    template_pages = load_template_map_pages(project_dir)
    regions_dir = sheet_dir / "regions"
    question_region_map, _preview_paths = build_question_region_map(
        page_paths,
        template_pages,
        alignment_reference,
        regions_dir,
    )

    sheet = AnswerSheet(
        id=answer_sheet_id,
        project_id=project_id,
        roll_number=roll_number.strip(),
        original_pdf_path=str(pdf_path),
        page_image_paths_json=json.dumps(page_paths),
        question_region_map_json=json.dumps(question_region_map),
    )
    db.add(sheet)
    db.commit()
    db.refresh(sheet)
    return _sheet_to_detail(sheet)
