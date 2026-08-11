"""Implements the "first N attempted, ascending order" choice-question rule
(TechDoc §2.4 / §10) as a pre-API filter, using the cheap ink-density check —
no AI call is spent deciding what NOT to grade.

Ambiguous ink-density cases (see services/ink_density.py) are a genuine judgment call
the source docs leave open. This implementation treats them conservatively: they are
never auto-graded and never silently skipped — always surfaced via `flagged_ambiguous`
for a human decision — and they do NOT consume one of a choice group's N slots, so an
uncertain classification can never unfairly block a later, clearly-attempted answer
from being graded. This is a deliberate assumption, not a confirmed rule; flagged here
and in PHASE2_NOTES.md rather than picked silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services import ink_density
from app.services.question_grouping import group_question_bank_by_group, resolve_region_keys_for_question, split_base_and_part


@dataclass
class QuestionUnit:
    question_number: str
    ink_status: str
    ink_ratio: float
    image_paths: list[str]
    group_id: str | None


@dataclass
class FilteredQuestions:
    to_grade: list[QuestionUnit] = field(default_factory=list)
    skipped_blank: list[str] = field(default_factory=list)
    skipped_beyond_n: list[str] = field(default_factory=list)
    flagged_ambiguous: list[str] = field(default_factory=list)
    no_regions: list[str] = field(default_factory=list)


def _sort_key(question_number: str) -> tuple[int, str]:
    base, part = split_base_and_part(question_number)
    try:
        base_int = int(base)
    except ValueError:
        base_int = 10**9
    return (base_int, part)


def _find_region_image_paths(regions_dir: Path, region_keys: list[str]) -> list[str]:
    paths: list[str] = []
    if not regions_dir.exists():
        return paths
    for key in region_keys:
        paths.extend(str(p) for p in sorted(regions_dir.glob(f"{key}_p*.png")))
    return paths


def apply_first_n_filter(
    question_region_map: dict,
    regions_dir: Path,
    question_bank_numbers: list[str],
    question_groups: list[dict],
) -> FilteredQuestions:
    region_map_keys = list(question_region_map.keys())
    membership = group_question_bank_by_group(question_bank_numbers, question_groups)
    groups_by_id = {group["id"]: group for group in question_groups}

    units: dict[str, QuestionUnit] = {}
    for qn in question_bank_numbers:
        region_keys = resolve_region_keys_for_question(qn, region_map_keys)
        image_paths = _find_region_image_paths(regions_dir, region_keys)
        if not image_paths:
            units[qn] = QuestionUnit(qn, "no_regions", 0.0, [], membership.get(qn))
            continue
        classification = ink_density.classify_unit(image_paths)
        units[qn] = QuestionUnit(qn, classification.status, classification.ratio, image_paths, membership.get(qn))

    result = FilteredQuestions()

    # Group question_numbers by their QuestionGroup (or None = ungrouped) for processing.
    by_group: dict[str | None, list[str]] = {}
    for qn in question_bank_numbers:
        by_group.setdefault(units[qn].group_id, []).append(qn)

    for group_id, members in by_group.items():
        group = groups_by_id.get(group_id) if group_id else None
        selection_type = group["selection_type"] if group else "compulsory"
        members_sorted = sorted(members, key=_sort_key)

        if selection_type == "choose_n_of_m":
            n_required = group.get("n_required") or 0
            attempted_count = 0
            for qn in members_sorted:
                unit = units[qn]
                if unit.ink_status == "no_regions":
                    result.no_regions.append(qn)
                elif unit.ink_status == "blank":
                    result.skipped_blank.append(qn)
                elif unit.ink_status == "ambiguous":
                    result.flagged_ambiguous.append(qn)
                else:  # attempted
                    if attempted_count < n_required:
                        result.to_grade.append(unit)
                        attempted_count += 1
                    else:
                        result.skipped_beyond_n.append(qn)
        else:  # compulsory (explicit group or ungrouped default)
            for qn in members_sorted:
                unit = units[qn]
                if unit.ink_status == "no_regions":
                    result.no_regions.append(qn)
                elif unit.ink_status == "blank":
                    result.skipped_blank.append(qn)
                elif unit.ink_status == "ambiguous":
                    result.flagged_ambiguous.append(qn)
                else:  # attempted
                    result.to_grade.append(unit)

    return result
