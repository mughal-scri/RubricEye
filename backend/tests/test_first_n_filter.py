"""Offline tests for the first-N filter and question identity (Phase 4).

Covers blank-answer handling, compound choice units, ambiguous-ink
respect for choice limits, roman-numeral sorting, and question label
canonicalization. Converted from validate_unattempted_lock.py,
validate_question_identity.py, and validate_roman_numeral_parts.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.first_n_filter import QuestionUnit, apply_first_n_filter
from app.services.ink_density import InkDensityResult
from app.services.question_grouping import (
    canonical_question_label,
    group_question_bank_by_group,
    resolve_region_keys_for_question,
    sort_question_labels,
)
from app.services.segmentation import safe_region_filename_key


# ---------------------------------------------------------------------------
# First-N filter (from validate_unattempted_lock.py)
# ---------------------------------------------------------------------------


def _make_regions(root: Path, keys: list[str]) -> Path:
    """Create dummy region crop files for the given question keys."""
    regions = root / "regions"
    regions.mkdir(parents=True, exist_ok=True)
    for key in keys:
        (regions / f"{safe_region_filename_key(key)}_p2.png").write_bytes(b"fixture")
    return regions


def test_unattempted_lock_blank_skipped_no_slot_consumed():
    """Blank answers must be skipped without consuming a choice slot.

    From validate_unattempted_lock.py — the core first-N regression.
    """
    with tempfile.TemporaryDirectory(prefix="rubriceye_filter_") as d:
        root = Path(d)
        keys = ["2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii", "3a", "3b", "4a", "4b"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            name = Path(paths[0]).name
            if name.startswith(f"{safe_region_filename_key('2i')}_"):
                return InkDensityResult("blank", 0.0)
            return InkDensityResult("attempted", 0.1)

        groups = [
            {
                "id": "b",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii"],
                "selection_units": [["2i"], ["2ii"], ["2iii"], ["2iv"], ["2v"], ["2vi"], ["2vii"]],
                "n_required": 5,
            },
            {
                "id": "c",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["3a", "3b", "4a", "4b"],
                "selection_units": [["3a", "3b"], ["4a", "4b"]],
                "n_required": 1,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter(
                {key: [{}] for key in keys}, regions, keys, groups
            )

        assert result.skipped_blank == ["2i"], f"2i should be skipped blank: {result.skipped_blank}"
        assert result.skipped_beyond_n == ["2vii", "4a", "4b"], (
            f"Beyond-N mismatch: {result.skipped_beyond_n}"
        )
        to_grade_keys = [u.question_number for u in result.to_grade]
        assert to_grade_keys == ["2ii", "2iii", "2iv", "2v", "2vi", "3a", "3b"], (
            f"to_grade mismatch: {to_grade_keys}"
        )


def test_first_n_ambiguous_items_respect_choice_limits():
    """Phase 0 fix: ambiguous-ink items must count toward the N limit.

    This is the regression for the 58-vs-35 bug: ambiguous items previously
    bypassed the choice limit, causing all items to leak through.
    """
    with tempfile.TemporaryDirectory(prefix="rubriceye_ambiguous_") as d:
        root = Path(d)
        keys = ["1a", "1b", "1c", "1d", "1e"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            # All items are ambiguous
            return InkDensityResult("ambiguous", 0.03)

        groups = [
            {
                "id": "a",
                "selection_type": "choose_n_of_m",
                "question_numbers": keys,
                "selection_units": [[k] for k in keys],
                "n_required": 2,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter(
                {key: [{}] for key in keys}, regions, keys, groups
            )

        # Only 2 should be flagged (counting toward N), the rest skipped
        assert len(result.flagged_ambiguous) == 2, (
            f"Expected 2 flagged ambiguous (N limit), got {len(result.flagged_ambiguous)}: "
            f"{result.flagged_ambiguous}"
        )
        assert len(result.skipped_beyond_n) == 3, (
            f"Expected 3 skipped beyond N, got {len(result.skipped_beyond_n)}: "
            f"{result.skipped_beyond_n}"
        )


def test_first_n_all_blank_group():
    """When all items in a choice group are blank, nothing is graded."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_allblank_") as d:
        root = Path(d)
        keys = ["5a", "5b", "5c"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            return InkDensityResult("blank", 0.0)

        groups = [
            {
                "id": "g",
                "selection_type": "choose_n_of_m",
                "question_numbers": keys,
                "selection_units": [[k] for k in keys],
                "n_required": 2,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter(
                {key: [{}] for key in keys}, regions, keys, groups
            )

        assert result.skipped_blank == keys
        assert result.to_grade == []
        assert result.flagged_ambiguous == []


def test_compound_choices_stay_together():
    """Compound selection units (e.g., [3a, 3b]) must be graded or skipped as one."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_compound_") as d:
        root = Path(d)
        keys = ["3a", "3b", "4a", "4b"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            return InkDensityResult("attempted", 0.2)

        groups = [
            {
                "id": "c",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["3a", "3b", "4a", "4b"],
                "selection_units": [["3a", "3b"], ["4a", "4b"]],
                "n_required": 1,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter(
                {key: [{}] for key in keys}, regions, keys, groups
            )

        # Only the first compound unit (3a+3b) should be graded
        to_grade_keys = sorted(u.question_number for u in result.to_grade)
        assert to_grade_keys == ["3a", "3b"], f"Expected [3a, 3b], got {to_grade_keys}"
        assert sorted(result.skipped_beyond_n) == ["4a", "4b"]


# ---------------------------------------------------------------------------
# Question identity (from validate_question_identity.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "labels",
    [
        ["Q2(i)", "Q.2(i)", "Question 2(i)", "2(i)", "2i"],
        ["Q3a", "Q.3a", "Question 3a", "3a"],
    ],
)
def test_canonical_label_equivalence(labels):
    """Equivalent label formats must normalize to the same canonical form."""
    canonical_set = {canonical_question_label(label) for label in labels}
    assert len(canonical_set) == 1, f"Labels {labels} did not normalize to a single form: {canonical_set}"


def test_resolve_region_keys_for_question():
    """Bare question number resolves all its part keys."""
    keys = ["2", "2i", "2ii", "2iii"]
    assert resolve_region_keys_for_question("Q2", keys) == keys
    assert resolve_region_keys_for_question("Q.2(ii)", keys) == ["2ii"]


def test_group_question_bank_by_group():
    """Group membership mapping is correct."""
    membership = group_question_bank_by_group(
        ["2i", "2ii"],
        [{"id": "g", "question_numbers": ["Q2"], "selection_units": []}],
    )
    assert membership == {"2i": "g", "2ii": "g"}


# ---------------------------------------------------------------------------
# Roman numeral sorting (from validate_roman_numeral_parts.py)
# ---------------------------------------------------------------------------


def test_sort_roman_numeral_labels_ascending():
    """Roman numeral labels must sort in true numeric order, not lexicographic."""
    shuffled = ["2vii", "2iii", "2i", "2v", "2ii", "2vi", "2iv"]
    sorted_labels = sort_question_labels(shuffled)
    expected = ["2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii"]
    assert sorted_labels == expected, f"Roman sort failed: {sorted_labels}"


def test_sort_mixed_letter_labels():
    """Single-letter part labels sort correctly."""
    shuffled = ["1c", "1a", "1b"]
    sorted_labels = sort_question_labels(shuffled)
    assert sorted_labels == ["1a", "1b", "1c"]


def test_sort_bare_numbers():
    """Bare question numbers (no parts) sort numerically."""
    shuffled = ["10", "2", "1", "5"]
    sorted_labels = sort_question_labels(shuffled)
    assert sorted_labels == ["1", "2", "5", "10"]
