from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AnswerSheet, GradingResult, Project, QuestionBankItem, QuestionGroup
from app.schemas.models import (
    AnswerSheetResultsResponse,
    AnswerSheetResultsSummary,
    ExaminerConfirmRequest,
    GradeTriggerResponse,
    GradingResultResponse,
    GradingResultSummary,
    PartScore,
    SectionSummary,
)
from app.services import first_n_filter, grading, storage
from app.services.question_grouping import resolve_region_keys_for_question
from app.services.segmentation import safe_region_filename_key

router = APIRouter(prefix="/projects", tags=["grading"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _get_sheet_or_404(project_id: str, answer_sheet_id: str, db: Session) -> AnswerSheet:
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")
    return sheet


def _question_groups_as_dicts(project_id: str, db: Session) -> list[dict]:
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id, QuestionGroup.suggestion_status == "confirmed").all()
    return [
        {
            "id": g.id,
            "group_name": g.group_name,
            "selection_type": g.selection_type,
            "question_numbers": json.loads(g.question_numbers_json or "[]"),
            "selection_units": json.loads(g.selection_units_json or "[]") or [[question] for question in json.loads(g.question_numbers_json or "[]")],
            "n_required": g.n_required,
        }
        for g in groups
    ]


def _region_preview_urls(project_id: str, sheet_id: str, question_number: str, region_map_keys: list[str]) -> list[str]:
    regions_dir = storage.answer_sheet_dir(project_id, sheet_id) / "regions"
    keys = resolve_region_keys_for_question(question_number, region_map_keys)
    urls: list[str] = []
    if not regions_dir.exists():
        return urls
    for key in keys:
        for path in sorted(regions_dir.glob(f"{safe_region_filename_key(key)}_p*.png")):
            urls.append(f"/files/projects/{project_id}/answer_sheets/{sheet_id}/regions/{path.name}")
    return urls


def _result_to_response(result: GradingResult, project_id: str, region_map_keys: list[str]) -> GradingResultResponse:
    return GradingResultResponse(
        id=result.id,
        answer_sheet_id=result.answer_sheet_id,
        question_number=result.question_number,
        ai_score=result.ai_score,
        ai_total_possible=result.ai_total_possible,
        ai_rationale=result.ai_rationale,
        part_scores=[PartScore(**p) for p in json.loads(result.part_scores_json or "[]")],
        transcription_summary=result.transcription_summary,
        flags=json.loads(result.flags_json or "[]"),
        confidence=result.confidence,
        truncation_flag=result.truncation_flag,
        ink_status=result.ink_status,
        ink_density_ratio=result.ink_density_ratio,
        choice_status=result.choice_status,
        human_confirmed_score=result.human_confirmed_score,
        human_reviewer_note=result.human_reviewer_note,
        reviewed=result.reviewed,
        grading_status=result.grading_status,
        error_message=result.error_message,
        graded_at=result.graded_at,
        region_preview_urls=_region_preview_urls(project_id, result.answer_sheet_id, result.question_number, region_map_keys),
    )


def _upsert_result(db: Session, sheet_id: str, question_number: str, **fields) -> GradingResult:
    """Edge Case C: upsert keyed on (answer_sheet_id, question_number), never a blind insert."""
    existing = (
        db.query(GradingResult)
        .filter(GradingResult.answer_sheet_id == sheet_id, GradingResult.question_number == question_number)
        .one_or_none()
    )
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    result = GradingResult(answer_sheet_id=sheet_id, question_number=question_number, **fields)
    db.add(result)
    return result


def _build_summary(db: Session, project_id: str, sheet_id: str) -> AnswerSheetResultsSummary:
    """Edge Case G: computed on read from GradingResult + QuestionGroup, never persisted."""
    results = db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet_id).all()
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id, QuestionGroup.suggestion_status == "confirmed").all()

    group_listed: dict[str, set[str]] = {}
    for g in groups:
        group_listed[g.group_name] = set(json.loads(g.question_numbers_json or "[]"))

    sections: dict[str, list[GradingResult]] = {name: [] for name in group_listed}
    sections["Ungrouped"] = []

    for result in results:
        placed = False
        for name, listed in group_listed.items():
            if result.question_number in listed:
                sections[name].append(result)
                placed = True
                break
        if not placed:
            sections["Ungrouped"].append(result)

    section_summaries: list[SectionSummary] = []
    grand_awarded = 0
    grand_possible = 0
    for name, rows in sections.items():
        if not rows:
            continue
        questions = [
            GradingResultSummary(
                question_number=r.question_number,
                ai_score=r.human_confirmed_score if r.reviewed else r.ai_score,
                ai_total_possible=r.ai_total_possible,
                confidence=r.confidence,
                choice_status=r.choice_status,
                reviewed=r.reviewed,
                grading_status=r.grading_status,
            )
            for r in rows
        ]
        section_awarded = sum(q.ai_score or 0 for q in questions)
        section_possible = sum(
            q.ai_total_possible or 0
            for q in questions
            if q.choice_status not in ("skipped_beyond_n", "skipped_blank")
        )
        section_summaries.append(
            SectionSummary(
                section_name=name,
                questions=questions,
                section_total_awarded=section_awarded,
                section_total_possible=section_possible,
            )
        )
        grand_awarded += section_awarded
        grand_possible += section_possible

    return AnswerSheetResultsSummary(
        answer_sheet_id=sheet_id,
        sections=section_summaries,
        grand_total_awarded=grand_awarded,
        grand_total_possible=grand_possible,
    )


@router.post("/{project_id}/answer-sheets/{answer_sheet_id}/grade", response_model=GradeTriggerResponse)
def trigger_grading(project_id: str, answer_sheet_id: str, db: Session = Depends(get_db)) -> GradeTriggerResponse:
    project = _get_project_or_404(project_id, db)
    sheet = _get_sheet_or_404(project_id, answer_sheet_id, db)

    if not project.question_bank_confirmed:
        raise HTTPException(status_code=409, detail="Question bank must be confirmed before grading.")

    # Validate correspondence before changing durable state. An uncertainty response
    # must leave the sheet retryable rather than marooning it in in_progress.
    question_region_map = json.loads(sheet.question_region_map_json or "{}")
    uncertain_regions = [
        key
        for key, refs in question_region_map.items()
        if any(bool(ref.get("alignment_uncertain", False) or ref.get("page_correspondence_uncertain", False)) for ref in refs)
    ]
    if uncertain_regions:
        raise HTTPException(
            status_code=409,
            detail=(
                "Grading is blocked because page alignment is uncertain for "
                f"{', '.join(uncertain_regions[:8])}. Review the booklet correspondence or re-upload the sheet."
            ),
        )

    # Edge Case C (idempotency): an already-processed sheet is never re-processed
    # merely because examiner review is still outstanding.
    if sheet.grading_status in ("complete", "review_required"):
        existing = db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet.id).all()
        return GradeTriggerResponse(
            answer_sheet_id=sheet.id,
            grading_status=sheet.grading_status,
            graded=[r.question_number for r in existing if r.choice_status == "graded"],
            skipped_blank=[r.question_number for r in existing if r.choice_status == "skipped_blank"],
            skipped_beyond_n=[r.question_number for r in existing if r.choice_status == "skipped_beyond_n"],
            flagged_ambiguous=[r.question_number for r in existing if r.choice_status == "flagged_ambiguous"],
            failed=[r.question_number for r in existing if r.grading_status == "failed"],
        )
    if sheet.grading_status == "in_progress":
        raise HTTPException(status_code=409, detail="Grading is already in progress for this sheet.")

    sheet.grading_status = "in_progress"
    db.commit()

    try:
        return _trigger_grading_inner(project_id, answer_sheet_id, db, sheet)
    except HTTPException:
        db.rollback()
        failed_sheet = db.get(AnswerSheet, sheet.id)
        if failed_sheet and failed_sheet.grading_status == "in_progress":
            failed_sheet.grading_status = "failed"
            db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 — preserve retryability after unexpected processing failures
        db.rollback()
        failed_sheet = db.get(AnswerSheet, sheet.id)
        if failed_sheet:
            failed_sheet.grading_status = "failed"
            db.commit()
        raise HTTPException(status_code=500, detail="Grading failed unexpectedly; retry the answer sheet after reviewing the saved error logs.") from exc


def _trigger_grading_inner(project_id: str, answer_sheet_id: str, db: Session, sheet: AnswerSheet) -> GradeTriggerResponse:
    qb_items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    qb_items_by_number = {item.question_number: item for item in qb_items}
    question_groups = _question_groups_as_dicts(project_id, db)

    # Skip any question_number that already has a COMPLETE row (retry resumes, per Edge Case C).
    already_complete = {
        r.question_number
        for r in db.query(GradingResult)
        .filter(GradingResult.answer_sheet_id == sheet.id, GradingResult.grading_status == "complete")
        .all()
    }
    pending_numbers = [qn for qn in qb_items_by_number if qn not in already_complete]

    question_region_map = json.loads(sheet.question_region_map_json or "{}")
    regions_dir = storage.answer_sheet_dir(project_id, sheet.id) / "regions"

    filtered = first_n_filter.apply_first_n_filter(
        question_region_map, regions_dir, pending_numbers, question_groups
    )

    now = datetime.now(timezone.utc)

    for qn in filtered.skipped_blank:
        _upsert_result(
            db, sheet.id, qn,
            ai_score=None, ai_total_possible=qb_items_by_number[qn].marks_possible,
            ai_rationale=None, part_scores_json="[]", transcription_summary=None,
            flags_json="[]", confidence="low", ink_status="blank", ink_density_ratio=0.0,
            choice_status="skipped_blank", grading_status="complete", graded_at=now,
        )
    for qn in filtered.skipped_beyond_n:
        _upsert_result(
            db, sheet.id, qn,
            ai_score=None, ai_total_possible=qb_items_by_number[qn].marks_possible,
            ai_rationale=None, part_scores_json="[]", transcription_summary=None,
            flags_json=json.dumps(["skipped: beyond the allowed number of choices"]),
            confidence="low", ink_status="attempted", choice_status="skipped_beyond_n",
            grading_status="complete", graded_at=now,
        )
    for qn in filtered.flagged_ambiguous:
        _upsert_result(
            db, sheet.id, qn,
            ai_score=None, ai_total_possible=qb_items_by_number[qn].marks_possible,
            ai_rationale=None, part_scores_json="[]", transcription_summary=None,
            flags_json=json.dumps(["ambiguous ink density — needs human review before grading"]),
            confidence="low", ink_status="ambiguous", choice_status="flagged_ambiguous",
            grading_status="complete", graded_at=now,
        )
    for qn in filtered.no_regions:
        _upsert_result(
            db, sheet.id, qn,
            ai_score=None, ai_total_possible=qb_items_by_number[qn].marks_possible,
            ai_rationale=None, part_scores_json="[]", transcription_summary=None,
            flags_json=json.dumps(["no matching region found — check template map / question bank alignment"]),
            confidence="low", ink_status="blank", choice_status="no_regions",
            grading_status="failed", error_message="no matching region for this question_number",
            graded_at=now,
        )

    graded_results = grading.grade_units(filtered.to_grade, qb_items_by_number, question_groups)
    for graded in graded_results:
        _upsert_result(
            db, sheet.id, graded.question_number,
            ai_score=graded.ai_score, ai_total_possible=graded.ai_total_possible,
            ai_rationale=graded.ai_rationale, part_scores_json=json.dumps(graded.part_scores),
            transcription_summary=graded.transcription_summary, flags_json=json.dumps(graded.flags),
            confidence=graded.confidence,
            ink_status="attempted",
            choice_status="graded" if graded.grading_status == "complete" else "graded",
            grading_status=graded.grading_status, error_message=graded.error_message, graded_at=now,
        )

    overflow_by_key = {
        key: any(bool(ref.get("overflow_detected", False)) for ref in refs)
        for key, refs in question_region_map.items()
    }
    for stored_result in db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet.id).all():
        region_keys = resolve_region_keys_for_question(stored_result.question_number, list(question_region_map.keys()))
        stored_result.truncation_flag = any(overflow_by_key.get(key, False) for key in region_keys)
    db.commit()

    any_hard_failure = any(r.grading_status == "failed" for r in graded_results) or bool(filtered.no_regions)
    # Blank and beyond-limit choices are closed automatically. A genuine ambiguous
    # ink state remains a human decision, just like an AI-scored answer.
    requires_review = any(r.grading_status == "complete" for r in graded_results) or bool(filtered.flagged_ambiguous)
    sheet.grading_status = "failed" if any_hard_failure else ("review_required" if requires_review else "complete")
    db.commit()

    return GradeTriggerResponse(
        answer_sheet_id=sheet.id,
        grading_status=sheet.grading_status,
        graded=[g.question_number for g in graded_results if g.grading_status == "complete"],
        skipped_blank=filtered.skipped_blank,
        skipped_beyond_n=filtered.skipped_beyond_n,
        flagged_ambiguous=filtered.flagged_ambiguous,
        failed=[g.question_number for g in graded_results if g.grading_status == "failed"] + filtered.no_regions,
    )


@router.get("/{project_id}/answer-sheets/{answer_sheet_id}/results", response_model=AnswerSheetResultsResponse)
def list_results(project_id: str, answer_sheet_id: str, db: Session = Depends(get_db)) -> AnswerSheetResultsResponse:
    _get_project_or_404(project_id, db)
    sheet = _get_sheet_or_404(project_id, answer_sheet_id, db)
    region_map_keys = list(json.loads(sheet.question_region_map_json or "{}").keys())

    results = db.query(GradingResult).filter(GradingResult.answer_sheet_id == sheet.id).all()
    return AnswerSheetResultsResponse(
        answer_sheet_id=sheet.id,
        grading_status=sheet.grading_status,
        results=[_result_to_response(r, project_id, region_map_keys) for r in results],
        summary=_build_summary(db, project_id, sheet.id),
        report_ready=bool(sheet.report_path),
        report_download_url=(f"/files/projects/{project_id}/answer_sheets/{sheet.id}/examiner_report.pdf" if sheet.report_path else None),
        completed_at=sheet.completed_at,
    )


@router.get(
    "/{project_id}/answer-sheets/{answer_sheet_id}/results/{question_number}",
    response_model=GradingResultResponse,
)
def get_result(
    project_id: str, answer_sheet_id: str, question_number: str, db: Session = Depends(get_db)
) -> GradingResultResponse:
    _get_project_or_404(project_id, db)
    sheet = _get_sheet_or_404(project_id, answer_sheet_id, db)
    result = (
        db.query(GradingResult)
        .filter(GradingResult.answer_sheet_id == sheet.id, GradingResult.question_number == question_number)
        .one_or_none()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Grading result not found for this question.")
    region_map_keys = list(json.loads(sheet.question_region_map_json or "{}").keys())
    return _result_to_response(result, project_id, region_map_keys)


@router.post(
    "/{project_id}/answer-sheets/{answer_sheet_id}/results/{question_number}/confirm",
    response_model=GradingResultResponse,
)
def confirm_result(
    project_id: str,
    answer_sheet_id: str,
    question_number: str,
    payload: ExaminerConfirmRequest,
    db: Session = Depends(get_db),
) -> GradingResultResponse:
    _get_project_or_404(project_id, db)
    sheet = _get_sheet_or_404(project_id, answer_sheet_id, db)
    result = (
        db.query(GradingResult)
        .filter(GradingResult.answer_sheet_id == sheet.id, GradingResult.question_number == question_number)
        .one_or_none()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Grading result not found for this question.")

    max_score = result.ai_total_possible
    if max_score is None:
        question = (
            db.query(QuestionBankItem)
            .filter(
                QuestionBankItem.project_id == project_id,
                QuestionBankItem.question_number == question_number,
            )
            .one_or_none()
        )
        max_score = question.marks_possible if question else None
    if max_score is None:
        raise HTTPException(status_code=409, detail="Marks limit is unavailable for this question; cannot confirm a bounded score.")
    if payload.human_confirmed_score < 0 or payload.human_confirmed_score > max_score:
        raise HTTPException(status_code=422, detail=f"Confirmed score must be between 0 and {max_score} marks.")

    result.human_confirmed_score = payload.human_confirmed_score
    result.human_reviewer_note = payload.human_reviewer_note
    result.reviewed = True

    remaining = (
        db.query(GradingResult)
        .filter(
            GradingResult.answer_sheet_id == sheet.id,
            GradingResult.id != result.id,
            GradingResult.reviewed.is_(False),
            GradingResult.choice_status.in_(["graded", "flagged_ambiguous"]),
            GradingResult.grading_status != "failed",
        )
        .count()
    )
    if remaining == 0 and sheet.grading_status == "review_required":
        sheet.grading_status = "complete"
    db.commit()

    region_map_keys = list(json.loads(sheet.question_region_map_json or "{}").keys())
    return _result_to_response(result, project_id, region_map_keys)
