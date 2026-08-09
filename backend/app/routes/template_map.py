from __future__ import annotations

import json
from pathlib import Path

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


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
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
    grouped: dict[int, list] = {}
    for region in payload.regions:
        if region.page_number not in pages:
            raise HTTPException(status_code=400, detail=f"Unknown page number: {region.page_number}")
        x1, y1, x2, y2 = region.bbox
        if x2 <= x1 or y2 <= y1:
            raise HTTPException(status_code=400, detail="Invalid bbox coordinates.")
        grouped.setdefault(region.page_number, []).append(
            {
                "question_number": region.question_number.strip(),
                "part_label": region.part_label.strip(),
                "bbox": [x1, y1, x2, y2],
            }
        )

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
