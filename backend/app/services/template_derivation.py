from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from pytesseract import Output

from app.services.template_types import DerivationResult, DetectedRegion
from app.services.template_vision_fallback import extract_regions_with_vision


QUESTION_PATTERN = re.compile(
    r"(?:Q(?:uestion)?\.?\s*)?(\d+)\s*([a-z])?",
    re.IGNORECASE,
)


def _detect_lines(gray: np.ndarray) -> tuple[list[int], list[int]]:
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=80, maxLineGap=10)
    horizontals: list[int] = []
    verticals: list[int] = []
    if lines is not None:
        for line in lines.reshape(-1, 4):
            x1, y1, x2, y2 = line
            if abs(y2 - y1) < 8:
                horizontals.append(int((y1 + y2) / 2))
            elif abs(x2 - x1) < 8:
                verticals.append(int((x1 + x2) / 2))
    horizontals = sorted(set(horizontals))
    verticals = sorted(set(verticals))
    return horizontals, verticals


def _cluster_positions(values: list[int], tolerance: int = 12) -> list[int]:
    if not values:
        return []
    clusters: list[list[int]] = [[values[0]]]
    for value in values[1:]:
        if abs(value - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [int(sum(cluster) / len(cluster)) for cluster in clusters]


def _find_answer_boxes(gray: np.ndarray, horizontals: list[int], verticals: list[int]) -> list[list[int]]:
    height, width = gray.shape
    boxes: list[list[int]] = []
    hs = _cluster_positions(horizontals)
    vs = _cluster_positions(verticals)
    if len(hs) < 2 or len(vs) < 2:
        return boxes
    for i in range(len(hs) - 1):
        for j in range(len(vs) - 1):
            y1, y2 = hs[i], hs[i + 1]
            x1, x2 = vs[j], vs[j + 1]
            if (y2 - y1) < 40 or (x2 - x1) < 80:
                continue
            if (y2 - y1) > height * 0.45 or (x2 - x1) > width * 0.95:
                continue
            boxes.append([x1, y1, x2, y2])
    return boxes


def _ocr_question_labels(image_path: Path) -> list[tuple[str, str, list[int]]]:
    image = cv2.imread(str(image_path))
    if image is None:
        return []
    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
    except Exception:
        return []
    labels: list[tuple[str, str, list[int]]] = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf = int(float(data["conf"][i])) if data["conf"][i] != "-1" else -1
        if conf < 40 or not text:
            continue
        match = QUESTION_PATTERN.search(text)
        if not match:
            continue
        q_num = match.group(1)
        part = (match.group(2) or "").lower()
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        labels.append((q_num, part, [x, y, x + w, y + h]))
    return labels


def _assign_boxes_to_labels(
    labels: list[tuple[str, str, list[int]]],
    boxes: list[list[int]],
) -> list[DetectedRegion]:
    regions: list[DetectedRegion] = []
    used_boxes: set[int] = set()
    for q_num, part, label_bbox in labels:
        lx, ly, _, ly2 = label_bbox
        best_idx = None
        best_score = float("inf")
        for idx, box in enumerate(boxes):
            if idx in used_boxes:
                continue
            x1, y1, x2, y2 = box
            if y1 < ly2:
                continue
            score = abs(x1 - lx) + (y1 - ly2)
            if score < best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None:
            used_boxes.add(best_idx)
            regions.append(
                DetectedRegion(
                    question_number=q_num,
                    part_label=part,
                    bbox=boxes[best_idx],
                )
            )
    if not regions and boxes:
        for idx, box in enumerate(boxes[:12]):
            regions.append(
                DetectedRegion(
                    question_number=str(idx + 1),
                    part_label="",
                    bbox=box,
                )
            )
    return regions


def _derive_page(image_path: Path) -> tuple[list[DetectedRegion], dict]:
    image = cv2.imread(str(image_path))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    horizontals, verticals = _detect_lines(gray)
    boxes = _find_answer_boxes(gray, horizontals, verticals)
    labels = _ocr_question_labels(image_path)
    regions = _assign_boxes_to_labels(labels, boxes)
    alignment = {
        "horizontal_lines": _cluster_positions(horizontals),
        "vertical_lines": _cluster_positions(verticals),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
    }
    return regions, alignment


def derive_template_map(page_image_paths: list[str]) -> DerivationResult:
    pages: dict[int, list[DetectedRegion]] = {}
    alignment_pages: dict[str, dict] = {}
    total_regions = 0
    low_confidence = False

    for idx, path in enumerate(page_image_paths, start=1):
        regions, alignment = _derive_page(Path(path))
        pages[idx] = regions
        alignment_pages[str(idx)] = alignment
        total_regions += len(regions)
        if len(regions) == 0:
            low_confidence = True

    confidence = "low" if low_confidence or total_regions < 2 else "high"
    used_vision_fallback = False

    if confidence == "low":
        vision_result = extract_regions_with_vision(page_image_paths)
        if vision_result.pages:
            pages = vision_result.pages
            alignment_pages = vision_result.alignment_reference.get("pages", alignment_pages)
            confidence = vision_result.confidence
            used_vision_fallback = True

    return DerivationResult(
        pages=pages,
        alignment_reference={"pages": alignment_pages},
        confidence=confidence,
        used_vision_fallback=used_vision_fallback,
    )


def regions_to_json(regions: list[DetectedRegion]) -> str:
    payload = [
        {
            "question_number": region.question_number,
            "part_label": region.part_label,
            "bbox": region.bbox,
        }
        for region in regions
    ]
    return json.dumps(payload)


def regions_from_json(raw: str) -> list[DetectedRegion]:
    data = json.loads(raw or "[]")
    return [
        DetectedRegion(
            question_number=item["question_number"],
            part_label=item.get("part_label", ""),
            bbox=item["bbox"],
        )
        for item in data
    ]
