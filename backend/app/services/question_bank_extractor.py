"""Auto-extracts QuestionBankItem candidates (question_number, marks_possible,
key_points) from a typeset rubric PDF at project creation time (Phase 2 plan §3).

Best-effort regex extraction over PyMuPDF text — always reviewed/correctable by the
examiner in Question Bank Setup before locking, so false positives here are a UX
annoyance, not a correctness risk, as long as they're never silently graded on.

Edge Case D (scanned/no-text-layer rubric): if PyMuPDF reports near-empty text despite
the PDF having pages, `extract_question_bank` returns an empty list and sets
`used_vision_fallback=False` with `has_text_layer=False` — the caller (routes/projects.py)
is expected to fall back to the vision extractor. The actual vision-based structural
read is NOT implemented in this file (out of scope for Phase 2 per the plan — it reuses
the *pattern* already built for template derivation, not this module) and is flagged as
a follow-up in PHASE2_NOTES.md rather than silently stubbed out here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from app.services.question_grouping import canonical_question_label, roman_to_int

# Matches top-level question headers: "Q.1", "Q1", "Question 2", or a bare "3." at
# the start of a line.
_TOP_HEADER = re.compile(
    r"(?:^|\n)\s*(?:Q(?:uestion)?\.?\s*)(\d+)([a-z]|(?:i{1,3}|iv|v|vi{0,3}|ix|x))?\b|(?:^|\n)\s*(\d+)\s*[).]\s",
    re.IGNORECASE,
)

# Matches sub-part headers within a question's block: "(a)", "Part (a)", "a)", "a.",
# and the same forms with a roman numeral instead of a single letter ("(vii)", "vii.").
# The broadened [a-zA-Z]+ over-matches on its own (e.g. a stray word at a line start
# followed by a period) -- _is_valid_part_label() below filters those out, so only a
# real single letter or a syntactically valid roman numeral survives as a match.
_PART_HEADER = re.compile(
    r"(?:Part\s*)?\(([a-zA-Z]+)\)|(?:^|\n)\s*([a-zA-Z]+)[).]\s",
    re.IGNORECASE,
)

# Matches a marks value near a header: "(6 marks)", "- 6 marks", "[6]", "(6)"
_MARKS_PATTERN = re.compile(r"(\d+)\s*marks?\b|\((\d+)\)|\[(\d+)\]", re.IGNORECASE)

# Matches the paper's own stated total -- "Total Marks: 53" or "Maximum Marks: 35"
# (confirmed against a real mock exam that uses the latter phrasing; the original
# version of this pattern only recognized "total", which silently found nothing on
# that paper rather than warning on a real mismatch).
_TOTAL_MARKS_PATTERN = re.compile(r"(?:total|maximum)\s*marks?\s*[:\-]?\s*(\d+)", re.IGNORECASE)

MIN_TEXT_LAYER_CHARS = 40


def _is_valid_part_label(token: str) -> bool:
    token = token.lower()
    if len(token) == 1 and token.isalpha():
        return True
    return roman_to_int(token) is not None


@dataclass
class QuestionBankItemData:
    question_number: str
    marks_possible: int | None
    key_points: str


@dataclass
class ExtractionResult:
    items: list[QuestionBankItemData] = field(default_factory=list)
    has_text_layer: bool = True
    stated_total_marks: int | None = None


def _has_real_text_layer(doc: "fitz.Document") -> bool:
    total_chars = 0
    for page in doc:
        total_chars += len((page.get_text() or "").strip())
        if total_chars >= MIN_TEXT_LAYER_CHARS:
            return True
    return False


def _nearest_marks(window_text: str) -> int | None:
    match = _MARKS_PATTERN.search(window_text)
    if not match:
        return None
    for group in match.groups():
        if group is not None:
            return int(group)
    return None


def _extract_stated_total(full_text: str) -> int | None:
    match = _TOTAL_MARKS_PATTERN.search(full_text)
    return int(match.group(1)) if match else None


def _split_question_blocks(full_text: str) -> list[tuple[str, str]]:
    """Returns [(question_number, block_text), ...] split on top-level headers."""
    matches = list(_TOP_HEADER.finditer(full_text))
    blocks: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        qnum = canonical_question_label(f"{match.group(1)}{match.group(2) or ''}" if match.group(1) else match.group(3))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        blocks.append((qnum, full_text[start:end]))
    return blocks


def _extract_parts(question_number: str, block_text: str) -> list[QuestionBankItemData]:
    raw_matches = list(_PART_HEADER.finditer(block_text))
    part_matches = [m for m in raw_matches if _is_valid_part_label(m.group(1) or m.group(2) or "")]

    if not part_matches:
        marks = _nearest_marks(block_text[:200])
        key_points = block_text.strip()[:2000]
        return [QuestionBankItemData(question_number=question_number, marks_possible=marks, key_points=key_points)]

    items: list[QuestionBankItemData] = []
    for idx, match in enumerate(part_matches):
        part = (match.group(1) or match.group(2) or "").lower()
        start = match.end()
        end = part_matches[idx + 1].start() if idx + 1 < len(part_matches) else len(block_text)
        part_text = block_text[start:end]
        marks = _nearest_marks(part_text[:120])
        items.append(
            QuestionBankItemData(
                question_number=canonical_question_label(f"{question_number}{part}"),
                marks_possible=marks,
                key_points=part_text.strip()[:2000],
            )
        )
    return items


def find_stated_total(pdf_path: str) -> int | None:
    """Public helper for Edge Case H (cross-check at question-bank confirm time),
    usable against either the rubric or the question paper PDF.
    """
    doc = fitz.open(pdf_path)
    try:
        full_text = "\n".join(page.get_text() or "" for page in doc)
    finally:
        doc.close()
    return _extract_stated_total(full_text)


def extract_question_bank(rubric_pdf_path: str) -> ExtractionResult:
    doc = fitz.open(rubric_pdf_path)
    try:
        if not _has_real_text_layer(doc):
            return ExtractionResult(items=[], has_text_layer=False, stated_total_marks=None)

        full_text = "\n".join(page.get_text() or "" for page in doc)
    finally:
        doc.close()

    stated_total = _extract_stated_total(full_text)
    blocks = _split_question_blocks(full_text)

    items: list[QuestionBankItemData] = []
    for question_number, block_text in blocks:
        items.extend(_extract_parts(question_number, block_text))

    return ExtractionResult(items=items, has_text_layer=True, stated_total_marks=stated_total)
