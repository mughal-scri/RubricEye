from __future__ import annotations

import os
from pathlib import Path

FIXTURES_DIR = Path(os.environ.get("RUBRICEYE_REAL_FIXTURES_DIR", "fixtures/real"))


def fixture_path(name: str, env_name: str | None = None) -> Path:
    value = os.environ.get(env_name) if env_name else None
    path = Path(value) if value else FIXTURES_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing real fixture: {path}. Set RUBRICEYE_REAL_FIXTURES_DIR or {env_name or 'the relevant fixture variable'}."
        )
    return path


def answer_books() -> list[Path]:
    configured = os.environ.get("RUBRICEYE_REAL_ANSWER_BOOKS")
    if configured:
        paths = [Path(item.strip()) for item in configured.split(",") if item.strip()]
    else:
        paths = sorted(FIXTURES_DIR.glob("Testanswerbook1-*.pdf"))
    if not paths:
        raise FileNotFoundError(
            "No real answer books found. Set RUBRICEYE_REAL_ANSWER_BOOKS to a comma-separated list "
            "or place Testanswerbook1-*.pdf under RUBRICEYE_REAL_FIXTURES_DIR."
        )
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing configured real answer books: {', '.join(missing)}")
    return paths


BLANK = fixture_path("RubricEye_AnswerBooklet.pdf", "RUBRICEYE_REAL_BLANK_BOOKLET")
QUESTION_PAPER = fixture_path("RubricEyeMockExamQuestionPaper.pdf", "RUBRICEYE_REAL_QUESTION_PAPER")
RUBRIC = fixture_path("RubricEye_MockExam_Rubric.pdf", "RUBRICEYE_REAL_RUBRIC")
