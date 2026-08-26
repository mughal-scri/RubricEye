#!/usr/bin/env python3
"""Verify template-map edits fail closed before confirmation or persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from fastapi import HTTPException

from app.routes.template_map import _RegionValidationPayload, _validate_regions


def _page(path: Path):
    return SimpleNamespace(page_number=1, page_image_path=str(path))


def _assert_422(regions, pages, fragment: str, *, require_any: bool = False):
    try:
        _validate_regions(regions, pages, require_any=require_any)
    except HTTPException as exc:
        assert exc.status_code == 422, exc
        assert fragment in str(exc.detail), exc.detail
    else:
        raise AssertionError(f"Expected 422 containing {fragment!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rubriceye_template_validation_") as directory:
        image_path = Path(directory) / "page.png"
        Image.new("RGB", (100, 100), "white").save(image_path)
        pages = {1: _page(image_path)}

        _assert_422([], pages, "At least one mapped", require_any=True)
        _assert_422([_RegionValidationPayload(1, "", "", [1, 1, 10, 10])], pages, "without a question label")
        _assert_422([_RegionValidationPayload(1, "1", "", [10, 10, 10, 20])], pages, "invalid bbox")
        _assert_422([_RegionValidationPayload(1, "1", "", [1, 1, 101, 20])], pages, "outside the page image")
        duplicate = [
            _RegionValidationPayload(1, "1", "i", [1, 1, 20, 20]),
            _RegionValidationPayload(1, "1", "i", [25, 25, 40, 40]),
        ]
        _assert_422(duplicate, pages, "Duplicate region identity")
        aliases = [
            _RegionValidationPayload(1, "Q2(i)", "", [1, 1, 20, 20]),
            _RegionValidationPayload(1, "2", "i", [25, 25, 40, 40]),
        ]
        _assert_422(aliases, pages, "Duplicate region identity")
        normalized = _validate_regions([_RegionValidationPayload(1, "Question 3(a)", "", [1, 1, 20, 20])], pages, require_any=True)
        assert normalized[1][0]["question_number"] == "3" and normalized[1][0]["part_label"] == "a", normalized

    print("Template-map validation regression passed: empty confirmation, unlabeled, invalid, out-of-bounds, and duplicate regions are rejected with 422.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
