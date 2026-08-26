from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Project, QuestionBankItem, QuestionGroup
from app.schemas.models import QuestionBankConfirmResponse, QuestionBankItemResponse, QuestionBankItemUpdate, QuestionBankListResponse
from app.services.paper_structure import calculate_structure, infer_group_suggestions, refresh_project_structure
from app.services.question_bank_extractor import find_stated_total

router = APIRouter(prefix="/projects", tags=["question-bank"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _group_dicts(project_id: str, db: Session) -> list[dict]:
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).all()
    return [
        {
            "id": group.id,
            "group_name": group.group_name,
            "selection_type": group.selection_type,
            "question_numbers": json.loads(group.question_numbers_json or "[]"),
            "selection_units": json.loads(group.selection_units_json or "[]") or [[question] for question in json.loads(group.question_numbers_json or "[]")],
            "n_required": group.n_required,
        }
        for group in groups
    ]


def _ensure_inferred_groups(project: Project, items: list[QuestionBankItem], db: Session) -> None:
    if db.query(QuestionGroup).filter(QuestionGroup.project_id == project.id).count() > 0:
        return
    item_dicts = [{"question_number": item.question_number, "marks_possible": item.marks_possible} for item in items]
    suggestions = infer_group_suggestions(project.question_paper_file_path, item_dicts)
    assigned: set[str] = set()
    for suggestion in suggestions:
        flat = [question for unit in suggestion.selection_units for question in unit]
        if not flat or assigned.intersection(flat):
            continue
        group = QuestionGroup(
            id=str(uuid.uuid4()),
            project_id=project.id,
            group_name=suggestion.group_name,
            selection_type=suggestion.selection_type,
            question_numbers_json=json.dumps(flat),
            selection_units_json=json.dumps(suggestion.selection_units),
            n_required=suggestion.n_required,
            suggestion_confidence=suggestion.confidence,
            suggestion_evidence=suggestion.evidence,
            suggestion_status="provisional",
        )
        db.add(group)
        assigned.update(flat)
    db.flush()


@router.get("/{project_id}/question-bank", response_model=QuestionBankListResponse)
def list_question_bank(project_id: str, db: Session = Depends(get_db)) -> QuestionBankListResponse:
    _get_project_or_404(project_id, db)
    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    return QuestionBankListResponse(project_id=project_id, confirmed=_get_project_or_404(project_id, db).question_bank_confirmed, items=[QuestionBankItemResponse.model_validate(item) for item in items])


@router.post("/{project_id}/question-bank", response_model=QuestionBankItemResponse, status_code=201)
def add_question_bank_item(project_id: str, question_number: str, marks_possible: int | None = None, key_points: str | None = None, db: Session = Depends(get_db)) -> QuestionBankItemResponse:
    project = _get_project_or_404(project_id, db)
    if project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank is already confirmed and locked.")
    normalized_question_number = question_number.strip()
    if not normalized_question_number:
        raise HTTPException(status_code=400, detail="question_number is required.")
    if marks_possible is not None and marks_possible < 0:
        raise HTTPException(status_code=422, detail="marks_possible must be non-negative.")
    duplicate = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id, QuestionBankItem.question_number == normalized_question_number).one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="A question with this number already exists in the question bank.")
    item = QuestionBankItem(id=str(uuid.uuid4()), project_id=project_id, question_number=normalized_question_number, marks_possible=marks_possible, key_points=key_points)
    db.add(item)
    db.commit()
    db.refresh(item)
    return QuestionBankItemResponse.model_validate(item)


@router.patch("/{project_id}/question-bank/{question_number}", response_model=QuestionBankItemResponse)
def update_question_bank_item(project_id: str, question_number: str, payload: QuestionBankItemUpdate, db: Session = Depends(get_db)) -> QuestionBankItemResponse:
    project = _get_project_or_404(project_id, db)
    if project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank is already confirmed and locked.")
    item = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id, QuestionBankItem.question_number == question_number).one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Question bank item not found.")
    if payload.marks_possible is not None:
        if payload.marks_possible < 0:
            raise HTTPException(status_code=422, detail="marks_possible must be non-negative.")
        item.marks_possible = payload.marks_possible
    if payload.key_points is not None:
        item.key_points = payload.key_points
    db.commit()
    db.refresh(item)
    return QuestionBankItemResponse.model_validate(item)


@router.delete("/{project_id}/question-bank/{question_number}", status_code=204)
def delete_question_bank_item(project_id: str, question_number: str, db: Session = Depends(get_db)) -> None:
    project = _get_project_or_404(project_id, db)
    if project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank is already confirmed and locked.")
    item = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id, QuestionBankItem.question_number == question_number).one_or_none()
    if item:
        db.delete(item)
        db.commit()


@router.post("/{project_id}/question-bank/confirm", response_model=QuestionBankConfirmResponse)
def confirm_question_bank(project_id: str, db: Session = Depends(get_db)) -> QuestionBankConfirmResponse:
    project = _get_project_or_404(project_id, db)
    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    if not items:
        raise HTTPException(status_code=400, detail="Cannot confirm an empty question bank.")

    _ensure_inferred_groups(project, items, db)
    structure = refresh_project_structure(project, db)
    project.question_bank_confirmed = True
    db.commit()

    return QuestionBankConfirmResponse(
        project_id=project_id,
        confirmed=True,
        total_marks_extracted=structure.raw_total,
        total_marks_on_paper=structure.stated_total,
        marks_mismatch_warning=project.question_bank_marks_warning,
        effective_total=structure.effective_total,
        structure_status=structure.status,
        structure_warning=structure.warning,
    )


@router.post("/{project_id}/question-bank/unlock", response_model=QuestionBankListResponse)
def unlock_question_bank(project_id: str, db: Session = Depends(get_db)) -> QuestionBankListResponse:
    from app.db.models import AnswerSheet, GradingResult

    project = _get_project_or_404(project_id, db)
    if not project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank is not currently confirmed.")
    grading_count = db.query(GradingResult).join(AnswerSheet, GradingResult.answer_sheet_id == AnswerSheet.id).filter(AnswerSheet.project_id == project_id).count()
    group_count = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).count()
    blockers = []
    if grading_count > 0:
        blockers.append(f"{grading_count} grading result(s)")
    if group_count > 0:
        blockers.append(f"{group_count} question group(s)")
    if blockers:
        raise HTTPException(status_code=409, detail=f"Cannot unlock safely while dependent records exist: {', '.join(blockers)}.")
    project.question_bank_confirmed = False
    project.question_bank_marks_warning = None
    project.question_bank_structure_status = "unresolved"
    db.commit()
    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    return QuestionBankListResponse(project_id=project_id, confirmed=False, items=[QuestionBankItemResponse.model_validate(item) for item in items])
