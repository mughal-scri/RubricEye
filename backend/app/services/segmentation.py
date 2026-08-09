from __future__ import annotations

import json
from pathlib import Path

import cv2

from app.services.alignment import compute_alignment_matrix, transform_bbox
from app.services.storage import atomic_write_bytes


def _question_key(question_number: str, part_label: str) -> str:
    if part_label:
        return f"{question_number}{part_label}"
    return question_number


def build_question_region_map(
    page_image_paths: list[str],
    template_map_pages: list[dict],
    alignment_reference: dict,
    regions_output_dir: Path,
) -> tuple[dict[str, list[dict]], dict[str, list[str]]]:
    question_region_map: dict[str, list[dict]] = {}
    region_preview_urls: dict[str, list[str]] = {}
    regions_output_dir.mkdir(parents=True, exist_ok=True)

    page_lookup = {page["page_number"]: page for page in template_map_pages}

    for page_index, scan_path in enumerate(page_image_paths):
        page_number = page_index + 1
        page_data = page_lookup.get(page_number)
        if not page_data:
            continue
        matrix = compute_alignment_matrix(scan_path, alignment_reference, page_number)
        if matrix is None:
            import numpy as np

            matrix = np.identity(3, dtype=np.float64)
        image = cv2.imread(scan_path)
        if image is None:
            continue

        for region in page_data.get("regions", []):
            q_num = region["question_number"]
            part = region.get("part_label", "")
            key = _question_key(q_num, part)
            bbox = transform_bbox(region["bbox"], matrix)
            x1, y1, x2, y2 = bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = image[y1:y2, x1:x2]
            preview_name = f"{key}_p{page_number}.png"
            preview_path = regions_output_dir / preview_name
            atomic_write_bytes(preview_path, cv2.imencode(".png", crop)[1].tobytes())
            question_region_map.setdefault(key, []).append({"page_index": page_index, "bbox": [x1, y1, x2, y2]})
            region_preview_urls.setdefault(key, []).append(str(preview_path))

    return question_region_map, region_preview_urls


def load_template_map_pages(project_dir: Path) -> list[dict]:
    path = project_dir / "template_map.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("pages", [])
