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

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.config import settings

# Pixels darker than this (0-255 grayscale) are counted as "ink". 200 is a generous
# threshold that catches pencil/light pen strokes without picking up paper shadow/noise.
DARK_PIXEL_VALUE = 200

# Segmentation writes each region's blank-template crop next to the scan crop as
# "<key>__baseline_p<N>.png". The trailing "__baseline" keeps it outside the
# "{key}_p*.png" glob that first_n_filter uses to collect gradable crops.
_BASELINE_NAME_RE = re.compile(r"^(?P<stem>.+)_p(?P<page>\d+)\.png$")

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


def _baseline_image_path(image_path: str) -> Path | None:
    """Return the blank-template sibling crop for a scan crop, if it exists.

    Args:
        image_path: path to a scan crop named "<key>_p<N>.png".

    Returns:
        Path to "<key>__baseline_p<N>.png" when that sibling exists, else None.
    """
    path = Path(image_path)
    match = _BASELINE_NAME_RE.match(path.name)
    if not match:
        return None
    candidate = path.with_name(f"{match.group('stem')}__baseline_p{match.group('page')}.png")
    return candidate if candidate.exists() else None


def classify_region(
    image_path: str,
    blank_threshold: float | None = None,
    ambiguous_threshold: float | None = None,
) -> InkDensityResult:
    """Classify one region crop as blank/ambiguous/attempted.

    When segmentation wrote a blank-template baseline sibling for the crop, a
    dark-pixel ratio within ``ink_density_excess_tolerance`` of that baseline is
    blank: the printed rules and labels dominate the ratio, so an absolute
    threshold alone misreads every empty answer box as "ambiguous" and lets it
    consume a choice slot.

    Args:
        image_path: path to the scan crop.
        blank_threshold: override for settings.ink_density_blank_threshold.
        ambiguous_threshold: override for settings.ink_density_ambiguous_threshold.

    Returns:
        InkDensityResult with status "blank" | "ambiguous" | "attempted" and the
        scan crop's raw dark-pixel ratio.
    """
    blank_threshold = blank_threshold if blank_threshold is not None else settings.ink_density_blank_threshold
    ambiguous_threshold = (
        ambiguous_threshold if ambiguous_threshold is not None else settings.ink_density_ambiguous_threshold
    )
    ratio = measure_ink_density(image_path)
    baseline_path = _baseline_image_path(image_path)
    if baseline_path is not None:
        baseline_ratio = measure_ink_density(str(baseline_path))
        if ratio - baseline_ratio < settings.ink_density_excess_tolerance:
            return InkDensityResult(status="blank", ratio=ratio)
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
