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

    if "answer_sheets" in tables:
        sheet_cols = {col["name"] for col in inspector.get_columns("answer_sheets")}
        with engine.begin() as conn:
            if "grading_status" not in sheet_cols:
                conn.execute(text("ALTER TABLE answer_sheets ADD COLUMN grading_status VARCHAR(32) NOT NULL DEFAULT 'not_graded'"))

