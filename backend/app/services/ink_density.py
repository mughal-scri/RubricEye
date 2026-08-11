"""Cheap, non-AI pre-filter to classify a cropped region as blank/attempted/ambiguous.

Used before any Qwen-VL call so genuinely blank regions never get sent to the API
(TechDoc §2.4 / §7 cost optimization), and so borderline cases are flagged for human
review instead of silently guessed either way.

Deviates slightly from the Phase 2 plan's literal signature
`is_blank_region(path, threshold) -> tuple[bool, float]`: a two-way bool can't express
the required third "ambiguous" state described in the same plan paragraph, so this
returns a 3-way status string instead. Functionally a superset — `status == "blank"`
recovers the boolean case exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.config import settings

# Pixels darker than this (0-255 grayscale) are counted as "ink". 200 is a generous
# threshold that catches pencil/light pen strokes without picking up paper shadow/noise.
DARK_PIXEL_VALUE = 200

IinkStatus = str  # "blank" | "attempted" | "ambiguous"


@dataclass
class InkDensityResult:
    status: str
    ratio: float


def measure_ink_density(image_path: str) -> float:
    """Returns the fraction of dark (ink-like) pixels in the image, 0.0-1.0."""
    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None or gray.size == 0:
        return 0.0
    dark_mask = gray < DARK_PIXEL_VALUE
    return float(np.count_nonzero(dark_mask)) / float(gray.size)


def classify_region(
    image_path: str,
    blank_threshold: float | None = None,
    ambiguous_threshold: float | None = None,
) -> InkDensityResult:
    blank_threshold = blank_threshold if blank_threshold is not None else settings.ink_density_blank_threshold
    ambiguous_threshold = (
        ambiguous_threshold if ambiguous_threshold is not None else settings.ink_density_ambiguous_threshold
    )
    ratio = measure_ink_density(image_path)
    if ratio < blank_threshold:
        status = "blank"
    elif ratio < ambiguous_threshold:
        status = "ambiguous"
    else:
        status = "attempted"
    return InkDensityResult(status=status, ratio=ratio)


def classify_unit(
    image_paths: list[str],
    blank_threshold: float | None = None,
    ambiguous_threshold: float | None = None,
) -> InkDensityResult:
    """Classifies a gradable unit that may span several region-crop images
    (multiple parts and/or multiple pages). Any single crop showing real content
    is enough to call the whole unit "attempted" — a student's answer to one
    sub-part shouldn't be masked by a blank neighboring crop.
    """
    if not image_paths:
        return InkDensityResult(status="blank", ratio=0.0)

    results = [classify_region(path, blank_threshold, ambiguous_threshold) for path in image_paths]
    if any(r.status == "attempted" for r in results):
        best = max(results, key=lambda r: r.ratio)
        return InkDensityResult(status="attempted", ratio=best.ratio)
    if any(r.status == "ambiguous" for r in results):
        best = max(results, key=lambda r: r.ratio)
        return InkDensityResult(status="ambiguous", ratio=best.ratio)
    return InkDensityResult(status="blank", ratio=max((r.ratio for r in results), default=0.0))
