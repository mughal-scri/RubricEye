from sqlalchemy import inspect, text
from app.db.database import Base, engine
from app.db import models  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    # Auto-migrate missing columns on existing SQLite database files
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "projects" in tables:
        project_cols = {col["name"] for col in inspector.get_columns("projects")}
        with engine.begin() as conn:
            if "question_bank_confirmed" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN question_bank_confirmed BOOLEAN NOT NULL DEFAULT 0"))
            if "question_bank_marks_warning" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN question_bank_marks_warning TEXT"))
            if "deleted_at" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN deleted_at DATETIME"))
            if "template_map_error" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN template_map_error TEXT"))
            if "question_bank_raw_total" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN question_bank_raw_total INTEGER"))
            if "question_bank_stated_total" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN question_bank_stated_total INTEGER"))
            if "question_bank_effective_total" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN question_bank_effective_total INTEGER"))
            if "question_bank_structure_status" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN question_bank_structure_status VARCHAR(40) NOT NULL DEFAULT 'unresolved'"))
            if "rubric_source_mode" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN rubric_source_mode VARCHAR(16) NOT NULL DEFAULT 'uploaded'"))
            if "rubric_studio_status" not in project_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN rubric_studio_status VARCHAR(24) NOT NULL DEFAULT 'not_used'"))

    if "question_bank_items" in tables:
        question_cols = {col["name"] for col in inspector.get_columns("question_bank_items")}
        with engine.begin() as conn:
            if "rubric_provenance" not in question_cols:
                conn.execute(text("ALTER TABLE question_bank_items ADD COLUMN rubric_provenance VARCHAR(255)"))
            if "rubric_confidence" not in question_cols:
                conn.execute(text("ALTER TABLE question_bank_items ADD COLUMN rubric_confidence VARCHAR(16)"))
            if "rubric_reviewed" not in question_cols:
                conn.execute(text("ALTER TABLE question_bank_items ADD COLUMN rubric_reviewed BOOLEAN NOT NULL DEFAULT 0"))
            if "section_label" not in question_cols:
                conn.execute(text("ALTER TABLE question_bank_items ADD COLUMN section_label VARCHAR(255)"))
            if "question_text" not in question_cols:
                conn.execute(text("ALTER TABLE question_bank_items ADD COLUMN question_text TEXT"))
            if "alignment_question_number" not in question_cols:
                conn.execute(text("ALTER TABLE question_bank_items ADD COLUMN alignment_question_number VARCHAR(64)"))
            if "alignment_status" not in question_cols:
                conn.execute(text("ALTER TABLE question_bank_items ADD COLUMN alignment_status VARCHAR(24) NOT NULL DEFAULT 'unreviewed'"))

    if "question_groups" in tables:
        group_cols = {col["name"] for col in inspector.get_columns("question_groups")}
        with engine.begin() as conn:
            if "selection_units_json" not in group_cols:
                conn.execute(text("ALTER TABLE question_groups ADD COLUMN selection_units_json TEXT NOT NULL DEFAULT '[]'"))
            if "suggestion_confidence" not in group_cols:
                conn.execute(text("ALTER TABLE question_groups ADD COLUMN suggestion_confidence VARCHAR(16)"))
            if "suggestion_evidence" not in group_cols:
                conn.execute(text("ALTER TABLE question_groups ADD COLUMN suggestion_evidence TEXT"))
            if "suggestion_status" not in group_cols:
                conn.execute(text("ALTER TABLE question_groups ADD COLUMN suggestion_status VARCHAR(16) NOT NULL DEFAULT 'confirmed'"))

    if "answer_sheets" in tables:
        sheet_cols = {col["name"] for col in inspector.get_columns("answer_sheets")}
        with engine.begin() as conn:
            if "grading_status" not in sheet_cols:
                conn.execute(text("ALTER TABLE answer_sheets ADD COLUMN grading_status VARCHAR(32) NOT NULL DEFAULT 'not_graded'"))
            if "report_path" not in sheet_cols:
                conn.execute(text("ALTER TABLE answer_sheets ADD COLUMN report_path VARCHAR(1024)"))
            if "report_generated_at" not in sheet_cols:
                conn.execute(text("ALTER TABLE answer_sheets ADD COLUMN report_generated_at DATETIME"))
            if "completed_at" not in sheet_cols:
                conn.execute(text("ALTER TABLE answer_sheets ADD COLUMN completed_at DATETIME"))
            if "deleted_at" not in sheet_cols:
                conn.execute(text("ALTER TABLE answer_sheets ADD COLUMN deleted_at DATETIME"))

