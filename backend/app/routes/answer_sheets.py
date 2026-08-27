from __future__ import annotations

import json
import shutil
import uuid

import cv2
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AnswerSheet, GradingResult, Project, QuestionBankItem, QuestionGroup
from app.schemas.models import AnswerSheetDetail, AnswerSheetRegionUpdate, AnswerSheetSummary, RegionRef, ReportResponse
from app.services import storage
from app.services.pdf_validation import read_validated_upload
from app.services.cover_page_check import identity_page_indexes
from app.services.pdf_pipeline import pdf_to_ordered_images
from app.services.segmentation import _clamp_bbox, _has_overflow, build_question_region_map, load_template_map_pages, safe_region_filename_key
from app.services.page_correspondence import compare_page_labels
from app.services.question_grouping import resolve_region_keys_for_question
from app.services.reporting import generate_report, report_blockers

router = APIRouter(prefix="/projects", tags=["answer-sheets"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _report_url(sheet: AnswerSheet) -> str | None:
    if not sheet.report_path:
        return None
    return f"/files/projects/{sheet.project_id}/answer_sheets/{sheet.id}/examiner_report.pdf"


def _sheet_to_summary(sheet: AnswerSheet) -> AnswerSheetSummary:
    page_paths = json.loads(sheet.page_image_paths_json or "[]")
    return AnswerSheetSummary(
        id=sheet.id,
        project_id=sheet.project_id,
        roll_number=sheet.roll_number,
        uploaded_at=sheet.uploaded_at,
        deleted_at=sheet.deleted_at,
        page_count=len(page_paths),
        grading_status=sheet.grading_status,
        report_ready=bool(sheet.report_path),
        report_download_url=_report_url(sheet),
        completed_at=sheet.completed_at,
    )


def _sheet_to_detail(sheet: AnswerSheet) -> AnswerSheetDetail:
    page_paths = json.loads(sheet.page_image_paths_json or "[]")
    question_region_map = json.loads(sheet.question_region_map_json or "{}")
    region_preview_urls: dict[str, list[str]] = {}
    regions_dir = storage.answer_sheet_dir(sheet.project_id, sheet.id) / "regions"
    if regions_dir.exists():
        for key in question_region_map:
            previews = sorted(regions_dir.glob(f"{safe_region_filename_key(key)}_p*.png"))
            region_preview_urls[key] = [
                f"/files/projects/{sheet.project_id}/answer_sheets/{sheet.id}/regions/{path.name}"
                for path in previews
            ]

    mapped = {
        key: [
            RegionRef(
                page_index=ref["page_index"],
                bbox=ref["bbox"],
                nominal_bbox=ref.get("nominal_bbox"),
                overflow_detected=bool(ref.get("overflow_detected", False)),
                alignment_method=ref.get("alignment_method", "feature"),
                alignment_confidence=ref.get("alignment_confidence", "high"),
                alignment_uncertain=bool(ref.get("alignment_uncertain", False)),
                page_correspondence_uncertain=bool(ref.get("page_correspondence_uncertain", False)),
            )
            for ref in refs
        ]
        for key, refs in question_region_map.items()
    }
    return AnswerSheetDetail(
        id=sheet.id,
        project_id=sheet.project_id,
        roll_number=sheet.roll_number,
        uploaded_at=sheet.uploaded_at,
        deleted_at=sheet.deleted_at,
        page_count=len(page_paths),
        grading_status=sheet.grading_status,
        report_ready=bool(sheet.report_path),
        report_download_url=_report_url(sheet),
        completed_at=sheet.completed_at,
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
        .filter(AnswerSheet.project_id == project_id, AnswerSheet.deleted_at.is_(None))
        .order_by(AnswerSheet.uploaded_at.desc())
        .all()
    )
    return [_sheet_to_summary(sheet) for sheet in sheets]


@router.get("/{project_id}/answer-sheets/trash", response_model=list[AnswerSheetSummary])
def list_deleted_answer_sheets(project_id: str, db: Session = Depends(get_db)) -> list[AnswerSheetSummary]:
    _get_project_or_404(project_id, db)
    sheets = (
        db.query(AnswerSheet)
        .filter(AnswerSheet.project_id == project_id, AnswerSheet.deleted_at.is_not(None))
        .order_by(AnswerSheet.deleted_at.desc())
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
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is not None:
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
    if not roll_number.strip():
        raise HTTPException(status_code=400, detail="Roll number is required.")

    pdf_bytes = await read_validated_upload(pdf, "Answer sheet")
    answer_sheet_id = str(uuid.uuid4())
    sheet_dir = storage.answer_sheet_dir(project_id, answer_sheet_id)
    pdf_path = sheet_dir / "original.pdf"
    storage.save_upload(pdf_path, pdf_bytes)

    try:
        page_paths = pdf_to_ordered_images(str(pdf_path), str(sheet_dir))
    except Exception as exc:  # noqa: BLE001 — failed processing must not leave an upload artifact
        shutil.rmtree(sheet_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Answer sheet could not be rendered into readable pages.") from exc
    if not page_paths:
        shutil.rmtree(sheet_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="PDF contains no pages.")

    project_dir = storage.project_dir(project_id)
    template_pages = load_template_map_pages(project_dir)
    template_page_count = max((int(page.get("page_number") or 0) for page in template_pages), default=0)
    if template_page_count and len(page_paths) != template_page_count:
        shutil.rmtree(sheet_dir, ignore_errors=True)
        raise HTTPException(
            status_code=409,
            detail=(
                f"This answer booklet has {len(page_paths)} pages; the confirmed template has "
                f"{template_page_count}. Check the scan order and make sure no pages are missing or extra before uploading."
            ),
        )

    uncertain_page_numbers: set[int] = set()
    for page in template_pages:
        if not page.get("regions"):
            continue
        state, expected_labels, detected_labels = compare_page_labels(page, page_paths[page["page_number"] - 1])
        if state == "mismatch":
            shutil.rmtree(sheet_dir, ignore_errors=True)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Answer page {page['page_number']} does not match the confirmed template. "
                    f"Expected labels {', '.join(sorted(expected_labels))}; detected {', '.join(sorted(detected_labels))}. "
                    "Check page order or re-upload the original booklet."
                ),
            )
        if state == "uncertain":
            uncertain_page_numbers.add(int(page["page_number"]))

    alignment_reference = {}
    alignment_path = project_dir / "alignment_reference.json"
    if alignment_path.exists():
        alignment_reference = json.loads(alignment_path.read_text(encoding="utf-8"))
    elif project.alignment_reference_json:
        alignment_reference = json.loads(project.alignment_reference_json)

    identity_indexes = set(identity_page_indexes(str(pdf_path), rendered_page_paths=page_paths))
    answer_page_numbers = [page["page_number"] for page in template_pages if page.get("regions")]
    if answer_page_numbers:
        first_answer_page = min(answer_page_numbers)
        identity_indexes.update(range(0, max(0, first_answer_page - 1)))
    # Identity/front-matter pages remain stored locally for audit/review, but are
    # never passed into segmentation or grading. Exclusion is learned from the
    # uploaded blank booklet's own semantic map, not a fixed page number.
    if len(identity_indexes) == len(page_paths):
        shutil.rmtree(sheet_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Upload contains no answer pages after local front-matter exclusion.")

    regions_dir = sheet_dir / "regions"
    try:
        question_region_map, _preview_paths = build_question_region_map(
            page_paths,
            template_pages,
            alignment_reference,
            regions_dir,
            skip_page_indices=identity_indexes,
            uncertain_page_numbers=uncertain_page_numbers,
        )
    except Exception as exc:  # noqa: BLE001 — segmentation failures are recoverable upload errors
        shutil.rmtree(sheet_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Answer sheet segmentation could not be completed; review the template and re-upload.") from exc

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


@router.put("/{project_id}/answer-sheets/{answer_sheet_id}/regions/{question_key}", response_model=AnswerSheetDetail)
def update_answer_sheet_region(
    project_id: str,
    answer_sheet_id: str,
    question_key: str,
    payload: AnswerSheetRegionUpdate,
    db: Session = Depends(get_db),
) -> AnswerSheetDetail:
    _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")

    page_paths = json.loads(sheet.page_image_paths_json or "[]")
    question_region_map = json.loads(sheet.question_region_map_json or "{}")
    refs = question_region_map.get(question_key)
    if not refs:
        raise HTTPException(status_code=404, detail=f"Question region '{question_key}' was not found.")
    if payload.page_index is None and len(refs) > 1:
        raise HTTPException(status_code=422, detail="page_index is required when a question has multiple region slices.")
    ref_index = next((index for index, ref in enumerate(refs) if payload.page_index is None or ref.get("page_index") == payload.page_index), None)
    if ref_index is None:
        raise HTTPException(status_code=404, detail=f"Question region '{question_key}' was not found on the requested page.")

    ref = refs[ref_index]
    page_index = int(ref.get("page_index", -1))
    if page_index < 0 or page_index >= len(page_paths):
        raise HTTPException(status_code=422, detail="The selected region points to an unavailable page image.")
    image = cv2.imread(page_paths[page_index])
    if image is None:
        raise HTTPException(status_code=422, detail="The selected page image could not be read.")
    bbox = payload.bbox
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        raise HTTPException(status_code=422, detail="Region bbox must have positive width and height.")
    bbox = _clamp_bbox(bbox, image.shape[1], image.shape[0])
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        raise HTTPException(status_code=422, detail="Region bbox must remain inside the page image.")

    x1, y1, x2, y2 = bbox
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        raise HTTPException(status_code=422, detail="The selected region produced an empty crop.")
    regions_dir = storage.answer_sheet_dir(project_id, answer_sheet_id) / "regions"
    preview_path = regions_dir / f"{safe_region_filename_key(question_key)}_p{page_index + 1}.png"
    encoded = cv2.imencode(".png", crop)
    if not encoded[0]:
        raise HTTPException(status_code=422, detail="The selected region could not be encoded.")
    storage.atomic_write_bytes(preview_path, encoded[1].tobytes())

    ref["bbox"] = bbox
    if ref.get("nominal_bbox"):
        ref["overflow_detected"] = _has_overflow(image, ref["nominal_bbox"], bbox)
    question_region_map[question_key] = refs
    sheet.question_region_map_json = json.dumps(question_region_map)

    affected_results = [
        result
        for result in db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet.id).all()
        if resolve_region_keys_for_question(result.question_number, [question_key])
    ]
    if affected_results:
        for result in affected_results:
            result.ai_score = None
            result.ai_rationale = None
            result.part_scores_json = "[]"
            result.transcription_summary = None
            result.human_confirmed_score = None
            result.human_reviewer_note = None
            result.reviewed = False
            result.grading_status = "pending"
            result.choice_status = "graded"
            result.error_message = "Crop edited; re-grading required."
            result.graded_at = None
        sheet.grading_status = "not_graded"
        sheet.report_path = None
        sheet.report_generated_at = None
        sheet.completed_at = None
    db.commit()
    db.refresh(sheet)
    return _sheet_to_detail(sheet)


@router.post("/{project_id}/answer-sheets/{answer_sheet_id}/regions/{question_key}/confirm-overflow", response_model=AnswerSheetDetail)
def confirm_answer_sheet_region_overflow(
    project_id: str,
    answer_sheet_id: str,
    question_key: str,
    page_index: int | None = None,
    db: Session = Depends(get_db),
) -> AnswerSheetDetail:
    """Acknowledge examiner review of overflow for one question.

    This deliberately clears all slices belonging to the selected question,
    without altering their crops or any other question's segmentation data.
    The warning is cleared only after the examiner has inspected/corrected the
    source crop.
    """
    _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")

    question_region_map = json.loads(sheet.question_region_map_json or "{}")
    refs = question_region_map.get(question_key)
    if not refs:
        raise HTTPException(status_code=404, detail=f"Question region '{question_key}' was not found.")
    selected = [ref for ref in refs if page_index is None or int(ref.get("page_index", -1)) == page_index]
    if not selected:
        raise HTTPException(status_code=404, detail=f"Question region '{question_key}' was not found on the requested page.")
    for ref in selected:
        ref["overflow_detected"] = False

    question_region_map[question_key] = refs
    sheet.question_region_map_json = json.dumps(question_region_map)
    for result in db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet.id).all():
        if resolve_region_keys_for_question(result.question_number, [question_key]):
            result.truncation_flag = False
    db.commit()
    db.refresh(sheet)
    return _sheet_to_detail(sheet)


@router.post("/{project_id}/answer-sheets/{answer_sheet_id}/alignment/confirm", response_model=AnswerSheetDetail)
def confirm_answer_sheet_alignment(
    project_id: str,
    answer_sheet_id: str,
    db: Session = Depends(get_db),
) -> AnswerSheetDetail:
    """Record examiner confirmation of the stored page/region correspondence.

    Automatic alignment remains conservative and continues to flag uncertain
    pages at upload time. This explicit, sheet-scoped acknowledgement allows an
    examiner who has inspected the page overlay to clear only those review
    markers; it does not change any bounding boxes or other answer sheets.
    """
    _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")

    question_region_map = json.loads(sheet.question_region_map_json or "{}")
    uncertain_found = False
    for refs in question_region_map.values():
        for ref in refs:
            if ref.get("alignment_uncertain") or ref.get("page_correspondence_uncertain"):
                uncertain_found = True
            ref["alignment_uncertain"] = False
            ref["page_correspondence_uncertain"] = False
    if not uncertain_found:
        raise HTTPException(status_code=409, detail="No uncertain page alignment remains to confirm.")
    sheet.question_region_map_json = json.dumps(question_region_map)
    db.commit()
    db.refresh(sheet)
    return _sheet_to_detail(sheet)


@router.delete("/{project_id}/answer-sheets/{answer_sheet_id}", status_code=204)
def delete_answer_sheet(project_id: str, answer_sheet_id: str, db: Session = Depends(get_db)) -> None:
    _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")
    sheet.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{project_id}/answer-sheets/{answer_sheet_id}/restore", response_model=AnswerSheetSummary)
def restore_answer_sheet(project_id: str, answer_sheet_id: str, db: Session = Depends(get_db)) -> AnswerSheetSummary:
    _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is None:
        raise HTTPException(status_code=404, detail="Answer sheet not found in Trash.")
    sheet.deleted_at = None
    db.commit()
    db.refresh(sheet)
    return _sheet_to_summary(sheet)


@router.delete("/{project_id}/answer-sheets/{answer_sheet_id}/permanent", status_code=204)
def permanently_delete_answer_sheet(project_id: str, answer_sheet_id: str, db: Session = Depends(get_db)) -> None:
    _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is None:
        raise HTTPException(status_code=404, detail="Answer sheet not found in Trash.")
    sheet_dir = storage.answer_sheet_dir(project_id, answer_sheet_id)
    db.delete(sheet)
    db.commit()
    shutil.rmtree(sheet_dir, ignore_errors=True)


@router.post("/{project_id}/answer-sheets/{answer_sheet_id}/report", response_model=ReportResponse)
def create_examiner_report(project_id: str, answer_sheet_id: str, db: Session = Depends(get_db)) -> ReportResponse:
    project = _get_project_or_404(project_id, db)
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")

    results = db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet.id).order_by(GradingResult.question_number).all()
    blockers = report_blockers(results)
    if blockers:
        raise HTTPException(status_code=409, detail="Report cannot be generated until review is complete: " + "; ".join(blockers))

    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).all()
    question_text_by_number = {
        item.question_number: item.question_text
        for item in db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
        if item.question_text
    }
    report_path = generate_report(project, sheet, results, groups, question_text_by_number)
    sheet.report_path = str(report_path)
    sheet.report_generated_at = datetime.now(timezone.utc)
    sheet.completed_at = sheet.report_generated_at
    sheet.grading_status = "complete"
    db.commit()

    return ReportResponse(
        answer_sheet_id=sheet.id,
        report_ready=True,
        report_download_url=_report_url(sheet),
        completed_at=sheet.completed_at,
        blockers=[],
    )
