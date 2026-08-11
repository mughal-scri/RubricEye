"""Resolves the granularity mismatch between segmentation and grading.

Phase 1's `question_region_map` (services/segmentation.py) keys regions by
`question_number + part_label` combined — e.g. "3a" and "3b" are separate top-level
keys, never grouped under a shared "3". The Phase 2 plan's QuestionBankItem /
GradingResult, by contrast, use a single `question_number` field with no explicit
part concept.

Rather than force one fixed granularity, this module lets QuestionBankItem.question_number
be EITHER a bare number ("3", aggregating all its parts) OR a full part-level key ("3a"),
decided by whatever the examiner confirms in Question Bank Setup — and resolves either
choice correctly against the region map. This is the piece of Phase 2 the source
documents didn't specify; see PHASE2_NOTES.md for the full rationale.
"""

from __future__ import annotations

import re

_KEY_PATTERN = re.compile(r"^(\d+)([a-z]?)$", re.IGNORECASE)


def split_base_and_part(key: str) -> tuple[str, str]:
    """'3a' -> ('3', 'a'); '3' -> ('3', ''); anything unparseable -> (key, '')."""
    match = _KEY_PATTERN.match(key.strip())
    if not match:
        return key.strip(), ""
    return match.group(1), match.group(2).lower()


def resolve_region_keys_for_question(question_number: str, region_map_keys: list[str]) -> list[str]:
    """Finds every region-map key that belongs to a given QuestionBankItem.question_number.

    - Exact match ("3a" -> ["3a"]) covers the part-level-QuestionBankItem case.
    - Prefix match ("3" -> ["3a", "3b", "3"]) covers the whole-question-QuestionBankItem case.
    """
    qn = question_number.strip()
    exact = [key for key in region_map_keys if key == qn]
    if exact:
        return exact

    base_qn, part_qn = split_base_and_part(qn)
    if part_qn:
        # question_number itself already names a specific part but wasn't an exact
        # key match (e.g. region map only has "3" because segmentation didn't split
        # it) — fall back to the base number.
        return [key for key in region_map_keys if split_base_and_part(key)[0] == base_qn]

    return [key for key in region_map_keys if split_base_and_part(key)[0] == base_qn]


def group_question_bank_by_group(
    question_bank_numbers: list[str],
    question_groups: list[dict],
) -> dict[str, str | None]:
    """Maps each QuestionBankItem.question_number to the id of the QuestionGroup it
    belongs to (or None if ungrouped). A question_number belongs to a group if it
    appears in that group's question_numbers list, matched at whichever granularity
    the group was defined with (exact, or base-number containment).
    """
    membership: dict[str, str | None] = {qn: None for qn in question_bank_numbers}
    for group in question_groups:
        group_id = group["id"]
        listed = set(group.get("question_numbers", []))
        for qn in question_bank_numbers:
            if membership[qn] is not None:
                continue
            if qn in listed:
                membership[qn] = group_id
                continue
            base_qn, _ = split_base_and_part(qn)
            if base_qn in listed:
                membership[qn] = group_id
    return membership
