#!/usr/bin/env python3
"""Verify optional-section inference across varied, non-paper-specific wording."""
from __future__ import annotations

import tempfile
from pathlib import Path

import fitz

from app.services.paper_structure import calculate_structure, infer_group_suggestions


def write_pdf(text: str) -> str:
    path = Path(tempfile.mkstemp(prefix="rubriceye_structure_", suffix=".pdf")[1])
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((40, 50), text, fontsize=9)
    doc.save(path)
    doc.close()
    return str(path)


def check(text: str, items: list[dict], expected_n: int, expected_units: list[list[str]], stated: int, expected_effective: int) -> None:
    path = write_pdf(text)
    try:
        suggestions = infer_group_suggestions(path, items)
        match = next((suggestion for suggestion in suggestions if suggestion.selection_units == expected_units), None)
        assert match is not None, suggestions
        assert match.n_required == expected_n, match
        result = calculate_structure(items, [{"group_name": match.group_name, "selection_type": match.selection_type, "question_numbers": match.question_numbers, "selection_units": match.selection_units, "n_required": match.n_required}], stated)
        assert result.effective_total == expected_effective, result
        assert result.status == "resolved", result
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> int:
    check(
        "PART 3\nAnswer any 1 of the following 2 questions.\nQ3: Attempt both parts.\nQ4: Attempt both parts.",
        [{"question_number": qn, "marks_possible": marks} for qn, marks in (("3a", 6), ("3b", 4), ("4a", 6), ("4b", 4))],
        1,
        [["3a", "3b"], ["4a", "4b"]],
        10,
        10,
    )
    check(
        "GROUP B\nAttempt any five out of the given seven questions.\nQ2: [4]\nQ3: [4]\nQ4: [4]\nQ5: [4]\nQ6: [4]\nQ7: [4]\nQ8: [4]",
        [{"question_number": str(number), "marks_possible": 4} for number in range(2, 9)],
        5,
        [[str(number)] for number in range(2, 9)],
        20,
        20,
    )
    check(
        "SECTION IV\nChoose any one of the following two questions.\nQ5: [10]\nQ6: [10]",
        [{"question_number": "5", "marks_possible": 10}, {"question_number": "6", "marks_possible": 10}],
        1,
        [["5"], ["6"]],
        10,
        10,
    )
    check(
        "PART C\nEither Question 3 or Question 4 should be attempted.\nQ3: [10]\nQ4: [10]",
        [{"question_number": "3", "marks_possible": 10}, {"question_number": "4", "marks_possible": 10}],
        1,
        [["3"], ["4"]],
        10,
        10,
    )
    multi_section_path = write_pdf(
        "SECTION B\nAnswer any five out of the following seven questions.\n"
        "Q2: [4]\nQ3: [4]\nQ4: [4]\nQ5: [4]\nQ6: [4]\nQ7: [4]\nQ8: [4]\n"
        "SECTION C\nAnswer any one of the following two questions.\nQ9: [5]\nQ10: [5]"
    )
    try:
        multi_section = infer_group_suggestions(
            multi_section_path,
            [{"question_number": str(number), "marks_possible": 4} for number in range(2, 9)]
            + [{"question_number": "9", "marks_possible": 5}, {"question_number": "10", "marks_possible": 5}],
        )
        units = {tuple(tuple(unit) for unit in suggestion.selection_units): suggestion for suggestion in multi_section}
        assert (("2",), ("3",), ("4",), ("5",), ("6",), ("7",), ("8",)) in units, multi_section
        assert (("9",), ("10",)) in units, multi_section
        assert units[(("2",), ("3",), ("4",), ("5",), ("6",), ("7",), ("8",))].n_required == 5
        assert units[(("9",), ("10",))].n_required == 1
    finally:
        Path(multi_section_path).unlink(missing_ok=True)
    print("Generic paper-structure regression passed: varied verbs, word numbers, following/given clauses, headings, and either/or instructions are inferred without fixed section labels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
