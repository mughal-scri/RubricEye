import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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
    rubric_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    question_paper_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    blank_booklet_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    template_map_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rubric_locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    template_map_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    alignment_reference_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    template_map_pages: Mapped[list["TemplateMapPage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    answer_sheets: Mapped[list["AnswerSheet"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    question_bank_items: Mapped[list["QuestionBankItem"]] = relationship(
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

    project: Mapped["Project"] = relationship(back_populates="answer_sheets")


class QuestionBankItem(Base):
    __tablename__ = "question_bank_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    question_number: Mapped[str] = mapped_column(String(64), nullable=False)
    marks_possible: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="question_bank_items")
