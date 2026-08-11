from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Project, QuestionGroup
from app.schemas.models import QuestionGroupCreate, QuestionGroupResponse

router = APIRouter(prefix="/projects", tags=["question-groups"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _to_response(group: QuestionGroup) -> QuestionGroupResponse:
    return QuestionGroupResponse(
        id=group.id,
        project_id=group.project_id,
        group_name=group.group_name,
        selection_type=group.selection_type,
        question_numbers=json.loads(group.question_numbers_json or "[]"),
        n_required=group.n_required,
    )


@router.get("/{project_id}/question-groups", response_model=list[QuestionGroupResponse])
def list_question_groups(project_id: str, db: Session = Depends(get_db)) -> list[QuestionGroupResponse]:
    _get_project_or_404(project_id, db)
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).all()
    return [_to_response(g) for g in groups]


@router.post("/{project_id}/question-groups", response_model=QuestionGroupResponse, status_code=201)
def create_question_group(
    project_id: str, payload: QuestionGroupCreate, db: Session = Depends(get_db)
) -> QuestionGroupResponse:
    _get_project_or_404(project_id, db)

    if payload.selection_type not in ("compulsory", "choose_n_of_m"):
        raise HTTPException(status_code=400, detail="selection_type must be 'compulsory' or 'choose_n_of_m'.")
    if payload.selection_type == "choose_n_of_m":
        if not payload.n_required or payload.n_required < 1:
            raise HTTPException(status_code=400, detail="n_required must be a positive integer for choose_n_of_m groups.")
        if payload.n_required > len(payload.question_numbers):
            raise HTTPException(status_code=400, detail="n_required cannot exceed the number of listed questions.")

    group = QuestionGroup(
        id=str(uuid.uuid4()),
        project_id=project_id,
        group_name=payload.group_name.strip(),
        selection_type=payload.selection_type,
        question_numbers_json=json.dumps(payload.question_numbers),
        n_required=payload.n_required if payload.selection_type == "choose_n_of_m" else None,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return _to_response(group)


@router.delete("/{project_id}/question-groups/{group_id}", status_code=204)
def delete_question_group(project_id: str, group_id: str, db: Session = Depends(get_db)) -> None:
    _get_project_or_404(project_id, db)
    group = db.get(QuestionGroup, group_id)
    if group and group.project_id == project_id:
        db.delete(group)
        db.commit()
