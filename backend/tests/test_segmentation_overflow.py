"""Offline tests for segmentation overflow capture (acceptance Test E).

An answer written slightly outside its nominal region box must still land in
that region's expanded crop — attributed to the correct question and visible
to the grader — while the padding-ring check flags it for the examiner.
"""

from __future__ import annotations

import numpy as np

from app.services.segmentation import _expand_bbox, _has_overflow


def _blank_page(width: int = 400, height: int = 600) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def test_ink_in_padding_ring_is_flagged_and_kept_in_crop():
    """Out-of-box strokes stay inside their own region's expanded crop."""
    page = _blank_page()
    nominal = [100, 100, 300, 200]
    expanded = _expand_bbox(nominal, page.shape[1], page.shape[0])

    # Student writes just below the nominal box, inside the padding ring.
    page[205:215, 150:250] = 0

    assert _has_overflow(page, nominal, expanded), "Ring ink must raise the overflow flag"

    x1, y1, x2, y2 = expanded
    crop = page[y1:y2, x1:x2]
    ink_pixels = int((crop < 200).sum())
    assert ink_pixels > 0, (
        "Out-of-box strokes must remain inside this region's crop so they are "
        "attributed to the correct question, not lost or reassigned"
    )


def test_ink_inside_nominal_box_is_not_overflow():
    """Ink inside the assigned box must not raise the overflow flag."""
    page = _blank_page()
    nominal = [100, 100, 300, 200]
    expanded = _expand_bbox(nominal, page.shape[1], page.shape[0])

    page[120:180, 150:250] = 0

    assert not _has_overflow(page, nominal, expanded)
