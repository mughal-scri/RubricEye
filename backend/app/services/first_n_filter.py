"""Cheap, non-AI pre-filter for answer units.

The filter runs before any model call. It classifies local crop evidence as blank,
ambiguous, or attempted. Choice groups may define compound units such as ["3a",
"3b"], which count as one selectable question and are graded together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services import ink_density
from app.services.question_grouping import build_part_sort_key, group_question_bank_by_group, resolve_region_keys_for_question, split_base_and_part
from app.services.segmentation import safe_region_filename_key


@dataclass
class QuestionUnit:
    question_number: str
    ink_status: str
    ink_ratio: float
    image_paths: list[str]
    group_id: str | None
    compound_batch_id: str | None = None
    compound_image_paths: list[str] | None = None


@dataclass
class FilteredQuestions:
    to_grade: list[QuestionUnit] = field(default_factory=list)
    skipped_blank: list[str] = field(default_factory=list)
    skipped_beyond_n: list[str] = field(default_factory=list)
    flagged_ambiguous: list[str] = field(default_factory=list)
    no_regions: list[str] = field(default_factory=list)


def _sort_members(members: list[str]) -> list[str]:
    split = [split_base_and_part(m) for m in members]
    sibling_parts = [part for _, part in split]
    part_key_fn = build_part_sort_key(sibling_parts)

    def key(question_number: str) -> tuple:
        base, part = split_base_and_part(question_number)
        try:
            base_int = int(base)
        except ValueError:
            base_int = 10**9
        return (base_int,) + part_key_fn(part)

    return sorted(members, key=key)


def _find_region_image_paths(regions_dir: Path, region_keys: list[str]) -> list[str]:
    paths: list[str] = []
    if not regions_dir.exists():
        return paths
    for key in region_keys:
        paths.extend(str(path) for path in sorted(regions_dir.glob(f"{safe_region_filename_key(key)}_p*.png")))
    return paths


def _resolve_group_unit(raw_unit: list[str], members: list[str]) -> list[str]:
    resolved: list[str] = []
    for key in raw_unit:
        if key in members:
            candidates = [key]
        else:
            base, _ = split_base_and_part(key)
            candidates = [member for member in members if split_base_and_part(member)[0] == base]
        for candidate in candidates:
            if candidate not in resolved:
                resolved.append(candidate)
    return _sort_members(resolved)


def _classify_unit(question_numbers: list[str], units: dict[str, QuestionUnit]) -> tuple[str, float, list[str]]:
    image_paths = [path for number in question_numbers for path in units[number].image_paths]
    if any(units[number].ink_status == "no_regions" for number in question_numbers) and not image_paths:
        return "no_regions", 0.0, image_paths
    if any(units[number].ink_status == "attempted" for number in question_numbers):
        return "attempted", max(units[number].ink_ratio for number in question_numbers), image_paths
    if any(units[number].ink_status == "ambiguous" for number in question_numbers):
        return "ambiguous", max(units[number].ink_ratio for number in question_numbers), image_paths
    if any(units[number].ink_status == "no_regions" for number in question_numbers):
        return "ambiguous", max(units[number].ink_ratio for number in question_numbers), image_paths
    return "blank", max((units[number].ink_ratio for number in question_numbers), default=0.0), image_paths


def apply_first_n_filter(question_region_map: dict, regions_dir: Path, question_bank_numbers: list[str], question_groups: list[dict]) -> FilteredQuestions:
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
    by_group: dict[str | None, list[str]] = {}
    for qn in question_bank_numbers:
        by_group.setdefault(units[qn].group_id, []).append(qn)

    for group_id, members in by_group.items():
        group = groups_by_id.get(group_id) if group_id else None
        members_sorted = _sort_members(members)
        if not group or group.get("selection_type") != "choose_n_of_m":
            for qn in members_sorted:
                status = units[qn].ink_status
                if status == "no_regions":
                    result.no_regions.append(qn)
                elif status == "blank":
                    result.skipped_blank.append(qn)
                elif status == "ambiguous":
                    result.flagged_ambiguous.append(qn)
                else:
                    result.to_grade.append(units[qn])
            continue

        raw_units = group.get("selection_units") or [[qn] for qn in members_sorted]
        selectable_units = [_resolve_group_unit(raw_unit, members_sorted) for raw_unit in raw_units]
        selectable_units = [unit for unit in selectable_units if unit]
        n_required = int(group.get("n_required") or 0)

        # Classify every selectable unit up front so slot allocation is ordered
        # by evidence strength, not by unit order: attempted units claim choice
        # slots first and ambiguous units only fill leftover slots. Allocating
        # slots in unit order instead lets a noisy blank box that misclassifies
        # as ambiguous consume a slot ahead of a genuinely attempted unit,
        # inverting the selection (real attempt closed as beyond-N, blank box
        # opened for examiner review).
        classified_units = [
            (unit_numbers, *_classify_unit(unit_numbers, units))
            for unit_numbers in selectable_units
        ]

        selected_indexes: set[int] = set()
        slots_left = n_required
        for index, (_numbers, status, _ratio, _paths) in enumerate(classified_units):
            if status == "attempted" and slots_left > 0:
                selected_indexes.add(index)
                slots_left -= 1
        for index, (_numbers, status, _ratio, _paths) in enumerate(classified_units):
            if status == "ambiguous" and slots_left > 0:
                selected_indexes.add(index)
                slots_left -= 1

        for index, (unit_numbers, status, ratio, image_paths) in enumerate(classified_units):
            if status == "no_regions":
                result.no_regions.extend(unit_numbers)
            elif status == "blank":
                result.skipped_blank.extend(unit_numbers)
            elif index in selected_indexes:
                if status == "ambiguous":
                    # Ambiguous ink still means "the student probably wrote
                    # something": it occupies a leftover slot and goes to
                    # examiner review instead of the VL model (saves cost and
                    # avoids unreliable classification).
                    result.flagged_ambiguous.extend(unit_numbers)
                else:
                    compound_batch_id = f"{group_id}:{index}" if len(unit_numbers) > 1 else None
                    for number in unit_numbers:
                        # Keep each member's own evidence for traceability, while the
                        # compound collection gives the grader one authoritative union
                        # of every part's images for the single shared model call.
                        result.to_grade.append(
                            QuestionUnit(
                                number,
                                "attempted",
                                ratio,
                                list(units[number].image_paths),
                                group_id,
                                compound_batch_id,
                                list(image_paths) if compound_batch_id else None,
                            )
                        )
            else:
                result.skipped_beyond_n.extend(unit_numbers)

    return result
