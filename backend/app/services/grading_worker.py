"""Background grading job worker (Phase 1).

Polls the grading_jobs table for pending jobs and processes them
sequentially using a background asyncio task. No Redis/Celery —
SQLite-backed job state is the deliberate choice for this project's scale.

Lifecycle:
    1. On startup, ``recover_stale_jobs`` marks any in_progress rows as
       failed (crash recovery — the user can retry the sheet).
    2. ``grading_worker_loop`` polls for pending jobs, runs the existing
       synchronous grading pipeline via ``asyncio.to_thread``, and updates
       the job status on completion or failure.
    3. On shutdown, the stop event is set and the worker exits cleanly.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db.database import SessionLocal
from app.db.models import AnswerSheet, GradingJob

logger = logging.getLogger(__name__)

# How often the worker polls for new jobs (seconds).
_POLL_INTERVAL = 0.5


async def recover_stale_jobs() -> None:
    """Mark any in_progress jobs as failed after a server restart.

    Called once during lifespan startup. This is the crash-recovery
    mechanism described in PhasePlan.md Phase 1: any job that was being
    processed when the server died is reset so the user can retry.
    """
    db = SessionLocal()
    try:
        stale = db.query(GradingJob).filter(GradingJob.status == "in_progress").all()
        if not stale:
            return
        now = datetime.now(timezone.utc)
        for job in stale:
            job.status = "failed"
            job.finished_at = now
            job.error = "Server restarted while job was in progress. Please retry grading for this sheet."
        db.commit()
        logger.info("Phase 1 crash recovery: marked %d stale job(s) as failed", len(stale))
    except Exception:
        db.rollback()
        logger.exception("Failed to recover stale jobs")
    finally:
        db.close()


async def grading_worker_loop(stop_event: asyncio.Event) -> None:
    """Background coroutine that polls for pending grading jobs.

    Started as an ``asyncio.Task`` during lifespan. Runs until
    ``stop_event`` is set (clean shutdown). Jobs are processed one at a
    time — the grading pipeline is synchronous (CPU + API calls), so
    ``asyncio.to_thread`` keeps the event loop responsive.
    """
    logger.info("Grading worker started")
    while not stop_event.is_set():
        job = _claim_next_job()
        if job is None:
            await asyncio.sleep(_POLL_INTERVAL)
            continue
        await _process_job(job.id, job.answer_sheet_id)
    logger.info("Grading worker stopped")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _claim_next_job() -> GradingJob | None:
    """Atomically claim the oldest pending job, setting it to in_progress."""
    db = SessionLocal()
    try:
        job = (
            db.query(GradingJob)
            .filter(GradingJob.status == "pending")
            .order_by(GradingJob.created_at.asc())
            .first()
        )
        if job is None:
            return None
        job.status = "in_progress"
        job.started_at = datetime.now(timezone.utc)
        db.commit()
        claimed = GradingJob(
            id=job.id,
            answer_sheet_id=job.answer_sheet_id,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
        )
        return claimed
    except Exception:
        db.rollback()
        logger.exception("Failed to claim next grading job")
        return None
    finally:
        db.close()


async def _process_job(job_id: str, answer_sheet_id: str) -> None:
    """Run the grading pipeline for a claimed job.

    Delegates to ``_trigger_grading_inner`` which already handles:
    - Re-fetching the sheet and project
    - Running the first-N filter
    - Making DashScope API calls
    - Writing GradingResult rows
    - Setting sheet.grading_status to complete / review_required / failed

    On success the job status mirrors the sheet's grading_status.
    On failure the job is marked failed and the sheet's status is
    already set by ``_trigger_grading_inner``'s error handling.
    """
    # Import here to avoid circular imports at module level.
    from app.routes.grading import _trigger_grading_inner

    db = SessionLocal()
    try:
        sheet = db.get(AnswerSheet, answer_sheet_id)
        if sheet is None:
            _fail_job(db, job_id, "Answer sheet was deleted before grading could start.")
            return

        # Run the synchronous grading pipeline in a thread so the event
        # loop stays responsive for health checks and polling requests.
        await asyncio.to_thread(_trigger_grading_inner, sheet.project_id, answer_sheet_id, db, sheet)

        # Success — mirror the sheet's final grading_status on the job.
        db.refresh(sheet)
        _complete_job(db, job_id, sheet.grading_status)

    except HTTPException as exc:
        db.rollback()
        # Sheet status is already persisted by _trigger_grading_inner's
        # caller-side error handling (or the pre-flight check that raised).
        _fail_job(db, job_id, str(exc.detail))

    except Exception as exc:
        db.rollback()
        error_msg = str(exc) or type(exc).__name__
        _fail_job(db, job_id, f"Unexpected error: {error_msg}")
        # Ensure the sheet is marked failed if the inner function didn't
        # get far enough to do it itself (e.g., connection error early).
        _ensure_sheet_failed(db, answer_sheet_id)

    finally:
        db.close()


def _complete_job(db, job_id: str, sheet_status: str) -> None:
    """Mark a job as complete, deriving the final status from the sheet."""
    try:
        job = db.get(GradingJob, job_id)
        if job:
            # Sheet status is "failed" when any hard failure occurred; the
            # job should reflect that rather than showing "complete".
            job.status = "failed" if sheet_status == "failed" else "complete"
            job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update job %s status", job_id)


def _fail_job(db, job_id: str, error: str) -> None:
    """Mark a job as failed with a human-readable error message."""
    try:
        job = db.get(GradingJob, job_id)
        if job:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.error = error
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update job %s as failed", job_id)


def _ensure_sheet_failed(db, answer_sheet_id: str) -> None:
    """Set sheet.grading_status to 'failed' if it's still in_progress.

    Belt-and-suspenders: _trigger_grading_inner's error handling normally
    sets the sheet status, but if the failure happened before that code
    ran (e.g., DB connection error), this prevents the sheet from being
    stuck in 'in_progress' forever.
    """
    try:
        sheet = db.get(AnswerSheet, answer_sheet_id)
        if sheet and sheet.grading_status == "in_progress":
            sheet.grading_status = "failed"
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to set sheet %s to failed", answer_sheet_id)
