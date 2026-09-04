from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass

import cv2
from openai import OpenAI

from app.config import settings
from app.services.template_types import DetectedRegion


STRUCTURAL_PROMPT = """You analyze ONE blank exam answer-booklet page image.

Your task is to understand the page's printed structure, not to guess a known exam
layout. Detect every printed question answer area on this page. A question answer
area is the complete space intended for that question, including a large box, a
multi-line ruled area, or an open response region. Do NOT return one region per
horizontal ruled line. Do NOT return the page header, footer, identity fields,
cover instructions, rough-work area, or decorative lines.

Read the printed question label beside or above each answer area and copy it into
question_number and part_label. Examples include Q2(i), Q3(A), Q4(B), Question 12,
and a bare Q7. Never invent sequential question numbers. If a printed answer area
has no legible question label, omit it and report low confidence for that page.

Return ONLY valid JSON in this shape:
{
  "regions": [
    {
      "question_number": "2",
      "part_label": "i",
      "bbox": [x1, y1, x2, y2],
      "confidence": "high | medium | low",
      "evidence": "printed label and surrounding answer area"
    }
  ],
  "page_confidence": "high | medium | low"
}

Coordinates must be integer pixel values relative to this exact image. The bbox
must cover the complete printed answer area, not just the first writing line.
Use the page's own visual boundaries; do not use a predetermined coordinate map."""


@dataclass
class VisionDerivationResult:
    pages: dict[int, list[DetectedRegion]]
    alignment_reference: dict
    confidence: str


def _encode_image(path: str) -> str:
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def _parse_regions(raw: str, image_width: int | None = None, image_height: int | None = None) -> list[DetectedRegion]:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```json", "", cleaned)
    cleaned = re.sub(r"^```", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned)
    cleaned = cleaned.strip()
    payload = json.loads(cleaned)
    regions: list[DetectedRegion] = []
    for item in payload.get("regions", []):
        bbox = item.get("bbox", [])
        if len(bbox) != 4:
            continue
        try:
            bbox = [int(v) for v in bbox]
        except (TypeError, ValueError):
            continue
        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            continue
        if image_width and image_height:
            x1 = max(0, min(image_width, x1)); x2 = max(0, min(image_width, x2))
            y1 = max(0, min(image_height, y1)); y2 = max(0, min(image_height, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        question_number = str(item.get("question_number", "")).strip()
        if not question_number or not re.fullmatch(r"\d+", question_number):
            continue
        regions.append(DetectedRegion(question_number=question_number, part_label=str(item.get("part_label", "")).strip().strip("().").lower(), bbox=[x1, y1, x2, y2]))
    return regions


def extract_regions_with_vision(page_image_paths: list[str]) -> VisionDerivationResult:
    api_key = settings.dashscope_api_key
    if not api_key:
        return VisionDerivationResult(pages={}, alignment_reference={}, confidence="low")

    client = OpenAI(api_key=api_key, base_url=settings.dashscope_base_url)
    pages: dict[int, list[DetectedRegion]] = {}
    alignment_pages: dict[str, dict] = {}

    for idx, path in enumerate(page_image_paths, start=1):
        b64 = _encode_image(path)
        response = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[
                {"role": "system", "content": STRUCTURAL_PROMPT},
                {"role": "user", "content": [{"type": "text", "text": "Understand this booklet page and return its complete semantic answer areas."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        image = cv2.imread(path)
        height, width = image.shape[:2] if image is not None else (None, None)
        regions = _parse_regions(raw, width, height)
        pages[idx] = regions
        alignment_pages[str(idx)] = {"width": width, "height": height, "horizontal_lines": [], "vertical_lines": [], "reference_image_path": path}

    confidence = "medium" if any(pages.values()) else "low"
    return VisionDerivationResult(pages=pages, alignment_reference={"pages": alignment_pages}, confidence=confidence)
