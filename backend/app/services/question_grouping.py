"""Helpers for matching and ordering whole questions and their printed parts.

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

Part labels may be a single letter ("a", "b", ...) OR a lowercase roman numeral
("i", "ii", ... "vii", ...) — both are common exam conventions. The two are genuinely
ambiguous in isolation ("v" is a valid single letter AND a valid roman numeral) —
resolved by looking at the whole sibling group a part belongs to, not each label alone:
if ANY sibling is a multi-character roman numeral (e.g. "vii"), the whole group is
 treated as roman-numeral, since a single question's sibling parts normally use one
convention. See `build_part_sort_key`.

"""

from __future__ import annotations

import re

_KEY_PATTERN = re.compile(r"^(\d+)([a-zA-Z]*)$")
_CANONICAL_PATTERN = re.compile(r"^(?:question|q)?\s*\.?\s*(\d+)\s*(?:\(\s*([a-zA-Z]+)\s*\)|([a-zA-Z]+))?$", re.IGNORECASE)
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def canonical_question_label(raw: str) -> str:
    """Normalize equivalent printed labels to one internal identity.

    Examples such as ``Q2(i)``, ``Q.2(i)``, ``Question 2(i)``, ``2(i)``, and
    ``2i`` all become ``2i``. Unknown free-form labels are preserved in a
    conservative case-folded form rather than guessed into a numeric identity.
    """
    normalized = " ".join(str(raw or "").strip().split())
    match = _CANONICAL_PATTERN.match(normalized)
    if not match:
        return normalized.casefold()
    return f"{match.group(1)}{(match.group(2) or match.group(3) or '').casefold()}"


def split_base_and_part(key: str) -> tuple[str, str]:
    """'3a' -> ('3', 'a'); '2vii' -> ('2', 'vii'); '3' -> ('3', '')."""
    match = _KEY_PATTERN.match(key.strip())
    if not match:
        return key.strip(), ""
    return match.group(1), match.group(2).lower()


def _normalize_for_sort(raw: str) -> str:
    return canonical_question_label(raw)


def question_sort_key(question_number: str, sibling_labels: list[str] | None = None) -> tuple:
    """Return a stable natural-order key for a printed question label.

    Numeric bases sort numerically (so ``10`` follows ``2``), bare questions sort
    before their parts, and common printed Q2/Q2(i) forms are normalized only for
    sorting. When sibling labels are supplied, their shared part convention decides
    Roman-versus-letter ordering; without siblings, multi-character Roman labels are
    recognized but ambiguous single-character labels default to plain letters.
    """
    raw = question_number.strip()
    normalized = _normalize_for_sort(raw)
    base, part = split_base_and_part(normalized)
    if base.isdigit():
        base_key = (0, int(base))
    else:
        base_key = (1, base.casefold())
    if not part:
        part_key = (0, 0, "")
    else:
        sibling_parts = []
        for sibling in sibling_labels or []:
            sibling_base, sibling_part = split_base_and_part(_normalize_for_sort(sibling))
            if sibling_base == base and sibling_part:
                sibling_parts.append(sibling_part)
        if sibling_parts:
            part_key = (1, *build_part_sort_key(sibling_parts)(part))
        elif len(part) > 1 and roman_to_int(part) is not None:
            part_key = (1, 1, roman_to_int(part))
        elif part.isalpha():
            part_key = (1, 0, ord(part[0]) - ord("a"), part.casefold())
        else:
            part_key = (2, 0, part.casefold())
    return (*base_key, *part_key, raw.casefold())


def sort_question_labels(labels: list[str]) -> list[str]:
    """Sort labels naturally while resolving each base number's part convention."""
    return sorted(labels, key=lambda label: question_sort_key(label, labels))


def sort_records_by_question(records: list[object], label_getter) -> list[object]:
    """Sort records by their labels with sibling-aware part classification."""
    labels = [label_getter(record) for record in records]
    return sorted(records, key=lambda record: question_sort_key(label_getter(record), labels))


def roman_to_int(token: str) -> int | None:
    """Return the integer value of a syntactically valid lowercase Roman numeral."""
    token = token.lower()
    if not token or any(ch not in _ROMAN_VALUES for ch in token):
        return None
    total = 0
    previous_value = 0
    for ch in reversed(token):
        value = _ROMAN_VALUES[ch]
        if value < previous_value:
            total -= value
        else:
            total += value
            previous_value = value
    return total if _int_to_roman(total) == token else None


def _int_to_roman(n: int) -> str:
    table = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    ]
    result = []
    for value, symbol in table:
        while n >= value:
            result.append(symbol)
            n -= value
    return "".join(result)


def build_part_sort_key(sibling_parts: list[str]):
    """Return a sort-key function using the whole sibling group convention."""
    has_multi_character_roman = any(len(part) > 1 and roman_to_int(part) is not None for part in sibling_parts)
    has_non_roman_letter = any(part.isalpha() and roman_to_int(part) is None for part in sibling_parts)
    uses_roman = has_multi_character_roman and not has_non_roman_letter

    def key(part: str) -> tuple:
        if not part:
            return (0,)
        if uses_roman:
            value = roman_to_int(part)
            if value is not None:
                return (1, value)
            return (2, part)
        if len(part) == 1 and part.isalpha():
            return (1, ord(part) - ord("a"))
        return (2, part)

    return key


def resolve_region_keys_for_question(question_number: str, region_map_keys: list[str]) -> list[str]:
    """Find every region-map key belonging to a whole question or one part."""
    qn = canonical_question_label(question_number)
    base_qn, part_qn = split_base_and_part(qn)
    if part_qn:
        return [key for key in region_map_keys if canonical_question_label(key) == qn]
    return [key for key in region_map_keys if split_base_and_part(canonical_question_label(key))[0] == base_qn]


def group_question_bank_by_group(
    question_bank_numbers: list[str],
    question_groups: list[dict],
) -> dict[str, str | None]:
    """Map each QuestionBankItem label to its QuestionGroup ID or None."""
    membership: dict[str, str | None] = {qn: None for qn in question_bank_numbers}
    for group in question_groups:
        group_id = group["id"]
        listed = {canonical_question_label(str(value)) for value in group.get("question_numbers", [])}
        for qn in question_bank_numbers:
            if membership[qn] is not None:
                continue
            canonical_qn = canonical_question_label(qn)
            if canonical_qn in listed:
                membership[qn] = group_id
                continue
            base_qn, _ = split_base_and_part(canonical_qn)
            if base_qn in listed:
                membership[qn] = group_id
    return membership
