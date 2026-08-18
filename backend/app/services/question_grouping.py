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

Part labels may be a single letter ("a", "b", ...) OR a lowercase roman numeral
("i", "ii", ... "vii", ...) — both are real exam conventions, confirmed by testing
against Abdullah's actual mock exam (Q2's seven sub-parts are roman numerals, not
letters). The two are genuinely ambiguous in isolation ("v" is a valid single letter
AND a valid roman numeral) — resolved by looking at the whole sibling group a part
belongs to, not each label alone: if ANY sibling is a multi-character roman numeral
(e.g. "vii"), the whole group is treated as roman-numeral, since no real exam mixes
both schemes within one question's sub-parts. See `build_part_sort_key`.
"""

from __future__ import annotations

import re

# Digits, then the ENTIRE trailing letter run as one unit -- whether that's a single
# letter ("3a") or a multi-character roman numeral ("2vii"). Splitting on "one letter
# max" (the original version of this regex) silently broke on anything past "a" in a
# roman-numeral scheme; capturing the whole run and classifying it separately (see
# `build_part_sort_key`) handles both conventions correctly.
_KEY_PATTERN = re.compile(r"^(\d+)([a-zA-Z]*)$")

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def split_base_and_part(key: str) -> tuple[str, str]:
    """'3a' -> ('3', 'a'); '2vii' -> ('2', 'vii'); '3' -> ('3', ''); anything
    unparseable -> (key, '')."""
    match = _KEY_PATTERN.match(key.strip())
    if not match:
        return key.strip(), ""
    return match.group(1), match.group(2).lower()


def roman_to_int(token: str) -> int | None:
    """Returns the integer value of a lowercase roman numeral, or None if `token`
    isn't a syntactically valid one. Validates by round-tripping (encoding the parsed
    value back to a numeral and comparing) rather than just summing symbol values, so
    malformed strings like "iiii" or "vx" are correctly rejected rather than silently
    given a plausible-looking value.
    """
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
    """Returns a sort-key function for a group of sibling part labels, choosing the
    roman-numeral or plain-letter convention based on the WHOLE group rather than
    guessing per label. A lone "i" or "v" is genuinely ambiguous; a sibling like
    "vii" is not, and settles it for the whole group.
    """
    uses_roman = any(len(part) > 1 and roman_to_int(part) is not None for part in sibling_parts)

    def key(part: str) -> tuple:
        if not part:
            return (0,)
        if uses_roman:
            value = roman_to_int(part)
            if value is not None:
                return (1, value)
            return (2, part)  # unrecognized -- sort after every valid roman numeral
        if len(part) == 1 and part.isalpha():
            return (1, ord(part) - ord("a"))
        return (2, part)

    return key


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
