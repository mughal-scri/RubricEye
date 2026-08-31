"""Regression tests for _compute_review_state (Phase 5/6 review state label)."""

import pytest

from app.routes.grading import _compute_review_state


class _FakeResult:
    """Minimal stand-in for GradingResult with only the fields _compute_review_state reads."""

    def __init__(
        self,
        *,
        grading_status: str = "complete",
        choice_status: str = "graded",
        reviewed: bool = False,
        ai_score: int | None = 5,
        human_confirmed_score: int | None = None,
    ):
        self.grading_status = grading_status
        self.choice_status = choice_status
        self.reviewed = reviewed
        self.ai_score = ai_score
        self.human_confirmed_score = human_confirmed_score


def test_review_state_ai_draft() -> None:
    assert _compute_review_state(_FakeResult()) == "ai_draft"


def test_review_state_confirmed_same_score() -> None:
    assert _compute_review_state(_FakeResult(reviewed=True, ai_score=5, human_confirmed_score=5)) == "confirmed"


def test_review_state_confirmed_ai_null() -> None:
    """When AI score is null but examiner confirmed, treat as confirmed (not overridden)."""
    assert _compute_review_state(_FakeResult(reviewed=True, ai_score=None, human_confirmed_score=3)) == "confirmed"


def test_review_state_overridden() -> None:
    assert _compute_review_state(_FakeResult(reviewed=True, ai_score=5, human_confirmed_score=3)) == "overridden"


def test_review_state_ambiguous() -> None:
    assert _compute_review_state(_FakeResult(choice_status="flagged_ambiguous")) == "ambiguous"


def test_review_state_ambiguous_confirmed() -> None:
    """An ambiguous item that has been reviewed becomes confirmed, not ambiguous."""
    assert _compute_review_state(
        _FakeResult(choice_status="flagged_ambiguous", reviewed=True, ai_score=None, human_confirmed_score=2)
    ) == "confirmed"


def test_review_state_closed_blank() -> None:
    assert _compute_review_state(_FakeResult(choice_status="skipped_blank")) == "closed"


def test_review_state_closed_beyond_n() -> None:
    assert _compute_review_state(_FakeResult(choice_status="skipped_beyond_n")) == "closed"


def test_review_state_failed() -> None:
    assert _compute_review_state(_FakeResult(grading_status="failed")) == "failed"


def test_review_state_failed_overrides_everything() -> None:
    """A failed grading_status wins even if the result was reviewed."""
    assert _compute_review_state(
        _FakeResult(grading_status="failed", reviewed=True, ai_score=5, human_confirmed_score=5)
    ) == "failed"
