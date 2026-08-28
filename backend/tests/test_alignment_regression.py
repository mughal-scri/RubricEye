"""Regression guard for the alignment homography fix.

Phase 0.1 of the phase plan: assert that _collect_grid_points produces
distinct source and destination point sets when the reference and scan
grids differ. This prevents silent regression of the src==dst no-op bug.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.alignment import _collect_grid_points


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
