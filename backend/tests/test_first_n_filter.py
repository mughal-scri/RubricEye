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


def test_attempted_unit_wins_slot_over_ambiguous_predecessor():
    """Attempted units claim choice slots before ambiguous ones, regardless of unit order.

    Regression for the inverted-selection bug: a noisy blank box that
    classifies as ambiguous used to consume a choice slot ahead of a genuinely
    attempted unit, closing the real attempt as beyond-N while opening the
    blank box for examiner review. Selection must depend only on the group
    config and the ink classification, never on which unit sorts first.
    """
    with tempfile.TemporaryDirectory(prefix="rubriceye_inversion_") as d:
        root = Path(d)
        keys = ["5a", "5b", "5c", "6a", "6b", "7a", "7b"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            statuses = {
                safe_region_filename_key("5a"): "ambiguous",
                safe_region_filename_key("5c"): "blank",
                safe_region_filename_key("6a"): "ambiguous",
                safe_region_filename_key("6b"): "ambiguous",
            }
            stem = Path(paths[0]).name.rsplit("_p", 1)[0]
            status = statuses.get(stem, "attempted")
            ratio = {"blank": 0.0, "ambiguous": 0.03}.get(status, 0.1)
            return InkDensityResult(status, ratio)

        groups = [
            {
                "id": "g1",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["5a", "5b", "5c"],
                "selection_units": [["5a"], ["5b"], ["5c"]],
                "n_required": 1,
            },
            {
                "id": "g2",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["6a", "6b", "7a", "7b"],
                "selection_units": [["6a", "6b"], ["7a", "7b"]],
                "n_required": 1,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter({key: [{}] for key in keys}, regions, keys, groups)

        to_grade_keys = [u.question_number for u in result.to_grade]
        assert to_grade_keys == ["5b", "7a", "7b"], f"to_grade mismatch: {to_grade_keys}"
        assert result.flagged_ambiguous == [], (
            f"Ambiguous predecessors must not be flagged when an attempted unit "
            f"takes the slot: {result.flagged_ambiguous}"
        )
        assert result.skipped_blank == ["5c"]
        assert result.skipped_beyond_n == ["5a", "6a", "6b"]
        # Compound members stay one unit: shared batch id and the union of both parts' images.
        seven_a, seven_b = result.to_grade[1], result.to_grade[2]
        assert seven_a.compound_batch_id == seven_b.compound_batch_id
        assert seven_a.compound_image_paths == seven_b.compound_image_paths


def test_half_attempted_compound_unit_is_the_chosen_attempt():
    """One attempted part makes the compound unit the chosen attempt.

    Acceptance Test B (Section C half): the unit is selected whole, and the
    blank part's crop travels in the same compound batch so it is graded 0
    rather than dropped.
    """
    with tempfile.TemporaryDirectory(prefix="rubriceye_half_") as d:
        root = Path(d)
        keys = ["8a", "8b", "9a", "9b"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            statuses = {
                safe_region_filename_key("8a"): "attempted",
                safe_region_filename_key("8b"): "blank",
                safe_region_filename_key("9a"): "blank",
                safe_region_filename_key("9b"): "blank",
            }
            stem = Path(paths[0]).name.rsplit("_p", 1)[0]
            status = statuses[stem]
            return InkDensityResult(status, 0.1 if status == "attempted" else 0.0)

        groups = [
            {
                "id": "c",
                "selection_type": "choose_n_of_m",
                "question_numbers": keys,
                "selection_units": [["8a", "8b"], ["9a", "9b"]],
                "n_required": 1,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter({key: [{}] for key in keys}, regions, keys, groups)

        to_grade_keys = [u.question_number for u in result.to_grade]
        assert to_grade_keys == ["8a", "8b"], f"Half-attempted unit must be selected whole: {to_grade_keys}"
        assert result.to_grade[0].compound_batch_id == result.to_grade[1].compound_batch_id
        assert len(result.to_grade[0].compound_image_paths) == 2, (
            "Both parts' evidence must reach the shared grading call"
        )
        assert result.skipped_blank == ["9a", "9b"]
        assert result.flagged_ambiguous == []
        assert result.skipped_beyond_n == []


def test_underfilled_choice_group_is_not_padded():
    """Acceptance Test B (Section B): fewer attempted units than N required.

    Blank units must never be selected just to fill the quota.
    """
    with tempfile.TemporaryDirectory(prefix="rubriceye_underfill_") as d:
        root = Path(d)
        keys = ["2i", "2ii", "2iii", "2iv", "2v"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            stem = Path(paths[0]).name.rsplit("_p", 1)[0]
            status = "attempted" if stem != safe_region_filename_key("2v") else "blank"
            return InkDensityResult(status, 0.1 if status == "attempted" else 0.0)

        groups = [
            {
                "id": "b",
                "selection_type": "choose_n_of_m",
                "question_numbers": keys,
                "selection_units": [[k] for k in keys],
                "n_required": 5,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter({key: [{}] for key in keys}, regions, keys, groups)

        to_grade_keys = [u.question_number for u in result.to_grade]
        assert to_grade_keys == ["2i", "2ii", "2iii", "2iv"], f"No padding expected: {to_grade_keys}"
        assert result.skipped_blank == ["2v"]
        assert result.flagged_ambiguous == []
        assert result.skipped_beyond_n == []


def test_ambiguous_fills_leftover_slots_only():
    """Ambiguous units fill only the slots attempted units leave behind."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_leftover_") as d:
        root = Path(d)
        keys = ["1a", "1b", "1c", "1d", "1e"]
        regions = _make_regions(root, keys)

        def classify(paths, *_args):
            statuses = {
                safe_region_filename_key("1a"): "attempted",
                safe_region_filename_key("1b"): "ambiguous",
                safe_region_filename_key("1c"): "ambiguous",
                safe_region_filename_key("1d"): "ambiguous",
                safe_region_filename_key("1e"): "blank",
            }
            stem = Path(paths[0]).name.rsplit("_p", 1)[0]
            status = statuses[stem]
            ratio = {"attempted": 0.1, "ambiguous": 0.03, "blank": 0.0}[status]
            return InkDensityResult(status, ratio)

        groups = [
            {
                "id": "a",
                "selection_type": "choose_n_of_m",
                "question_numbers": keys,
                "selection_units": [[k] for k in keys],
                "n_required": 3,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter({key: [{}] for key in keys}, regions, keys, groups)

        to_grade_keys = [u.question_number for u in result.to_grade]
        assert to_grade_keys == ["1a"]
        assert result.flagged_ambiguous == ["1b", "1c"]
        assert result.skipped_beyond_n == ["1d"]
        assert result.skipped_blank == ["1e"]


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
