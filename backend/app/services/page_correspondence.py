from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from app.services.question_grouping import canonical_question_label, split_base_and_part
from app.services.template_derivation import QUESTION_PATTERN, _normalise_part, _ocr_question_labels


def page_region_key(question_number: str, part_label: str = "") -> str:
    return canonical_question_label(f"{question_number}{part_label}")


def expected_page_labels(template_page: dict) -> set[str]:
    return {
        page_region_key(str(region.get("question_number", "")), str(region.get("part_label", "")))
        for region in template_page.get("regions", [])
        if str(region.get("question_number", "")).strip()
    }


def detected_page_labels(image_path: str | Path) -> set[str]:
    path = Path(image_path)
    labels: set[str] = set()

    pdf_path = path.parent / "original.pdf"
    if pdf_path.exists():
        match_idx = re.search(r"page_(\d+)\.png$", path.name)
        if match_idx:
            page_idx = int(match_idx.group(1)) - 1
            try:
                doc = pymupdf.open(pdf_path)
                if 0 <= page_idx < len(doc):
                    page_text = doc[page_idx].get_text("text")
                    for match in QUESTION_PATTERN.finditer(" ".join(page_text.split())):
                        q_num = match.group(1)
                        part = _normalise_part(match.group(2) or match.group(3))
                        labels.add(page_region_key(q_num, part))
                doc.close()
            except Exception:
                pass

    if not labels:
        labels = {
            page_region_key(question_number, part_label)
            for question_number, part_label, _bbox in _ocr_question_labels(path)
        }

    return labels


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
