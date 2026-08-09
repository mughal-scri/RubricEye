from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass

from openai import OpenAI

from app.config import settings
from app.services.template_types import DetectedRegion


STRUCTURAL_PROMPT = """You analyze a blank exam answer booklet page image.
Detect printed answer regions (boxes or ruled areas) where students write answers.
Return ONLY valid JSON:
{
  "regions": [
    {"question_number": "1", "part_label": "a", "bbox": [x1, y1, x2, y2]}
  ]
}
Coordinates must be pixel values relative to the provided image.
Do not invent identity/header areas. Focus on answer writing regions only."""


@dataclass
class VisionDerivationResult:
    pages: dict[int, list[DetectedRegion]]
    alignment_reference: dict
    confidence: str


def _encode_image(path: str) -> str:
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def _parse_regions(raw: str) -> list[DetectedRegion]:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```json", "", cleaned)
    cleaned = re.sub(r"^```", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned)
    cleaned = cleaned.strip()
    payload = json.loads(cleaned)
    regions = []
    for item in payload.get("regions", []):
        bbox = item.get("bbox", [])
        if len(bbox) != 4:
            continue
        regions.append(
            DetectedRegion(
                question_number=str(item.get("question_number", "")),
                part_label=str(item.get("part_label", "")),
                bbox=[int(v) for v in bbox],
            )
        )
    return regions


def extract_regions_with_vision(page_image_paths: list[str]) -> VisionDerivationResult:
    api_key = settings.dashscope_api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return VisionDerivationResult(pages={}, alignment_reference={}, confidence="low")

    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )

    pages: dict[int, list[DetectedRegion]] = {}
    alignment_pages: dict[str, dict] = {}

    for idx, path in enumerate(page_image_paths, start=1):
        b64 = _encode_image(path)
        response = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[
                {"role": "system", "content": STRUCTURAL_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract answer regions from this blank booklet page."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        regions = _parse_regions(raw)
        pages[idx] = regions
        alignment_pages[str(idx)] = {"width": None, "height": None, "horizontal_lines": [], "vertical_lines": []}

    confidence = "medium" if any(pages.values()) else "low"
    return VisionDerivationResult(
        pages=pages,
        alignment_reference={"pages": alignment_pages},
        confidence=confidence,
    )
