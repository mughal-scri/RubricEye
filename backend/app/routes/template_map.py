from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Project, TemplateMapPage
from app.schemas.models import (
    BBox,
    TemplateMapPageResponse,
    TemplateMapResponse,
    TemplateMapUpdateRequest,
    TemplateRegion,
)
from app.services import storage
from app.services.template_derivation import regions_from_json, regions_to_json

router = APIRouter(prefix="/projects", tags=["template-map"])


@dataclass(frozen=True)
class _RegionValidationPayload:
    page_number: int
    question_number: str
    part_label: str
    bbox: list


def _page_image_url(project_id: str, page_number: int) -> str:
    return f"/files/projects/{project_id}/blank_booklet_pages/page_{page_number:03d}.png"


def _build_template_map_response(project: Project, pages: list[TemplateMapPage]) -> TemplateMapResponse:
    page_responses: list[TemplateMapPageResponse] = []
    for page in sorted(pages, key=lambda item: item.page_number):
        regions = [
            TemplateRegion(
                question_number=region.question_number,
                part_label=region.part_label,
                bbox=BBox.from_list(region.bbox),
            )
            for region in regions_from_json(page.regions_json)
        ]
        page_responses.append(
            TemplateMapPageResponse(
                page_number=page.page_number,
                page_image_url=_page_image_url(project.id, page.page_number),
                regions=regions,
            )
        )
    return TemplateMapResponse(
        project_id=project.id,
        confirmed=project.template_map_confirmed,
        status=project.template_map_status,
        pages=page_responses,
    )


def _validate_regions(regions: list, pages: dict[int, TemplateMapPage], *, require_any: bool) -> dict[int, list[dict]]:
    if require_any and not regions:
        raise HTTPException(status_code=422, detail="At least one mapped template region is required before confirmation.")
    grouped: dict[int, list[dict]] = {}
    seen_on_page: set[tuple[int, str, str]] = set()
    for region in regions:
        page_number = int(region.page_number)
        page = pages.get(page_number)
        if page is None or page_number < 1:
            raise HTTPException(status_code=422, detail=f"Unknown template page number: {page_number}.")
        question_number = region.question_number.strip()
        part_label = region.part_label.strip()
        if not question_number:
            raise HTTPException(status_code=422, detail=f"Page {page_number} contains a region without a question label.")
        if len(region.bbox) != 4:
            raise HTTPException(status_code=422, detail=f"Region {question_number} on page {page_number} must have four coordinates.")
        x1, y1, x2, y2 = (int(value) for value in region.bbox)
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            raise HTTPException(status_code=422, detail=f"Region {question_number} on page {page_number} has invalid bbox coordinates.")
        image_path = Path(page.page_image_path)
        if image_path.exists():
            try:
                with Image.open(image_path) as image:
                    width, height = image.size
            except Exception as exc:  # noqa: BLE001 — malformed local page is a review error
                raise HTTPException(status_code=422, detail=f"Template page {page_number} image could not be read.") from exc
            if x2 > width or y2 > height:
                raise HTTPException(status_code=422, detail=f"Region {question_number} on page {page_number} lies outside the page image.")
        identity = (page_number, question_number.casefold(), part_label.casefold())
        if identity in seen_on_page:
            raise HTTPException(status_code=422, detail=f"Duplicate region identity {question_number}{part_label} on page {page_number}.")
        seen_on_page.add(identity)
        grouped.setdefault(page_number, []).append({"question_number": question_number, "part_label": part_label, "bbox": [x1, y1, x2, y2]})
    return grouped


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.get("/{project_id}/template-map", response_model=TemplateMapResponse)
def get_template_map(project_id: str, db: Session = Depends(get_db)) -> TemplateMapResponse:
    project = _get_project_or_404(project_id, db)
    pages = (
        db.query(TemplateMapPage)
        .filter(TemplateMapPage.project_id == project_id)
        .order_by(TemplateMapPage.page_number)
        .all()
    )
    return _build_template_map_response(project, pages)


@router.put("/{project_id}/template-map", response_model=TemplateMapResponse)
def update_template_map(
    project_id: str,
    payload: TemplateMapUpdateRequest,
    db: Session = Depends(get_db),
) -> TemplateMapResponse:
    project = _get_project_or_404(project_id, db)
    if project.template_map_confirmed:
        raise HTTPException(status_code=409, detail="Template map is already confirmed and locked.")

    pages = {
        page.page_number: page
        for page in db.query(TemplateMapPage).filter(TemplateMapPage.project_id == project_id).all()
    }
    grouped = _validate_regions(payload.regions, pages, require_any=False)

    for page_number, page in pages.items():
        page.regions_json = json.dumps(grouped.get(page_number, []))
    project.template_map_status = "needs_review"
    db.commit()

    refreshed_pages = (
        db.query(TemplateMapPage)
        .filter(TemplateMapPage.project_id == project_id)
        .order_by(TemplateMapPage.page_number)
        .all()
    )
    return _build_template_map_response(project, refreshed_pages)


@router.post("/{project_id}/template-map/confirm", response_model=TemplateMapResponse)
def confirm_template_map(project_id: str, db: Session = Depends(get_db)) -> TemplateMapResponse:
    project = _get_project_or_404(project_id, db)
    if project.template_map_confirmed:
        raise HTTPException(status_code=409, detail="Template map is already confirmed.")

    pages = (
        db.query(TemplateMapPage)
        .filter(TemplateMapPage.project_id == project_id)
        .order_by(TemplateMapPage.page_number)
        .all()
    )
    if not pages:
        raise HTTPException(status_code=400, detail="No template map pages to confirm.")
    all_regions = [
        _RegionValidationPayload(
            page_number=page.page_number,
            question_number=str(region.get("question_number", "")),
            part_label=str(region.get("part_label", "")),
            bbox=region.get("bbox", []),
        )
        for page in pages
        for region in json.loads(page.regions_json or "[]")
    ]
    _validate_regions(all_regions, {page.page_number: page for page in pages}, require_any=True)

    payload_pages = []
    for page in pages:
        payload_pages.append(
            {
                "page_number": page.page_number,
                "page_image_path": page.page_image_path,
                "regions": json.loads(page.regions_json or "[]"),
            }
        )

    project_dir = storage.project_dir(project.id)
    storage.atomic_write_json(
        project_dir / "template_map.json",
        {"pages": payload_pages},
    )
    if project.alignment_reference_json:
        storage.atomic_write_json(
            project_dir / "alignment_reference.json",
            json.loads(project.alignment_reference_json),
        )

    project.template_map_confirmed = True
    project.template_map_status = "confirmed"
    db.commit()

    return _build_template_map_response(project, pages)


@router.post("/{project_id}/template-map/unlock", response_model=TemplateMapResponse)
def unlock_template_map(project_id: str, db: Session = Depends(get_db)) -> TemplateMapResponse:
    """Unlock the template map for re-editing.

    Blocked if any AnswerSheet has been uploaded against this project — those sheets
    were segmented against the current confirmed map, so unlocking and changing regions
    would make their segmentation data inconsistent. The examiner must delete all uploaded
    answer sheets first (or start a new project) before the map can be re-edited.

    If no answer sheets exist, unlocking is always safe: re-confirm resets the map file
    on disk and re-locks it.
    """
    from app.db.models import AnswerSheet  # local import to avoid circular at module level

    project = _get_project_or_404(project_id, db)
    if not project.template_map_confirmed:
        raise HTTPException(status_code=409, detail="Template map is not currently confirmed.")

    sheet_count = (
        db.query(AnswerSheet)
        .filter(AnswerSheet.project_id == project_id)
        .count()
    )
    if sheet_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{sheet_count} answer sheet(s) have already been uploaded and segmented "
                "against the current template map. Delete all answer sheets first before "
                "unlocking the template map for re-editing."
            ),
        )

    project.template_map_confirmed = False
    project.template_map_status = "needs_review"
    db.commit()

    pages = (
        db.query(TemplateMapPage)
        .filter(TemplateMapPage.project_id == project_id)
        .order_by(TemplateMapPage.page_number)
        .all()
    )
    return _build_template_map_response(project, pages)
