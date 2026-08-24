#!/usr/bin/env python3
"""Verify optional-section effective marks without invoking any model."""

from __future__ import annotations

from real_fixture_paths import QUESTION_PAPER, RUBRIC
from app.services.paper_structure import calculate_structure, infer_group_suggestions
from app.services.question_bank_extractor import extract_question_bank


def main() -> int:
    extracted = extract_question_bank(str(RUBRIC))
    items = [{"question_number": item.question_number, "marks_possible": item.marks_possible} for item in extracted.items]
    suggestions = infer_group_suggestions(str(QUESTION_PAPER), items)
    groups = [
        {
            "group_name": suggestion.group_name,
            "selection_type": suggestion.selection_type,
            "question_numbers": suggestion.question_numbers,
            "selection_units": suggestion.selection_units,
            "n_required": suggestion.n_required,
        }
        for suggestion in suggestions
    ]
    result = calculate_structure(items, groups, stated_total=35)
    assert result.raw_total == 58, result
    assert result.effective_total == 35, result
    assert result.status == "resolved", result
    assert {group["n_required"] for group in groups} == {1, 5}, groups
    assert any(len(unit) == 2 for group in groups for unit in group["selection_units"]), groups
    print("Paper-structure regression passed: raw 58 marks resolve to effective 35 marks using inferred optional groups.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
