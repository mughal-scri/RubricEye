from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def _detect_lines(gray: np.ndarray) -> tuple[list[int], list[int]]:
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=80, maxLineGap=10)
    horizontals: list[int] = []
    verticals: list[int] = []
    if lines is not None:
        for line in lines.reshape(-1, 4):
            x1, y1, x2, y2 = line
            if abs(y2 - y1) < 8:
                horizontals.append(int((y1 + y2) / 2))
            elif abs(x2 - x1) < 8:
                verticals.append(int((x1 + x2) / 2))
    return sorted(set(horizontals)), sorted(set(verticals))


def _cluster_positions(values: list[int], tolerance: int = 12) -> list[int]:
    if not values:
        return []
    clusters: list[list[int]] = [[values[0]]]
    for value in values[1:]:
        if abs(value - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [int(sum(cluster) / len(cluster)) for cluster in clusters]


def _sample_corresponding(reference: list[int], detected: list[int], limit: int = 8) -> tuple[list[float], list[float]]:
    """Pair ordered template and scan grid lines without assuming identical coordinates.

    The template stores line positions in the blank-booklet reference image, while the
    scan contains the corresponding lines after camera/scanner distortion. Sampling
    both ordered lists at the same number of positions gives findHomography real
    reference -> scan correspondences and still tolerates a few spurious lines.
    """
    count = min(len(reference), len(detected), limit)
    if count < 2:
        return [], []

    def sample(values: list[int]) -> list[float]:
        indices = np.linspace(0, len(values) - 1, count).round().astype(int).tolist()
        return [float(values[index]) for index in indices]

    return sample(reference), sample(detected)


def _collect_grid_points(
    alignment_reference: dict,
    page_number: int,
    scan_h: list[int],
    scan_v: list[int],
) -> tuple[np.ndarray, np.ndarray]:
    pages = alignment_reference.get("pages", {})
    page_ref = pages.get(str(page_number), {})
    ref_h = _cluster_positions(page_ref.get("horizontal_lines", []))
    ref_v = _cluster_positions(page_ref.get("vertical_lines", []))

    template_h, detected_h = _sample_corresponding(ref_h, scan_h)
    template_v, detected_v = _sample_corresponding(ref_v, scan_v)
    if len(template_h) < 2 or len(template_v) < 2:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    src_points: list[list[float]] = []
    dst_points: list[list[float]] = []
    for ref_y, scan_y in zip(template_h, detected_h):
        for ref_x, scan_x in zip(template_v, detected_v):
            src_points.append([ref_x, ref_y])
            dst_points.append([scan_x, scan_y])
    return np.array(src_points, dtype=np.float32), np.array(dst_points, dtype=np.float32)


def compute_alignment_matrix(
    scan_image_path: str,
    alignment_reference: dict,
    page_number: int,
) -> np.ndarray | None:
    image = cv2.imread(scan_image_path)
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scan_h, scan_v = _detect_lines(gray)
    scan_h = _cluster_positions(scan_h)
    scan_v = _cluster_positions(scan_v)

    src_pts, dst_pts = _collect_grid_points(alignment_reference, page_number, scan_h, scan_v)
    if src_pts.size >= 8 and dst_pts.size >= 8:
        matrix, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if matrix is not None and np.isfinite(matrix).all():
            return matrix

    ref_page = alignment_reference.get("pages", {}).get(str(page_number), {})
    ref_h = ref_page.get("height")
    ref_w = ref_page.get("width")
    if ref_h and ref_w:
        scale_x = ref_w / image.shape[1]
        scale_y = ref_h / image.shape[0]
        return np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=np.float64)
    return np.identity(3, dtype=np.float64)


def transform_bbox(bbox: list[int], matrix: np.ndarray) -> list[int]:
    x1, y1, x2, y2 = bbox
    corners = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
    xs = transformed[:, 0]
    ys = transformed[:, 1]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def load_alignment_reference(project_dir: Path) -> dict:
    path = project_dir / "alignment_reference.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
