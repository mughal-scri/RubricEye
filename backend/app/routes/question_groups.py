from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Project, QuestionBankItem, QuestionGroup
from app.schemas.models import QuestionGroupCreate, QuestionGroupResponse
from app.services.paper_structure import refresh_project_structure

router = APIRouter(prefix="/projects", tags=["question-groups"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _selection_units(group: QuestionGroup) -> list[list[str]]:
    units = json.loads(group.selection_units_json or "[]")
    return units or [[question] for question in json.loads(group.question_numbers_json or "[]")]


def _to_response(group: QuestionGroup) -> QuestionGroupResponse:
    return QuestionGroupResponse(
        id=group.id,
        project_id=group.project_id,
        group_name=group.group_name,
        selection_type=group.selection_type,
        question_numbers=json.loads(group.question_numbers_json or "[]"),
        n_required=group.n_required,
        selection_units=_selection_units(group),
        suggestion_confidence=group.suggestion_confidence,
        suggestion_evidence=group.suggestion_evidence,
        suggestion_status=group.suggestion_status,
    )


def _flatten_units(units: list[list[str]]) -> list[str]:
    return [question for unit in units for question in unit]


@router.get("/{project_id}/question-groups", response_model=list[QuestionGroupResponse])
def list_question_groups(project_id: str, db: Session = Depends(get_db)) -> list[QuestionGroupResponse]:
    _get_project_or_404(project_id, db)
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).all()
    return [_to_response(group) for group in groups]


@router.post("/{project_id}/question-groups", response_model=QuestionGroupResponse, status_code=201)
def create_question_group(project_id: str, payload: QuestionGroupCreate, db: Session = Depends(get_db)) -> QuestionGroupResponse:
    project = _get_project_or_404(project_id, db)

    group_name = payload.group_name.strip()
    if not group_name:
        raise HTTPException(status_code=400, detail="group_name cannot be empty.")
    if len(set(payload.question_numbers)) != len(payload.question_numbers):
        raise HTTPException(status_code=400, detail="question_numbers must not contain duplicates.")

    units = payload.selection_units or [[question] for question in payload.question_numbers]
    if any(not unit for unit in units):
        raise HTTPException(status_code=400, detail="selection_units cannot contain empty choices.")
    flattened = _flatten_units(units)
    if sorted(flattened) != sorted(payload.question_numbers):
        raise HTTPException(status_code=400, detail="selection_units must contain exactly the listed question numbers.")
    if len(set(flattened)) != len(flattened):
        raise HTTPException(status_code=400, detail="A question cannot appear in more than one selection unit.")

    known_questions = {item.question_number for item in db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()}
    unknown_questions = sorted(set(flattened) - known_questions)
    if unknown_questions:
        raise HTTPException(status_code=422, detail=f"Unknown question number(s): {', '.join(unknown_questions)}.")

    existing_groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).all()
    assigned_questions = {question for group in existing_groups for question in json.loads(group.question_numbers_json or "[]")}
    overlapping = sorted(set(flattened) & assigned_questions)
    if overlapping:
        raise HTTPException(status_code=409, detail=f"Question(s) already assigned to another group: {', '.join(overlapping)}.")

    if payload.selection_type not in ("compulsory", "choose_n_of_m"):
        raise HTTPException(status_code=400, detail="selection_type must be 'compulsory' or 'choose_n_of_m'.")
    if payload.selection_type == "choose_n_of_m":
        if not payload.n_required or payload.n_required < 1:
            raise HTTPException(status_code=400, detail="n_required must be a positive integer for choose_n_of_m groups.")
        if payload.n_required > len(units):
            raise HTTPException(status_code=400, detail="n_required cannot exceed the number of selectable choices.")

    group = QuestionGroup(
        id=str(uuid.uuid4()),
        project_id=project_id,
        group_name=group_name,
        selection_type=payload.selection_type,
        question_numbers_json=json.dumps(payload.question_numbers),
        selection_units_json=json.dumps(units),
        n_required=payload.n_required if payload.selection_type == "choose_n_of_m" else None,
        suggestion_status="confirmed",
    )
    db.add(group)
    refresh_project_structure(project, db)
    db.commit()
    db.refresh(group)
    return _to_response(group)


@router.post("/{project_id}/question-groups/{group_id}/confirm", response_model=QuestionGroupResponse)
def confirm_question_group(project_id: str, group_id: str, db: Session = Depends(get_db)) -> QuestionGroupResponse:
    project = _get_project_or_404(project_id, db)
    group = db.get(QuestionGroup, group_id)
    if not group or group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Question group not found.")
    group.suggestion_status = "confirmed"
    refresh_project_structure(project, db)
    db.commit()
    db.refresh(group)
    return _to_response(group)


@router.delete("/{project_id}/question-groups/{group_id}", status_code=204)
def delete_question_group(project_id: str, group_id: str, db: Session = Depends(get_db)) -> None:
    project = _get_project_or_404(project_id, db)
    group = db.get(QuestionGroup, group_id)
    if group and group.project_id == project_id:
        db.delete(group)
        refresh_project_structure(project, db)
        db.commit()
