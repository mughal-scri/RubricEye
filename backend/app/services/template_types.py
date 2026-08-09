from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DetectedRegion:
    question_number: str
    part_label: str
    bbox: list[int]


@dataclass
class DerivationResult:
    pages: dict[int, list[DetectedRegion]]
    alignment_reference: dict
    confidence: str
    used_vision_fallback: bool
