from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from app.services.alignment import compute_alignment_matrix, transform_bbox
from app.services.storage import atomic_write_bytes


def _question_key(question_number: str, part_label: str) -> str:
    if part_label:
        return f"{question_number}{part_label}"
    return question_number


def _clamp_bbox(bbox: list[int], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    return [max(0, min(width, x1)), max(0, min(height, y1)), max(0, min(width, x2)), max(0, min(height, y2))]


def _expand_bbox(bbox: list[int], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    padding = max(24, int(min(width, height) * 0.025))
    return _clamp_bbox([x1 - padding, y1 - padding, x2 + padding, y2 + padding], width, height)


def _ink_mask(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Printed rules are thin and low-contrast; this threshold prioritizes the
    # darker student strokes while keeping the method independent of pen color.
    return cv2.threshold(gray, 175, 255, cv2.THRESH_BINARY_INV)[1]


def _has_overflow(image: np.ndarray, nominal: list[int], expanded: list[int]) -> bool:
    x1, y1, x2, y2 = nominal
    ex1, ey1, ex2, ey2 = expanded
    if ex2 <= ex1 or ey2 <= ey1:
        return False
    mask = _ink_mask(image)
    outer = mask[ey1:ey2, ex1:ex2]
    if outer.size == 0:
        return False
    # Inspect only the padding ring, so ink inside the assigned region does
    # not become an overflow warning. A small ring threshold avoids reacting to
    # anti-aliased page borders or a few scanner specks.
    ring = outer.copy()
    ix1, iy1 = max(0, x1 - ex1), max(0, y1 - ey1)
    ix2, iy2 = min(ring.shape[1], x2 - ex1), min(ring.shape[0], y2 - ey1)
    if ix2 > ix1 and iy2 > iy1:
        ring[iy1:iy2, ix1:ix2] = 0
    return float(np.count_nonzero(ring)) / max(1, ring.size) > 0.0015


def build_question_region_map(
    page_image_paths: list[str],
    template_map_pages: list[dict],
    alignment_reference: dict,
    regions_output_dir: Path,
    skip_page_indices: set[int] | None = None,
) -> tuple[dict[str, list[dict]], dict[str, list[str]]]:
    question_region_map: dict[str, list[dict]] = {}
    region_preview_urls: dict[str, list[str]] = {}
    regions_output_dir.mkdir(parents=True, exist_ok=True)
    skip_page_indices = skip_page_indices or set()
    page_lookup = {page["page_number"]: page for page in template_map_pages}

    for page_index, scan_path in enumerate(page_image_paths):
        if page_index in skip_page_indices:
            continue
        page_number = page_index + 1
        page_data = page_lookup.get(page_number)
        if not page_data:
            continue
        matrix = compute_alignment_matrix(scan_path, alignment_reference, page_number)
        image = cv2.imread(scan_path)
        if image is None:
            continue
        if matrix is None:
            matrix = np.identity(3, dtype=np.float64)

        for region in page_data.get("regions", []):
            q_num = region["question_number"]
            part = region.get("part_label", "")
            key = _question_key(q_num, part)
            nominal_bbox = _clamp_bbox(transform_bbox(region["bbox"], matrix), image.shape[1], image.shape[0])
            if nominal_bbox[2] <= nominal_bbox[0] or nominal_bbox[3] <= nominal_bbox[1]:
                continue
            expanded_bbox = _expand_bbox(nominal_bbox, image.shape[1], image.shape[0])
            x1, y1, x2, y2 = expanded_bbox
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            preview_name = f"{key}_p{page_number}.png"
            preview_path = regions_output_dir / preview_name
            atomic_write_bytes(preview_path, cv2.imencode(".png", crop)[1].tobytes())
            question_region_map.setdefault(key, []).append(
                {
                    "page_index": page_index,
                    "bbox": expanded_bbox,
                    "nominal_bbox": nominal_bbox,
                    "overflow_detected": _has_overflow(image, nominal_bbox, expanded_bbox),
                }
            )
            region_preview_urls.setdefault(key, []).append(str(preview_path))

    return question_region_map, region_preview_urls


def load_template_map_pages(project_dir: Path) -> list[dict]:
    path = project_dir / "template_map.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("pages", [])
