from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import fitz

from app.services.question_bank_extractor import find_stated_total
from app.services.question_grouping import split_base_and_part

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_NUMBER_TOKEN = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"

# These patterns describe generic instruction language, not a particular paper.
# They are only provisional suggestions; the examiner can inspect and edit the groups.
_CHOICE_INSTRUCTION_RE = re.compile(
    rf"\b(?:answer|attempt|choose|select|solve|do)\s+(?:only\s+)?(?:any\s+)?(?P<n>{_NUMBER_TOKEN})\s+"
    rf"(?:(?:out|from)\s+of|of)\s+(?:(?:the|a)\s+)?(?:(?:following|given|listed)\s+)?"
    rf"(?P<m>{_NUMBER_TOKEN})\s+(?:questions|items)\b",
    re.IGNORECASE,
)
_SIMPLE_CHOICE_RE = re.compile(
    rf"\b(?:answer|attempt|choose|select|solve|do)\s+(?:only\s+)?(?:any\s+)?(?P<n>{_NUMBER_TOKEN})\s+(?:questions|items)\b",
    re.IGNORECASE,
)
_OPEN_CHOICE_RE = re.compile(
    rf"\b(?:answer|attempt|choose|select|solve|do)\s+(?:only\s+)?(?:any\s+)?(?P<n>{_NUMBER_TOKEN})\s+(?:out\s+of|of)\s+(?:(?:the|a)\s+)?(?:(?:following|given|listed)\s+)?(?:questions|items)\b",
    re.IGNORECASE,
)
_EITHER_RE = re.compile(
    r"\b(?:either\s+)?(?:question|q)\s*(?P<first>\d+)\D+(?:or|either)\s+(?:question|q)\s*(?P<second>\d+)\b.*?\b(?:attempted|answered|selected)\b",
    re.IGNORECASE | re.DOTALL,
)
_SECTION_HEADING_RE = re.compile(
    r"^[ \t]*(?:section|part|group)[ \t]+[A-Z0-9IVX]+[ \t]*(?:[:.)\-—][ \t]*|(?=\n|$))",
    re.IGNORECASE | re.MULTILINE,
)
_TOP_Q_RE = re.compile(r"(?:^|\n)\s*Q(?:uestion)?\.?\s*(\d+)\s*[:.)\-]", re.IGNORECASE)


@dataclass
class GroupSuggestion:
    group_name: str
    selection_type: str
    question_numbers: list[str]
    n_required: int | None
    selection_units: list[list[str]] = field(default_factory=list)
    evidence: str = ""
    confidence: str = "medium"


@dataclass
class StructureResult:
    raw_total: int
    effective_total: int | None
    stated_total: int | None
    status: str
    warning: str | None
    suggestions: list[GroupSuggestion] = field(default_factory=list)


def _paper_text(path: str) -> str:
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text("text", sort=True) or "" for page in doc)
    finally:
        doc.close()


def _marks(items: list[dict], qn: str) -> list[int]:
    return [int(item["marks_possible"]) for item in items if item["question_number"] == qn and item.get("marks_possible") is not None]


def _unit_keys_for_base(items: list[dict], base: str) -> list[str]:
    members = [item["question_number"] for item in items if split_base_and_part(item["question_number"])[0] == base]
    return members or [base]


def _number_value(token: str) -> int:
    normalized = token.strip().lower()
    return int(normalized) if normalized.isdigit() else _NUMBER_WORDS[normalized]


def _section_span(text: str, position: int) -> tuple[int, int]:
    """Return the span bounded by the nearest document-derived section heading."""
    headings = list(_SECTION_HEADING_RE.finditer(text))
    previous = [heading.start() for heading in headings if heading.start() <= position]
    following = [heading.start() for heading in headings if heading.start() > position]
    return (max(previous) if previous else 0, min(following) if following else len(text))


def _question_block(text: str, position: int) -> tuple[str, str, int] | None:
    headers = list(_TOP_Q_RE.finditer(text))
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        section_break = _SECTION_HEADING_RE.search(text, header.end(), end)
        if section_break:
            end = section_break.start()
        if header.start() <= position < end:
            return header.group(1), text[header.start():end], header.start()
    return None


def _bases_after(text: str, start: int, end: int) -> list[str]:
    bases: list[str] = []
    for match in _TOP_Q_RE.finditer(text, start, end):
        base = match.group(1)
        if base not in bases:
            bases.append(base)
    return bases


def _suggestion(group_name: str, n_required: int, units: list[list[str]], evidence: str) -> GroupSuggestion | None:
    if not units or n_required < 1 or n_required >= len(units):
        return None
    flat = [question for unit in units for question in unit]
    return GroupSuggestion(
        group_name=group_name,
        selection_type="choose_n_of_m",
        question_numbers=flat,
        n_required=n_required,
        selection_units=units,
        evidence=evidence.strip(),
        confidence=("high" if re.search(r"\b(?:of|out of)\b", evidence, re.IGNORECASE) else "medium"),
    )


def infer_group_suggestions(question_paper_path: str, items: list[dict]) -> list[GroupSuggestion]:
    """Infer optional groups from document instructions, never from a fixed paper label/list."""
    text = _paper_text(question_paper_path)
    suggestions: list[GroupSuggestion] = []
    fingerprints: set[tuple[int, tuple[tuple[str, ...], ...]]] = set()

    def add(suggestion: GroupSuggestion | None) -> None:
        if suggestion is None:
            return
        fingerprint = (suggestion.n_required or 0, tuple(tuple(unit) for unit in suggestion.selection_units))
        if fingerprint not in fingerprints:
            suggestions.append(suggestion)
            fingerprints.add(fingerprint)

    # A question-local instruction such as “Attempt only 5 questions” is scoped
    # to the nearest top-level question block, not to a hardcoded section name.
    local_instructions = list(_CHOICE_INSTRUCTION_RE.finditer(text)) + list(_SIMPLE_CHOICE_RE.finditer(text)) + list(_OPEN_CHOICE_RE.finditer(text))
    for instruction in local_instructions:
        block = _question_block(text, instruction.start())
        section_start, _ = _section_span(text, instruction.start())
        if block and (block[2] > section_start or section_start == 0):
            base, block_text, _header_start = block
            units = [[key] for key in _unit_keys_for_base(items, base)]
            n_required = _number_value(instruction.group("n"))
            explicit_m = instruction.groupdict().get("m")
            if explicit_m:
                n_available = _number_value(explicit_m)
                if n_available != len(units) and n_available < len(units):
                    units = units[:n_available]
            add(_suggestion(f"Question {base} — choose {n_required} of {len(units)}", n_required, units, instruction.group(0)))

    # A section-level instruction is bounded by whatever heading the uploaded
    # paper actually contains: Section, Part, Group, or no heading at all.
    section_instructions = list(_CHOICE_INSTRUCTION_RE.finditer(text)) + list(_OPEN_CHOICE_RE.finditer(text))
    for instruction in section_instructions:
        start, end = _section_span(text, instruction.start())
        block = _question_block(text, instruction.start())
        if block and (block[2] > start or start == 0):
            continue
        candidate_bases = _bases_after(text, instruction.end(), end)
        explicit_m = instruction.groupdict().get("m")
        expected = _number_value(explicit_m) if explicit_m else len(candidate_bases)
        if explicit_m and len(candidate_bases) >= expected:
            candidate_bases = candidate_bases[:expected]
        units = [_unit_keys_for_base(items, base) for base in candidate_bases]
        add(_suggestion(f"Choice block — choose {_number_value(instruction.group('n'))} of {len(units)}", _number_value(instruction.group("n")), units, instruction.group(0)))

    # “Either Question 3 or Question 4 should be attempted” has no count phrase,
    # so parse the two document-provided question numbers directly.
    for instruction in _EITHER_RE.finditer(text):
        bases = [instruction.group("first"), instruction.group("second")]
        start, end = _section_span(text, instruction.start())
        available = _bases_after(text, instruction.end(), end)
        if available:
            bases = [base for base in bases if base in available] or available[:2]
        units = [_unit_keys_for_base(items, base) for base in bases]
        add(_suggestion(f"Choice block — choose 1 of {len(units)}", 1, units, instruction.group(0)))

    return suggestions


def _resolve_members(items: list[dict], key: str) -> list[str]:
    if any(item["question_number"] == key for item in items):
        return [key]
    base, _ = split_base_and_part(key)
    return [item["question_number"] for item in items if split_base_and_part(item["question_number"])[0] == base]


def calculate_structure(items: list[dict], groups: list[dict], stated_total: int | None) -> StructureResult:
    raw_total = sum(int(item.get("marks_possible") or 0) for item in items)
    by_number = {item["question_number"]: item for item in items}
    assigned: set[str] = set()
    effective_total = 0
    unresolved: list[str] = []

    for group in groups:
        raw_units = group.get("selection_units") or [[key] for key in group.get("question_numbers", [])]
        unit_totals: list[int] = []
        for raw_unit in raw_units:
            members: list[str] = []
            for key in raw_unit:
                for member in _resolve_members(items, key):
                    if member not in members:
                        members.append(member)
            assigned.update(members)
            marks = [by_number[member].get("marks_possible") for member in members if by_number[member].get("marks_possible") is not None]
            if len(marks) != len(members):
                unresolved.append(f"{group.get('group_name', 'Unnamed group')} has a missing mark value.")
            unit_totals.append(sum(int(mark) for mark in marks))

        if group.get("selection_type") == "choose_n_of_m":
            n_required = int(group.get("n_required") or 0)
            if not unit_totals or not n_required or n_required > len(unit_totals):
                unresolved.append(f"{group.get('group_name', 'Unnamed group')} has an invalid choice count.")
            elif len(set(unit_totals)) != 1:
                unresolved.append(f"{group.get('group_name', 'Unnamed group')} has unequal marks per selectable question; examiner confirmation is required.")
            else:
                effective_total += n_required * unit_totals[0]
        else:
            effective_total += sum(unit_totals)

    for item in items:
        qn = item["question_number"]
        if qn not in assigned:
            effective_total += int(item.get("marks_possible") or 0)

    warning = None
    status = "resolved"
    if unresolved:
        status = "structure_review_required"
        warning = " ".join(unresolved)
    elif stated_total is not None and effective_total != stated_total:
        status = "structure_review_required"
        warning = f"Effective candidate maximum is {effective_total} marks, but the paper states {stated_total} marks. Review the optional-section structure before grading."
    elif stated_total is None:
        status = "resolved_without_stated_total"
        warning = "The paper’s stated maximum could not be detected; the effective total is based on the confirmed question structure."

    return StructureResult(raw_total, effective_total, stated_total, status, warning)


def refresh_project_structure(project, db) -> StructureResult:
    from app.db.models import QuestionBankItem, QuestionGroup

    items = db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project.id).all()
    groups = db.query(QuestionGroup).filter(QuestionGroup.project_id == project.id).all()
    item_dicts = [{"question_number": item.question_number, "marks_possible": item.marks_possible} for item in items]
    group_dicts = []
    for group in groups:
        question_numbers = json.loads(group.question_numbers_json or "[]")
        group_dicts.append({
            "group_name": group.group_name,
            "selection_type": group.selection_type,
            "question_numbers": question_numbers,
            "selection_units": json.loads(group.selection_units_json or "[]") or [[question] for question in question_numbers],
            "n_required": group.n_required,
        })
    stated_total = find_stated_total_from_project(project)
    result = calculate_structure(item_dicts, group_dicts, stated_total)
    project.question_bank_raw_total = result.raw_total
    project.question_bank_stated_total = result.stated_total
    project.question_bank_effective_total = result.effective_total
    project.question_bank_structure_status = result.status
    project.question_bank_marks_warning = result.warning if result.status == "structure_review_required" else None
    return result


def find_stated_total_from_project(project) -> int | None:
    for path in (project.question_paper_file_path, project.rubric_file_path):
        try:
            text = _paper_text(path)
        except Exception:
            continue
        match = re.search(r"(?:total|maximum)\s*marks?\s*[:\-]?\s*(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None
