#!/usr/bin/env python3
"""Verify template derivation only escalates when local evidence is insufficient."""

from __future__ import annotations

from unittest.mock import patch

from app.services.template_derivation import derive_template_map
from app.services.template_types import DetectedRegion
from app.services.template_vision_fallback import VisionDerivationResult


LOCAL_REGIONS = [
    DetectedRegion(question_number="1", part_label="", bbox=[10, 20, 200, 180]),
    DetectedRegion(question_number="2", part_label="", bbox=[10, 220, 200, 380]),
]


def _fake_fallback(_page_image_paths):
    _fake_fallback.calls += 1
    return VisionDerivationResult(pages={}, alignment_reference={}, confidence="low")


_fake_fallback.calls = 0


def main() -> int:
    with patch("app.services.template_derivation._raster_page_alignment", return_value={}), patch(
        "app.services.template_derivation.extract_regions_with_vision", side_effect=_fake_fallback
    ), patch("app.services.template_derivation._derive_page_from_raster", return_value=(LOCAL_REGIONS, {})):
        local_result = derive_template_map(["synthetic-page.png"])
    assert local_result.confidence == "high", local_result
    assert not local_result.used_vision_fallback, local_result
    assert _fake_fallback.calls == 0, _fake_fallback.calls

    with patch("app.services.template_derivation._raster_page_alignment", return_value={}), patch(
        "app.services.template_derivation.extract_regions_with_vision", side_effect=_fake_fallback
    ), patch("app.services.template_derivation._derive_page_from_raster", return_value=([], {})):
        weak_result = derive_template_map(["synthetic-page.png"])
    assert weak_result.used_vision_fallback, weak_result
    assert _fake_fallback.calls == 1, _fake_fallback.calls

    print("Template derivation escalation regression passed: strong local evidence made zero fallback calls; weak evidence used the existing fallback seam once.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
