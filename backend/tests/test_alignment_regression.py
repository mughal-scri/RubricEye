"""Regression guard for the alignment homography fix.

Phase 0.1 of the phase plan: assert that _collect_grid_points produces
distinct source and destination point sets when the reference and scan
grids differ. This prevents silent regression of the src==dst no-op bug.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.alignment import _collect_grid_points, _match_line_pairs, _compute_scale_translate, transform_bbox


def test_collect_grid_points_distinct_grids_produce_distinct_points():
    """When reference and scan grids differ, src and dst must NOT be identical.

    This is the regression guard for the alignment homography no-op bug:
    previously, dst was a copy of src, making the transform a no-op.
    """
    alignment_reference = {
        "pages": {
            "1": {
                "horizontal_lines": [100, 200, 300, 400],
                "vertical_lines": [100, 200, 300, 400],
            }
        }
    }
    # Scan has different line positions (shifted by ~20px)
    scan_h = [120, 220, 320, 420]
    scan_v = [115, 215, 315, 415]

    src, dst = _collect_grid_points(alignment_reference, 1, scan_h, scan_v)

    assert src.size >= 8, f"Expected at least 8 src points, got {src.size}"
    assert dst.size >= 8, f"Expected at least 8 dst points, got {dst.size}"
    assert not np.allclose(src, dst), (
        "CRITICAL: src and dst point sets are identical — alignment would be a no-op. "
        "This regression guard exists to prevent the homography bug from silently returning."
    )


def test_collect_grid_points_nonidentity_matrix_when_grids_differ():
    """The homography matrix must NOT be identity when grids are offset."""
    import cv2

    alignment_reference = {
        "pages": {
            "1": {
                "horizontal_lines": [100, 200, 300, 400, 500],
                "vertical_lines": [100, 200, 300, 400, 500],
            }
        }
    }
    scan_h = [110, 210, 310, 410, 510]
    scan_v = [105, 205, 305, 405, 505]

    src, dst = _collect_grid_points(alignment_reference, 1, scan_h, scan_v)
    assert src.size >= 8 and dst.size >= 8

    matrix, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    assert matrix is not None, "findHomography returned None"

    identity = np.eye(3, dtype=np.float64)
    assert not np.allclose(matrix, identity, atol=1e-3), (
        "CRITICAL: homography matrix is identity despite offset grids. "
        "The alignment transform would be a no-op."
    )


def test_collect_grid_points_insufficient_lines_returns_empty():
    """With fewer than 2 horizontal or vertical lines, returns empty arrays."""
    alignment_reference = {
        "pages": {
            "1": {
                "horizontal_lines": [100],  # Only 1 line — insufficient
                "vertical_lines": [100, 200, 300],
            }
        }
    }
    src, dst = _collect_grid_points(alignment_reference, 1, [120], [115, 215, 315])
    assert src.size == 0
    assert dst.size == 0


def test_match_line_pairs_nearest_neighbor_correctness():
    """NN matching must pair each reference line with the physically closest scan line.

    Regression guard for the uniform-sampling bug: when reference has more
    lines than the scan, index-based sampling produces mis-paired correspondences.
    """
    ref = [100, 200, 300, 400, 500]
    det = [105, 210, 305, 415]  # missing the line near 500
    r, d = _match_line_pairs(ref, det)
    assert len(r) == 4, f"Expected 4 pairs, got {len(r)}"
    # Each matched pair must be within ~15px (not mis-paired by index).
    for rv, dv in zip(r, d):
        assert abs(rv - dv) <= 20, f"Mis-paired: ref={rv} matched to det={dv}"


def test_match_line_pairs_handles_scale_offset():
    """When scan is uniformly scaled + shifted, NN matching must find all pairs."""
    ref = [100, 200, 300, 400, 500, 600]
    # Scan: 1.05x scale + 10px offset
    det = [int(100 * 1.05 + 10), int(200 * 1.05 + 10), int(300 * 1.05 + 10),
           int(400 * 1.05 + 10), int(500 * 1.05 + 10), int(600 * 1.05 + 10)]
    r, d = _match_line_pairs(ref, det)
    assert len(r) == 6, f"Expected 6 pairs, got {len(r)}"


def test_compute_scale_translate_recovers_offset():
    """Scale-translate must recover both scale and translation, not just scale.

    This is the core regression guard: the old scale_only fallback ignored
    translation, causing systematic crop displacement on every scan that
    wasn't pixel-perfectly aligned to the top-left corner.
    """
    ref_h = [100, 300, 500, 700]
    ref_v = [50, 250, 450]
    # Scan: 1.03x scale + 15px right + 20px down
    scale = 1.03
    tx, ty = 15, 20
    det_h = [int(100 * scale + ty), int(300 * scale + ty),
             int(500 * scale + ty), int(700 * scale + ty)]
    det_v = [int(50 * scale + tx), int(250 * scale + tx), int(450 * scale + tx)]

    matrix = _compute_scale_translate(ref_h, det_h, ref_v, det_v)
    assert matrix is not None, "scale_translate returned None with sufficient data"
    # Verify the matrix correctly transforms a known template bbox.
    bbox = [100, 200, 300, 400]
    result = transform_bbox(bbox, matrix)
    expected_x1 = int(100 * scale + tx)
    expected_y1 = int(200 * scale + ty)
    # Allow 2px tolerance for integer rounding.
    assert abs(result[0] - expected_x1) <= 2, f"x1: {result[0]} vs {expected_x1}"
    assert abs(result[1] - expected_y1) <= 2, f"y1: {result[1]} vs {expected_y1}"


def test_compute_scale_translate_insufficient_data_returns_none():
    """With fewer than 2 matched pairs per axis, returns None."""
    assert _compute_scale_translate([100], [105], [50, 250], [52, 255]) is None
    assert _compute_scale_translate([100, 300], [105, 310], [50], [52]) is None


def test_collect_grid_points_unequal_line_counts():
    """NN matching must handle mismatched line counts without mis-pairing.

    This tests the exact scenario that broke uniform sampling: reference has
    6 lines, scan detects only 4.  With index-based sampling, ref[4] would
    be paired with det[3] (wrong).  With NN matching, ref lines without a
    nearby detected line are simply excluded.
    """
    alignment_reference = {
        "pages": {
            "1": {
                "horizontal_lines": [100, 200, 300, 400, 500, 600],
                "vertical_lines": [100, 300, 500, 700],
            }
        }
    }
    # Scan: only 4 of 6 horizontal lines detected
    scan_h = [103, 205, 398, 602]
    scan_v = [102, 303, 498, 705]
    src, dst = _collect_grid_points(alignment_reference, 1, scan_h, scan_v)
    assert src.size >= 8, f"Expected >= 8 points, got {src.size}"
    # Every src-dst pair should be within 10px (NN, not index-based).
    for i in range(len(src)):
        dist = np.linalg.norm(src[i] - dst[i])
        assert dist < 20, f"Pair {i}: src={src[i]} dst={dst[i]} dist={dist:.1f}"
