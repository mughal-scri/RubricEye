import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rubric_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    question_paper_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    blank_booklet_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    template_map_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rubric_locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    template_map_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    template_map_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    alignment_reference_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Preparation and grading additions ---
    # Not explicitly in the Phase 2 plan's schema table, but required by the plan's own UI spec:
    # ProjectDetail.tsx needs a "Grade" button "disabled until question bank is set up", which
    # requires a durable lock flag (mirrors template_map_confirmed's pattern exactly).
    question_bank_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Cached warning from Edge Case H (marks cross-check against paper's stated total),
    # populated when question bank is confirmed. Null if no mismatch or no total was detected.
    question_bank_marks_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_bank_raw_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_bank_stated_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_bank_effective_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_bank_structure_status: Mapped[str] = mapped_column(String(40), default="unresolved", nullable=False)
    rubric_source_mode: Mapped[str] = mapped_column(String(16), default="uploaded", nullable=False)
    rubric_studio_status: Mapped[str] = mapped_column(String(24), default="not_used", nullable=False)

    template_map_pages: Mapped[list["TemplateMapPage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    answer_sheets: Mapped[list["AnswerSheet"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    question_bank_items: Mapped[list["QuestionBankItem"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    question_groups: Mapped[list["QuestionGroup"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class TemplateMapPage(Base):
    __tablename__ = "template_map_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    regions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    project: Mapped["Project"] = relationship(back_populates="template_map_pages")


class AnswerSheet(Base):
    __tablename__ = "answer_sheets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    roll_number: Mapped[str] = mapped_column(String(128), nullable=False)
    original_pdf_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    page_image_paths_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    question_region_map_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Phase 2 addition ---
    # Sheet-level grading status, independent of individual GradingResult.grading_status rows.
    # Edge Case C (idempotency): lets a retry short-circuit instantly if the whole sheet is
    # already "complete" without touching per-question rows at all.
    # One of: not_graded | in_progress | review_required | complete | failed
    grading_status: Mapped[str] = mapped_column(String(32), default="not_graded", nullable=False)
    report_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    report_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="answer_sheets")
    grading_results: Mapped[list["GradingResult"]] = relationship(
        back_populates="answer_sheet", cascade="all, delete-orphan"
    )


class QuestionBankItem(Base):
    __tablename__ = "question_bank_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    question_number: Mapped[str] = mapped_column(String(64), nullable=False)
    marks_possible: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    rubric_provenance: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rubric_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rubric_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alignment_question_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alignment_status: Mapped[str] = mapped_column(String(24), default="unreviewed", nullable=False)

    project: Mapped["Project"] = relationship(back_populates="question_bank_items")


class QuestionGroup(Base):
    """Defines compulsory vs. choose-N-of-M question groups (TechDoc §2.4).

    `question_numbers` uses the SAME granularity the examiner used when confirming
    QuestionBankItem rows (e.g. "3a"/"3b" if parts were split out, or "3" if not).
    See services/question_grouping.py for how this is resolved against segmentation
    region-map keys, which are always part-level.
    """

    __tablename__ = "question_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    group_name: Mapped[str] = mapped_column(String(255), nullable=False)
    selection_type: Mapped[str] = mapped_column(String(32), nullable=False)  # compulsory | choose_n_of_m
    question_numbers_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    selection_units_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    n_required: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggestion_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    suggestion_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion_status: Mapped[str] = mapped_column(String(16), default="confirmed", nullable=False)

    project: Mapped["Project"] = relationship(back_populates="question_groups")


class GradingResult(Base):
    """One row per gradable question unit per answer sheet.

    `question_number` matches QuestionBankItem.question_number for the same project
    (i.e. it may be a bare question number like "2" or a part-level key like "3a",
    whatever granularity the examiner confirmed in Question Bank Setup).
    """

    __tablename__ = "grading_results"
    __table_args__ = (
        # Edge Case C (idempotency): GradingResult writes must be upserts keyed on
        # (answer_sheet_id, question_number), never blind inserts. This constraint is
        # what makes that enforceable at the DB level, not just by convention in code.
        UniqueConstraint("answer_sheet_id", "question_number", name="uq_grading_result_sheet_question"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    answer_sheet_id: Mapped[str] = mapped_column(String(36), ForeignKey("answer_sheets.id"), nullable=False)
    question_number: Mapped[str] = mapped_column(String(64), nullable=False)

    ai_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_total_possible: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)  # human-readable summary
    part_scores_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    transcription_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default="low", nullable=False)  # high|medium|low

    # Edge Case A tie-in: carried through from segmentation if present, defaults False
    # for Phase 1 sheets that predate the truncation-flag addition.
    truncation_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Ink-density pre-filter classification (services/ink_density.py)
    ink_status: Mapped[str] = mapped_column(String(16), default="attempted", nullable=False)
    ink_density_ratio: Mapped[float | None] = mapped_column(nullable=True)

    # First-N choice-question bookkeeping (services/first_n_filter.py)
    choice_status: Mapped[str] = mapped_column(String(24), default="graded", nullable=False)
    # graded | skipped_blank | skipped_beyond_n | flagged_ambiguous | no_regions

    human_confirmed_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    human_reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Edge Case C (idempotency): pending | in_progress | review_required | complete | failed
    grading_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    answer_sheet: Mapped["AnswerSheet"] = relationship(back_populates="grading_results")
