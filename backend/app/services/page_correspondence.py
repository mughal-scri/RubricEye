from __future__ import annotations

from pathlib import Path

from app.services.question_grouping import canonical_question_label, split_base_and_part
from app.services.template_derivation import _ocr_question_labels


def page_region_key(question_number: str, part_label: str = "") -> str:
    return canonical_question_label(f"{question_number}{part_label}")


def expected_page_labels(template_page: dict) -> set[str]:
    return {
        page_region_key(str(region.get("question_number", "")), str(region.get("part_label", "")))
        for region in template_page.get("regions", [])
        if str(region.get("question_number", "")).strip()
    }


def detected_page_labels(image_path: str | Path) -> set[str]:
    return {
        page_region_key(question_number, part_label)
        for question_number, part_label, _bbox in _ocr_question_labels(Path(image_path))
    }


def compare_page_labels(template_page: dict, image_path: str | Path) -> tuple[str, set[str], set[str]]:
    """Return ``match``, ``mismatch``, or ``uncertain`` for one answer page."""
    expected = expected_page_labels(template_page)
    detected = detected_page_labels(image_path)
    if not expected or not detected:
        return "uncertain", expected, detected
    if expected.intersection(detected):
        return "match", expected, detected
    expected_parts = {label for label in expected if split_base_and_part(label)[1]}
    detected_parts = {label for label in detected if split_base_and_part(label)[1]}
    if expected_parts and detected_parts and not expected_parts.intersection(detected_parts):
        return "mismatch", expected, detected
    return "uncertain", expected, detected
