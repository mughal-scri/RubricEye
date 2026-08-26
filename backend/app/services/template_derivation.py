from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytesseract
from pytesseract import Output

from app.services.template_types import DerivationResult, DetectedRegion
from app.services.template_vision_fallback import extract_regions_with_vision

# The label is semantic, not a fixed question list. It supports labels such as
# Q2(i), Q3(A), Question 4b, and Q12.
QUESTION_PATTERN = re.compile(
    r"\bQ(?:uestion)?\s*\.?\s*(\d+)\s*(?:\(\s*([A-Za-z]{1,8})\s*\)|([A-Za-z]{1,8}))?",
    re.IGNORECASE,
)


def _normalise_part(part: str | None) -> str:
    return (part or "").strip().strip("().").lower()


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
    return sorted(set(horizontals)), sorted(set(verticals))


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
    """Recover raster rectangles as a fallback, never inventing labels.

    This deliberately returns only geometry. A region receives a question label
    only when an OCR or PDF-text anchor can be matched to it, or when the vision
    fallback supplies one.
    """
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
    scale = min(1.6, 1800 / max(image.shape[:2]))
    ocr_image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale > 1.01 else image
    labels: list[tuple[str, str, list[int]]] = []
    seen: set[tuple[str, str]] = set()
    for config in ("--psm 6", "--psm 11"):
        try:
            data = pytesseract.image_to_data(ocr_image, config=config, output_type=Output.DICT)
        except Exception:
            continue
        n = len(data["text"])
        for i in range(n):
            text = (data["text"][i] or "").strip()
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1
            if conf < 40 or not text:
                continue
            match = QUESTION_PATTERN.search(text)
            if not match:
                continue
            q_num = match.group(1)
            part = _normalise_part(match.group(2) or match.group(3))
            key = (q_num, part)
            if key in seen:
                continue
            seen.add(key)
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            labels.append((q_num, part, [int(x / scale), int(y / scale), int((x + w) / scale), int((y + h) / scale)]))
        if labels:
            break
    return labels


def _assign_boxes_to_labels(labels: list[tuple[str, str, list[int]]], boxes: list[list[int]]) -> list[DetectedRegion]:
    regions: list[DetectedRegion] = []
    used_boxes: set[int] = set()
    for q_num, part, label_bbox in labels:
        lx, ly, _, ly2 = label_bbox
        best_idx = None
        best_score = float("inf")
        for idx, box in enumerate(boxes):
            if idx in used_boxes:
                continue
            x1, y1, x2, _ = box
            if y1 < ly2:
                continue
            horizontal_distance = 0 if x1 <= lx <= x2 else min(abs(x1 - lx), abs(x2 - lx))
            score = horizontal_distance + (y1 - ly2)
            if score < best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None:
            used_boxes.add(best_idx)
            regions.append(DetectedRegion(question_number=q_num, part_label=part, bbox=boxes[best_idx]))
    # An unmatched label is not silently assigned a made-up region.
    return regions


def _raster_page_alignment(image_path: Path) -> dict:
    image = cv2.imread(str(image_path))
    if image is None:
        return {"horizontal_lines": [], "vertical_lines": [], "width": None, "height": None}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    horizontals, verticals = _detect_lines(gray)
    return {
        "horizontal_lines": _cluster_positions(horizontals),
        "vertical_lines": _cluster_positions(verticals),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "reference_image_path": str(image_path),
    }


def _derive_page_from_raster(image_path: Path) -> tuple[list[DetectedRegion], dict]:
    image = cv2.imread(str(image_path))
    if image is None:
        return [], _raster_page_alignment(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    horizontals, verticals = _detect_lines(gray)
    boxes = _find_answer_boxes(gray, horizontals, verticals)
    labels = _ocr_question_labels(image_path)
    return _assign_boxes_to_labels(labels, boxes), {
        "horizontal_lines": _cluster_positions(horizontals),
        "vertical_lines": _cluster_positions(verticals),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
    }


def _scale_pdf_bbox(bbox: tuple[float, float, float, float], page: pymupdf.Page, image_path: Path) -> list[int]:
    image = cv2.imread(str(image_path))
    if image is None:
        return [round(value) for value in bbox]
    sx = image.shape[1] / page.rect.width
    sy = image.shape[0] / page.rect.height
    x1, y1, x2, y2 = bbox
    return [round(x1 * sx), round(y1 * sy), round(x2 * sx), round(y2 * sy)]


def _pdf_answer_rects(page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    rects: list[tuple[float, float, float, float]] = []
    page_area = page.rect.width * page.rect.height
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None:
            continue
        area = rect.width * rect.height
        if rect.width >= page.rect.width * 0.98 and rect.height >= page.rect.height * 0.98:
            continue
        if rect.width < page.rect.width * 0.35 or rect.height < page.rect.height * 0.08:
            continue
        if area < page_area * 0.03:
            continue
        rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
    return sorted(set(rects), key=lambda rect: (rect[1], rect[0]))


def _derive_page_from_pdf(page: pymupdf.Page, image_path: Path) -> list[DetectedRegion]:
    anchors: list[tuple[str, str, tuple[float, float, float, float]]] = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text, *_ = block
        match = QUESTION_PATTERN.search(" ".join(text.split()))
        if match:
            anchors.append((match.group(1), _normalise_part(match.group(2) or match.group(3)), (x0, y0, x1, y1)))
    if not anchors:
        return []

    rects = _pdf_answer_rects(page)
    regions: list[DetectedRegion] = []
    used_rects: set[int] = set()
    for index, (q_num, part, anchor) in enumerate(anchors):
        x0, y0, x1, y1 = anchor
        best_index = None
        best_score = float("inf")
        for rect_index, rect in enumerate(rects):
            if rect_index in used_rects or rect[1] < y1:
                continue
            horizontal_overlap = max(0.0, min(x1, rect[2]) - max(x0, rect[0]))
            if horizontal_overlap == 0:
                continue
            score = (rect[1] - y1) + abs(rect[0] - x0) * 0.05
            if score < best_score:
                best_score = score
                best_index = rect_index
        if best_index is not None:
            used_rects.add(best_index)
            bbox = _scale_pdf_bbox(rects[best_index], page, image_path)
        else:
            # For scanned/vector hybrids with no closed rectangle, create a
            # page-derived band bounded by neighboring semantic anchors. This is
            # computed from the input page, never from a fixed exam template.
            next_y = anchors[index + 1][2][1] if index + 1 < len(anchors) else page.rect.height * 0.94
            bbox = _scale_pdf_bbox((page.rect.width * 0.08, y1 + 8, page.rect.width * 0.92, max(y1 + 40, next_y - 8)), page, image_path)
        regions.append(DetectedRegion(question_number=q_num, part_label=part, bbox=bbox))
    return regions


def derive_template_map(page_image_paths: list[str], source_pdf_path: str | None = None) -> DerivationResult:
    """Derive semantic answer regions from the supplied booklet itself.

    A text/vector PDF is parsed directly for its own question anchors and answer
    geometry. A scanned or flattened booklet uses OCR/CV, and a low-information
    result escalates to the existing vision fallback. No question list or page
    coordinates are embedded in this function.
    """
    pages: dict[int, list[DetectedRegion]] = {}
    alignment_pages: dict[str, dict] = {}
    total_regions = 0
    pdf_anchor_regions = 0
    pdf_doc: pymupdf.Document | None = None
    if source_pdf_path:
        try:
            pdf_doc = pymupdf.open(source_pdf_path)
        except Exception:
            pdf_doc = None

    try:
        for idx, path in enumerate(page_image_paths, start=1):
            image_path = Path(path)
            alignment_pages[str(idx)] = _raster_page_alignment(image_path)
            regions: list[DetectedRegion] = []
            if pdf_doc is not None and idx <= len(pdf_doc):
                regions = _derive_page_from_pdf(pdf_doc[idx - 1], image_path)
                pdf_anchor_regions += len(regions)
            if not regions:
                regions, alignment_pages[str(idx)] = _derive_page_from_raster(image_path)
            pages[idx] = regions
            total_regions += len(regions)
    finally:
        if pdf_doc is not None:
            pdf_doc.close()

    # Empty cover/rough-work pages are normal. Trigger vision only when the
    # booklet yielded too little semantic structure overall, and send only pages
    # for which local PDF/OCR/CV derivation found no labeled region. A missing
    # PDF text layer is not itself evidence that every page needs the provider.
    flattened_booklet = source_pdf_path is not None and pdf_anchor_regions == 0
    confidence = "low" if total_regions < 2 or flattened_booklet else "high"
    used_vision_fallback = False
    pages_needing_vision = [
        page_number
        for page_number in sorted(pages)
        if not pages[page_number]
    ]
    if confidence == "low" and pages_needing_vision:
        vision_paths = [page_image_paths[page_number - 1] for page_number in pages_needing_vision]
        vision_result = extract_regions_with_vision(vision_paths)
        used_vision_fallback = True
        if vision_result.pages:
            for fallback_page_number, fallback_regions in vision_result.pages.items():
                if not (1 <= int(fallback_page_number) <= len(pages_needing_vision)):
                    continue
                page_number = pages_needing_vision[int(fallback_page_number) - 1]
                if fallback_regions:
                    pages[page_number] = fallback_regions
            fallback_pages = vision_result.alignment_reference.get("pages", {})
            for fallback_page_number, reference in fallback_pages.items():
                if not (1 <= int(fallback_page_number) <= len(pages_needing_vision)):
                    continue
                page_number = pages_needing_vision[int(fallback_page_number) - 1]
                if reference.get("width") and reference.get("height"):
                    alignment_pages[str(page_number)] = reference
            total_regions = sum(len(regions) for regions in pages.values())
            confidence = vision_result.confidence if total_regions else "low"

    return DerivationResult(
        pages=pages,
        alignment_reference={"pages": alignment_pages},
        confidence=confidence,
        used_vision_fallback=used_vision_fallback,
    )


def regions_to_json(regions: list[DetectedRegion]) -> str:
    payload = [{"question_number": region.question_number, "part_label": region.part_label, "bbox": region.bbox} for region in regions]
    return json.dumps(payload)


def regions_from_json(raw: str) -> list[DetectedRegion]:
    data = json.loads(raw or "[]")
    return [DetectedRegion(question_number=item["question_number"], part_label=item.get("part_label", ""), bbox=item["bbox"]) for item in data]
