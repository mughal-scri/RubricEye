#!/usr/bin/env python3
"""Verify template derivation only escalates when local evidence is insufficient."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image

from app.services.template_derivation import derive_template_map
from app.services.template_types import DetectedRegion
from app.services.template_vision_fallback import VisionDerivationResult


LOCAL_REGIONS = [
    DetectedRegion(question_number="1", part_label="", bbox=[10, 20, 200, 180]),
    DetectedRegion(question_number="2", part_label="", bbox=[10, 220, 200, 380]),
]
ONE_LOCAL_REGION = [LOCAL_REGIONS[0]]


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

    with tempfile.TemporaryDirectory(prefix="rubriceye_flattened_template_") as directory:
        root = Path(directory)
        image_path = root / "page.png"
        Image.new("RGB", (400, 600), "white").save(image_path)
        source_pdf = root / "flattened.pdf"
        document = pymupdf.open()
        page = document.new_page(width=400, height=600)
        page.insert_image(page.rect, filename=str(image_path))
        document.save(source_pdf)
        document.close()
        _fake_fallback.calls = 0
        with patch("app.services.template_derivation._derive_page_from_raster", return_value=(LOCAL_REGIONS, {})), patch(
            "app.services.template_derivation.extract_regions_with_vision", side_effect=_fake_fallback
        ):
            flattened_result = derive_template_map([str(image_path)], source_pdf_path=str(source_pdf))
        assert sum(len(regions) for regions in flattened_result.pages.values()) == len(LOCAL_REGIONS), flattened_result
        assert not flattened_result.used_vision_fallback, flattened_result
        assert _fake_fallback.calls == 0, _fake_fallback.calls

    remapped_calls: list[list[str]] = []
    remapped_region = DetectedRegion(question_number="9", part_label="", bbox=[5, 5, 50, 50])

    def remapped_fallback(paths: list[str]):
        remapped_calls.append(paths)
        return VisionDerivationResult(
            pages={1: [remapped_region]},
            alignment_reference={"pages": {"1": {"width": 400, "height": 600}}},
            confidence="medium",
        )

    with patch("app.services.template_derivation._raster_page_alignment", return_value={}), patch(
        "app.services.template_derivation._derive_page_from_raster", side_effect=[(ONE_LOCAL_REGION, {}), ([], {})]
    ), patch("app.services.template_derivation.extract_regions_with_vision", side_effect=remapped_fallback):
        remapped_result = derive_template_map(["page-1.png", "page-2.png"])
    assert remapped_calls == [["page-2.png"]], remapped_calls
    assert remapped_result.pages[1] == ONE_LOCAL_REGION, remapped_result.pages
    assert remapped_result.pages[2] == [remapped_region], remapped_result.pages

    print("Template derivation escalation regression passed: strong local evidence made zero fallback calls, including a flattened source PDF; weak evidence used the existing fallback seam once; subset results remapped correctly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
