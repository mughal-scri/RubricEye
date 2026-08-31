from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AnswerSheet, GradingJob, GradingResult, Project, QuestionBankItem, QuestionGroup
from app.schemas.models import (
    AnswerSheetResultsResponse,
    AnswerSheetResultsSummary,
    ExaminerConfirmRequest,
    GradeEnqueueResponse,
    GradeTriggerResponse,
    GradingResultResponse,
    GradingResultSummary,
    JobStatusResponse,
    PartScore,
    ProjectReviewQueueResponse,
    ReviewQueueItem,
    ReviewQueueSheet,
    SectionSummary,
)
from app.services import first_n_filter, grading, storage
from app.services.paper_structure import infer_group_suggestions
from app.services.question_grouping import resolve_region_keys_for_question
from app.services.reporting import compute_totals
from app.services.segmentation import safe_region_filename_key

router = APIRouter(prefix="/projects", tags=["grading"])


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _get_sheet_or_404(project_id: str, answer_sheet_id: str, db: Session) -> AnswerSheet:
    sheet = db.get(AnswerSheet, answer_sheet_id)
    if not sheet or sheet.project_id != project_id or sheet.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Answer sheet not found.")
    return sheet


def _question_groups_as_dicts(project_id: str, db: Session) -> list[dict]:
    # Provisional groups are still document-derived grading rules. Their status
    # controls examiner review in Question Group Setup, not whether first-N
    # selection is silently bypassed.
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).all()
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


def _ensure_grading_groups(project: Project, db: Session) -> None:
    """Restore document-derived choice groups if a resolved structure lost them."""
    if db.query(QuestionGroup).filter(QuestionGroup.project_id == project.id).count() > 0:
        return
    if project.question_bank_raw_total is None or project.question_bank_effective_total is None:
        return
    if project.question_bank_effective_total >= project.question_bank_raw_total:
        return
    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project.id).all()
    suggestions = infer_group_suggestions(
        project.question_paper_file_path,
        [{"question_number": item.question_number, "marks_possible": item.marks_possible} for item in items],
    )
    for suggestion in suggestions:
        flat = [question for unit in suggestion.selection_units for question in unit]
        if not flat:
            continue
        db.add(QuestionGroup(
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
        ))
    db.flush()


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


def _compute_review_state(result: GradingResult) -> str:
    """Compute a human-readable review state label from the result's fields.

    States:
        ai_draft   — not reviewed, choice_status=graded, has ai_score
        confirmed  — reviewed, human score matches AI (or AI was null)
        overridden — reviewed, human score differs from AI
        ambiguous  — choice_status=flagged_ambiguous, not yet reviewed
        closed     — choice_status in (skipped_blank, skipped_beyond_n)
        failed     — grading_status=failed
    """
    if result.grading_status == "failed":
        return "failed"
    if result.choice_status in ("skipped_blank", "skipped_beyond_n"):
        return "closed"
    if result.choice_status == "flagged_ambiguous" and not result.reviewed:
        return "ambiguous"
    if result.reviewed:
        if result.ai_score is not None and result.human_confirmed_score != result.ai_score:
            return "overridden"
        return "confirmed"
    return "ai_draft"


def _result_to_response(
    result: GradingResult,
    project_id: str,
    region_map_keys: list[str],
    question_bank: dict[str, QuestionBankItem] | None = None,
) -> GradingResultResponse:
    qb = (question_bank or {}).get(result.question_number)
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
        # Phase 3 audit trail
        model_name=result.model_name,
        prompt_version=result.prompt_version,
        raw_response_json=result.raw_response_json,
        request_payload_summary=result.request_payload_summary,
        # Phase 5/6 review state and question context
        question_text=qb.question_text if qb else None,
        key_points=qb.key_points if qb else None,
        review_state=_compute_review_state(result),
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
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project_id).all()

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
        section_awarded, section_possible = compute_totals(rows)
        section_summaries.append(
            SectionSummary(
                section_name=name,
                questions=questions,
                section_total_awarded=section_awarded,
                section_total_possible=section_possible,
            )
        )

    grand_awarded, grand_possible = compute_totals(results)

    return AnswerSheetResultsSummary(
        answer_sheet_id=sheet_id,
        sections=section_summaries,
        grand_total_awarded=grand_awarded,
        grand_total_possible=grand_possible,
    )


@router.post(
    "/{project_id}/answer-sheets/{answer_sheet_id}/grade",
    response_model=GradeEnqueueResponse,
    status_code=202,
)
def trigger_grading(project_id: str, answer_sheet_id: str, db: Session = Depends(get_db)) -> GradeEnqueueResponse:
    """Enqueue a grading job for background processing (Phase 1 async).

    All pre-flight validation runs synchronously so errors are returned
    immediately. The actual grading pipeline (first-N filter, DashScope
    API calls, result writing) runs in the background worker.

    Returns 202 Accepted with a job_id for polling via GET /jobs/{job_id}.
    """
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
        # Return a synthetic enqueue response so the frontend treats it as
        # "already done" and reloads results immediately.
        return GradeEnqueueResponse(
            job_id="already-processed",
            answer_sheet_id=sheet.id,
        )
    if sheet.grading_status == "in_progress":
        raise HTTPException(status_code=409, detail="Grading is already in progress for this sheet.")

    sheet.grading_status = "in_progress"

    # Create the async job before committing the sheet status change.
    job = GradingJob(answer_sheet_id=sheet.id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    return GradeEnqueueResponse(job_id=job.id, answer_sheet_id=sheet.id)


def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    """Top-level endpoint for polling a grading job's status (Phase 1).

    Registered at ``GET /jobs/{job_id}`` in main.py (outside the
    ``/projects`` prefix) so the frontend can poll without knowing the
    project context.
    """
    job = db.get(GradingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatusResponse(
        job_id=job.id,
        answer_sheet_id=job.answer_sheet_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
    )


def _trigger_grading_inner(project_id: str, answer_sheet_id: str, db: Session, sheet: AnswerSheet) -> GradeTriggerResponse:
    project = _get_project_or_404(project_id, db)
    _ensure_grading_groups(project, db)
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
            # Only attempted items reach grade_units — the first-N filter
            # routes ambiguous/blank/no_regions separately.
            choice_status="graded",
            grading_status=graded.grading_status, error_message=graded.error_message, graded_at=now,
            # Phase 3 audit trail
            model_name=graded.model_name, prompt_version=graded.prompt_version,
            raw_response_json=graded.raw_response_json,
            request_payload_summary=graded.request_payload_summary,
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
    question_bank = {
        item.question_number: item
        for item in db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    }
    return AnswerSheetResultsResponse(
        answer_sheet_id=sheet.id,
        grading_status=sheet.grading_status,
        results=[_result_to_response(r, project_id, region_map_keys, question_bank) for r in results],
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
    question_bank = {
        item.question_number: item
        for item in db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    }
    return _result_to_response(result, project_id, region_map_keys, question_bank)


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
    question_bank = {
        item.question_number: item
        for item in db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project_id).all()
    }
    return _result_to_response(result, project_id, region_map_keys, question_bank)
