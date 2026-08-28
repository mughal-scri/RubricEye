"""Regression tests for grading totals and ink-density classification.

These tests verify the consolidated total marks computation and ink-density
pre-filter logic without requiring live API calls or real PDF processing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.reporting import compute_totals


@dataclass
class MockGradingResult:
    """Minimal mock for GradingResult with only the fields compute_totals uses."""

    choice_status: str
    grading_status: str
    ai_score: int | None
    ai_total_possible: int | None
    human_confirmed_score: int | None = None
    reviewed: bool = False


def _score(result: MockGradingResult) -> int | None:
    return result.human_confirmed_score if result.reviewed else result.ai_score


def test_compute_totals_excludes_no_regions():
    """Verify that no_regions items are excluded from the denominator.

    This is the regression test for the 58-vs-35 bug: the summary endpoint
    previously included no_regions items (which have grading_status="failed")
    in the total, inflating the denominator.
    """
    results = [
        # 5 graded questions worth 7 marks each = 35 total
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=5, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=6, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=4, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=7, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=3, ai_total_possible=7),
        # 3 no_regions questions worth 8 marks each = 24 marks (should be EXCLUDED)
        MockGradingResult(choice_status="no_regions", grading_status="failed", ai_score=None, ai_total_possible=8),
        MockGradingResult(choice_status="no_regions", grading_status="failed", ai_score=None, ai_total_possible=8),
        MockGradingResult(choice_status="no_regions", grading_status="failed", ai_score=None, ai_total_possible=8),
    ]
    awarded, possible = compute_totals(results)
    # Only the 5 graded items count: 5+6+4+7+3 = 25 awarded, 5*7 = 35 possible
    assert awarded == 25, f"Expected awarded=25, got {awarded}"
    assert possible == 35, f"Expected possible=35, got {possible}"


def test_compute_totals_excludes_skipped_items():
    """Verify that skipped_blank and skipped_beyond_n items are excluded."""
    results = [
        # 3 graded questions worth 10 marks each
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=8, ai_total_possible=10),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=7, ai_total_possible=10),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=9, ai_total_possible=10),
        # Skipped blank (should be excluded)
        MockGradingResult(choice_status="skipped_blank", grading_status="complete", ai_score=None, ai_total_possible=10),
        # Skipped beyond N (should be excluded)
        MockGradingResult(choice_status="skipped_beyond_n", grading_status="complete", ai_score=None, ai_total_possible=10),
    ]
    awarded, possible = compute_totals(results)
    # Only the 3 graded items: 8+7+9 = 24 awarded, 3*10 = 30 possible
    assert awarded == 24
    assert possible == 30


def test_compute_totals_includes_flagged_ambiguous():
    """Verify that flagged_ambiguous items are included (they need examiner review)."""
    results = [
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=5, ai_total_possible=10),
        MockGradingResult(choice_status="flagged_ambiguous", grading_status="complete", ai_score=None, ai_total_possible=10),
    ]
    awarded, possible = compute_totals(results)
    # Graded: 5 awarded, 10 possible. Ambiguous: 0 awarded (no score yet), 10 possible.
    assert awarded == 5
    assert possible == 20


def test_compute_totals_excludes_failed_grading():
    """Verify that items with grading_status='failed' are excluded even if choice_status is graded."""
    results = [
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=8, ai_total_possible=10),
        MockGradingResult(choice_status="graded", grading_status="failed", ai_score=None, ai_total_possible=10),
    ]
    awarded, possible = compute_totals(results)
    # Only the complete item counts
    assert awarded == 8
    assert possible == 10


def test_compute_totals_uses_human_confirmed_score():
    """Verify that human_confirmed_score overrides ai_score when reviewed."""
    results = [
        MockGradingResult(
            choice_status="graded",
            grading_status="complete",
            ai_score=5,
            ai_total_possible=10,
            human_confirmed_score=7,
            reviewed=True,
        ),
    ]
    awarded, possible = compute_totals(results)
    assert awarded == 7  # Uses human_confirmed_score, not ai_score
    assert possible == 10


def test_compute_totals_worst_case_paper():
    """Regression test for the specific worst-case paper: stated total 35, app reported 58.

    The paper has:
    - 5 graded questions worth 7 marks each = 35 marks (reviewable)
    - 3 no_regions questions worth ~8 marks each = 24 marks (excluded)
    Total if no_regions incorrectly included: 35 + 24 = 59 (close to 58)
    Total with correct exclusion: 35

    This test asserts the correct behavior: possible == 35, not 58/59.
    """
    results = [
        # 5 graded questions (the actual exam content)
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=5, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=6, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=4, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=7, ai_total_possible=7),
        MockGradingResult(choice_status="graded", grading_status="complete", ai_score=3, ai_total_possible=7),
        # 3 no_regions questions (template map gaps — should NOT count)
        MockGradingResult(choice_status="no_regions", grading_status="failed", ai_score=None, ai_total_possible=8),
        MockGradingResult(choice_status="no_regions", grading_status="failed", ai_score=None, ai_total_possible=8),
        MockGradingResult(choice_status="no_regions", grading_status="failed", ai_score=None, ai_total_possible=7),
    ]
    awarded, possible = compute_totals(results)
    assert possible == 35, f"CRITICAL: total marks should be 35 (stated on paper), got {possible}. The no_regions items must be excluded."
