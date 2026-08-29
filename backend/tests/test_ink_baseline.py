"""Regression guards for baseline-aware ink classification.

Printed answer boxes (ruled lines, borders, labels) alone measure above the
absolute blank threshold: on the real mock-exam booklet every empty box reads
~0.022-0.024 dark-pixel ratio against a 0.02 blank threshold. Without a
blank-template baseline to compare against, each empty box classified as
"ambiguous", consumed a choice slot, and pushed genuinely attempted later
items into skipped_beyond_n — the "wrong questions graded" failure where a
student attempting 2i,2ii,2iii,2vi,2vii got graded on the fixed 2i-2v subset.

These tests pin the differential rule: a region is blank when its dark-pixel
ratio exceeds the blank-template baseline by less than
settings.ink_density_excess_tolerance.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.config import settings
from app.services.ink_density import classify_region
from app.services.segmentation import build_question_region_map, safe_region_filename_key


def _printed_box_page(width: int = 400, height: int = 600, bbox: tuple[int, int, int, int] = (100, 100, 300, 400)) -> np.ndarray:
    """Render a synthetic answer-box page: border plus faint ruled lines.

    Args:
        width: page width in pixels.
        height: page height in pixels.
        bbox: answer-box rectangle (x1, y1, x2, y2).

    Returns:
        BGR image containing only printed content (no student ink).
    """
    page = np.full((height, width, 3), 255, dtype=np.uint8)
    x1, y1, x2, y2 = bbox
    cv2.rectangle(page, (x1, y1), (x2, y2), (100, 100, 100), thickness=1)
    for row in np.linspace(y1 + 20, y2 - 20, 8):
        cv2.line(page, (x1 + 5, int(row)), (x2 - 5, int(row)), (160, 160, 160), thickness=1)
    return page


def _assert_ratio_in_ambiguous_band(image_path: Path) -> float:
    """Guard the test premise: printed content alone must land in the ambiguous band."""
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    ratio = float(np.count_nonzero(gray < 200)) / float(gray.size)
    assert settings.ink_density_blank_threshold <= ratio < settings.ink_density_ambiguous_threshold, (
        f"Test premise broken: printed-only ratio {ratio:.4f} outside ambiguous band "
        f"[{settings.ink_density_blank_threshold}, {settings.ink_density_ambiguous_threshold})"
    )
    return ratio


def _write_region_crop(directory: Path, filename: str, page: np.ndarray, bbox: tuple[int, int, int, int] = (100, 100, 300, 400)) -> Path:
    """Save the padded region crop of a page, as segmentation produces on disk."""
    x1, y1, x2, y2 = bbox
    padding = max(24, int(min(page.shape[1], page.shape[0]) * 0.025))
    crop = page[y1 - padding : y2 + padding, x1 - padding : x2 + padding]
    path = directory / filename
    cv2.imwrite(str(path), crop)
    return path


def _attempted_page() -> np.ndarray:
    """Printed page plus clear student strokes."""
    page = _printed_box_page()
    x1, y1, x2, y2 = (100, 100, 300, 400)
    for row in np.linspace(y1 + 30, y2 - 30, 8):
        cv2.line(page, (x1 + 10, int(row)), (x2 - 40, int(row)), (60, 60, 60), thickness=3)
    return page


def test_printed_only_scan_with_baseline_is_blank(tmp_path: Path) -> None:
    """A scan matching the blank template must be blank, not ambiguous."""
    printed = _printed_box_page()
    scan_path = _write_region_crop(tmp_path, "2i-abc123_p1.png", printed)
    _write_region_crop(tmp_path, "2i-abc123__baseline_p1.png", printed.copy())
    _assert_ratio_in_ambiguous_band(scan_path)

    result = classify_region(str(scan_path))
    assert result.status == "blank", (
        f"Printed-only region classified {result.status}; without the baseline comparison "
        "empty answer boxes consume choice slots and attempted items get skipped_beyond_n."
    )


def test_printed_only_scan_without_baseline_keeps_absolute_behavior(tmp_path: Path) -> None:
    """Without a baseline sibling the absolute thresholds still apply (fallback path)."""
    scan_path = _write_region_crop(tmp_path, "2ii-abc123_p1.png", _printed_box_page())
    _assert_ratio_in_ambiguous_band(scan_path)

    result = classify_region(str(scan_path))
    assert result.status == "ambiguous"


def test_attempted_scan_with_baseline_is_attempted(tmp_path: Path) -> None:
    """Student strokes well above the baseline must classify as attempted."""
    scan_path = _write_region_crop(tmp_path, "2iii-abc123_p1.png", _attempted_page())
    _write_region_crop(tmp_path, "2iii-abc123__baseline_p1.png", _printed_box_page())

    result = classify_region(str(scan_path))
    assert result.status == "attempted"


def test_heavy_print_blank_box_is_blank(tmp_path: Path) -> None:
    """Dense printed content defeats absolute thresholds; the baseline still works.

    Simulates a booklet whose printed baseline alone exceeds the ambiguous
    threshold (0.04): only the differential rule can call it blank.
    """
    heavy = _printed_box_page()
    x1, y1, x2, y2 = (100, 100, 300, 400)
    for row in np.linspace(y1 + 10, y2 - 10, 24):
        cv2.line(heavy, (x1 + 3, int(row)), (x2 - 3, int(row)), (90, 90, 90), thickness=2)

    scan_path = _write_region_crop(tmp_path, "3a-abc123_p1.png", heavy)
    _write_region_crop(tmp_path, "3a-abc123__baseline_p1.png", heavy.copy())

    gray = cv2.imread(str(scan_path), cv2.IMREAD_GRAYSCALE)
    heavy_ratio = float(np.count_nonzero(gray < 200)) / float(gray.size)
    assert heavy_ratio >= settings.ink_density_ambiguous_threshold

    result = classify_region(str(scan_path))
    assert result.status == "blank"


def test_baseline_files_excluded_from_region_glob(tmp_path: Path) -> None:
    """The "{key}_p*.png" glob must never collect baseline crops.

    first_n_filter, the grading route, and the preview listing all glob the
    regions directory with that pattern; a baseline file matching it would feed
    blank-template images to the VL model and pollute previews.
    """
    key = "2iv"
    stem = safe_region_filename_key(key)
    (tmp_path / f"{stem}_p1.png").write_bytes(b"scan-crop")
    (tmp_path / f"{stem}__baseline_p1.png").write_bytes(b"baseline-crop")

    matched = sorted(path.name for path in tmp_path.glob(f"{stem}_p*.png"))
    assert matched == [f"{stem}_p1.png"], f"Baseline leaked into region glob: {matched}"


def test_build_question_region_map_writes_baseline_crops(tmp_path: Path) -> None:
    """Segmentation must write the blank-template crop beside each scan crop."""
    bbox = (100, 100, 300, 400)
    reference_path = tmp_path / "reference_page_1.png"
    cv2.imwrite(str(reference_path), _printed_box_page(bbox=bbox))

    blank_scan_dir = tmp_path / "scan_blank"
    blank_scan_dir.mkdir()
    blank_scan_path = blank_scan_dir / "page_1.png"
    cv2.imwrite(str(blank_scan_path), _printed_box_page(bbox=bbox))

    attempted_scan_dir = tmp_path / "scan_attempted"
    attempted_scan_dir.mkdir()
    attempted_scan_path = attempted_scan_dir / "page_1.png"
    cv2.imwrite(str(attempted_scan_path), _attempted_page())

    template_pages = [
        {"page_number": 1, "regions": [{"question_number": "2", "part_label": "iv", "bbox": list(bbox)}]}
    ]
    alignment_reference = {
        "pages": {"1": {"reference_image_path": str(reference_path), "width": 400, "height": 600}}
    }

    for scan_dir in (blank_scan_dir, attempted_scan_dir):
        regions_dir = scan_dir / "regions"
        region_map, _previews = build_question_region_map(
            [str(scan_dir / "page_1.png")], template_pages, alignment_reference, regions_dir
        )
        assert "2iv" in region_map
        stem = safe_region_filename_key("2iv")
        baseline = regions_dir / f"{stem}__baseline_p1.png"
        scan_crop = regions_dir / f"{stem}_p1.png"
        assert baseline.exists(), "Segmentation did not write the blank-template baseline crop"
        assert scan_crop.exists()

    # Blank scan: identical printed content -> excess ~0 -> blank.
    blank_result = classify_region(str(blank_scan_dir / "regions" / f"{safe_region_filename_key('2iv')}_p1.png"))
    assert blank_result.status == "blank"
    # Attempted scan: strokes well above the baseline -> attempted.
    attempted_result = classify_region(str(attempted_scan_dir / "regions" / f"{safe_region_filename_key('2iv')}_p1.png"))
    assert attempted_result.status == "attempted"
