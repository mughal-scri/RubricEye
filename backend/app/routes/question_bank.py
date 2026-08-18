from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Project, QuestionBankItem
from app.schemas.models import (
    QuestionBankConfirmResponse,
    QuestionBankItemResponse,
    QuestionBankItemUpdate,
    QuestionBankListResponse,
)
from app.services.question_bank_extractor import find_stated_total

router = APIRouter(prefix="/projects", tags=["question-bank"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.get("/{project_id}/question-bank", response_model=QuestionBankListResponse)
def list_question_bank(project_id: str, db: Session = Depends(get_db)) -> QuestionBankListResponse:
    project = _get_project_or_404(project_id, db)
    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    return QuestionBankListResponse(
        project_id=project_id,
        confirmed=project.question_bank_confirmed,
        items=[QuestionBankItemResponse.model_validate(i) for i in items],
    )


@router.post("/{project_id}/question-bank", response_model=QuestionBankItemResponse, status_code=201)
def add_question_bank_item(
    project_id: str, question_number: str, marks_possible: int | None = None, key_points: str | None = None,
    db: Session = Depends(get_db),
) -> QuestionBankItemResponse:
    """Manual entry, needed for Edge Case D (scanned rubric with no text layer — auto
    extraction returns zero rows, examiner must be able to add questions by hand).
    Not in the original Phase 2 route table; added because that table only specifies
    PATCH (update existing), which has nothing to update when extraction found nothing.
    """
    project = _get_project_or_404(project_id, db)
    if project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank is already confirmed and locked.")
    if not question_number.strip():
        raise HTTPException(status_code=400, detail="question_number is required.")

    item = QuestionBankItem(
        id=str(uuid.uuid4()),
        project_id=project_id,
        question_number=question_number.strip(),
        marks_possible=marks_possible,
        key_points=key_points,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return QuestionBankItemResponse.model_validate(item)


@router.patch("/{project_id}/question-bank/{question_number}", response_model=QuestionBankItemResponse)
def update_question_bank_item(
    project_id: str, question_number: str, payload: QuestionBankItemUpdate, db: Session = Depends(get_db)
) -> QuestionBankItemResponse:
    project = _get_project_or_404(project_id, db)
    if project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank is already confirmed and locked.")

    item = (
        db.query(QuestionBankItem)
        .filter(QuestionBankItem.project_id == project_id, QuestionBankItem.question_number == question_number)
        .one_or_none()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Question bank item not found.")

    if payload.marks_possible is not None:
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
    item = (
        db.query(QuestionBankItem)
        .filter(QuestionBankItem.project_id == project_id, QuestionBankItem.question_number == question_number)
        .one_or_none()
    )
    if item:
        db.delete(item)
        db.commit()


@router.post("/{project_id}/question-bank/confirm", response_model=QuestionBankConfirmResponse)
def confirm_question_bank(project_id: str, db: Session = Depends(get_db)) -> QuestionBankConfirmResponse:
    """Locks the question bank and runs Edge Case H's marks cross-check: sum every
    extracted marks_possible and compare against the paper's own stated total (if one
    can be detected in either the rubric or the question paper), surfacing a mismatch
    right here — before any grading call is made.
    """
    project = _get_project_or_404(project_id, db)
    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    if not items:
        raise HTTPException(status_code=400, detail="Cannot confirm an empty question bank.")

    total_extracted = sum(item.marks_possible or 0 for item in items)

    stated_total = find_stated_total(project.question_paper_file_path)
    if stated_total is None:
        stated_total = find_stated_total(project.rubric_file_path)

    warning = None
    if stated_total is not None and stated_total != total_extracted:
        warning = (
            f"Extracted questions sum to {total_extracted} marks, but the paper states "
            f"a total of {stated_total} marks. Please review the question bank for a "
            f"missed or misread question before grading."
        )

    project.question_bank_confirmed = True
    project.question_bank_marks_warning = warning
    db.commit()

    return QuestionBankConfirmResponse(
        project_id=project_id,
        confirmed=True,
        total_marks_extracted=total_extracted,
        total_marks_on_paper=stated_total,
        marks_mismatch_warning=warning,
    )


@router.post("/{project_id}/question-bank/unlock")
def unlock_question_bank(project_id: str, db: Session = Depends(get_db)) -> QuestionBankListResponse:
    """Unlock the question bank for re-editing.

    Blocked if any GradingResult or QuestionGroup rows already reference this project's
    questions — clearing the question bank in that state would leave grading results
    pointing at question numbers that no longer exist. The examiner must clear grading
    results (delete answer sheets) and question groups first.

    If no dependents exist, unlocking is always safe.
    """
    from app.db.models import GradingResult, QuestionGroup, AnswerSheet  # noqa: PLC0415

    project = _get_project_or_404(project_id, db)
    if not project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank is not currently confirmed.")

    # Check for grading results that reference this project's questions.
    grading_count = (
        db.query(GradingResult)
        .join(AnswerSheet, GradingResult.answer_sheet_id == AnswerSheet.id)
        .filter(AnswerSheet.project_id == project_id)
        .count()
    )
    group_count = (
        db.query(QuestionGroup)
        .filter(QuestionGroup.project_id == project_id)
        .count()
    )

    blockers = []
    if grading_count > 0:
        blockers.append(f"{grading_count} grading result(s)")
    if group_count > 0:
        blockers.append(f"{group_count} question group(s)")

    if blockers:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot unlock: {' and '.join(blockers)} already reference this question bank. "
                "Delete them first (remove answer sheets and question groups) before re-editing."
            ),
        )

    project.question_bank_confirmed = False
    project.question_bank_marks_warning = None
    db.commit()

    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    return QuestionBankListResponse(
        project_id=project_id,
        confirmed=False,
        items=[QuestionBankItemResponse.model_validate(i) for i in items],
    )
