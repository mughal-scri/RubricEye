from __future__ import annotations

import json
from dataclasses import dataclass
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
    count = min(len(reference), len(detected), limit)
    if count < 2:
        return [], []

    def sample(values: list[int]) -> list[float]:
        indices = np.linspace(0, len(values) - 1, count).round().astype(int).tolist()
        return [float(values[index]) for index in indices]

    return sample(reference), sample(detected)


def _filter_matches_ratio(
    distances: list[float], ratio: float = 0.85
) -> list[int]:
    """Return indices passing Lowe-style ratio test on 1-D distance lists."""
    if len(distances) < 2:
        return list(range(len(distances)))
    sorted_dist = sorted(distances)
    threshold = sorted_dist[0] / max(sorted_dist[1], 1e-6) if sorted_dist[1] > 0 else 0.0
    if threshold < ratio:
        return []
    best = sorted_dist[0]
    return [i for i, d in enumerate(distances) if d <= best * (1.0 + ratio)]


def _match_line_pairs(
    reference: list[int], detected: list[int], max_distance: float = 80.0
) -> tuple[list[float], list[float]]:
    """Match reference lines to nearest detected lines with outlier rejection.

    For each reference line position, finds the nearest detected line.  Pairs
    where no detected line is within *max_distance* pixels are discarded.  This
    is more robust than uniform sampling when the scan has slightly different
    line counts (missed faint lines or merged clusters).
    """
    if len(reference) < 2 or len(detected) < 2:
        return [], []
    ref_arr = np.array(reference, dtype=np.float64)
    det_arr = np.array(detected, dtype=np.float64)
    # Distance matrix: rows=reference, cols=detected
    dist_matrix = np.abs(ref_arr[:, None] - det_arr[None, :])
    best_indices = np.argmin(dist_matrix, axis=1)
    best_distances = dist_matrix[np.arange(len(ref_arr)), best_indices]
    matched: list[tuple[float, float]] = []
    for i, (idx, dist) in enumerate(zip(best_indices, best_distances)):
        if dist <= max_distance:
            matched.append((float(ref_arr[i]), float(det_arr[idx])))
    if len(matched) < 2:
        return [], []
    return [m[0] for m in matched], [m[1] for m in matched]


def _collect_grid_points(
    alignment_reference: dict,
    page_number: int,
    scan_h: list[int],
    scan_v: list[int],
) -> tuple[np.ndarray, np.ndarray]:
    """Build grid intersection point pairs using nearest-neighbor line matching.

    Previously used uniform sampling which produces systematic mis-pairing
    when the reference and scan have different line counts.  Now uses
    nearest-neighbor distance matching so each reference line is paired with
    the physically closest detected line.
    """
    pages = alignment_reference.get("pages", {})
    page_ref = pages.get(str(page_number), {})
    ref_h = _cluster_positions(page_ref.get("horizontal_lines", []))
    ref_v = _cluster_positions(page_ref.get("vertical_lines", []))
    matched_h_ref, matched_h_det = _match_line_pairs(ref_h, scan_h)
    matched_v_ref, matched_v_det = _match_line_pairs(ref_v, scan_v)
    if len(matched_h_ref) < 2 or len(matched_v_ref) < 2:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    src_points: list[list[float]] = []
    dst_points: list[list[float]] = []
    for ref_y, scan_y in zip(matched_h_ref, matched_h_det):
        for ref_x, scan_x in zip(matched_v_ref, matched_v_det):
            src_points.append([ref_x, ref_y])
            dst_points.append([scan_x, scan_y])
    return np.array(src_points, dtype=np.float32), np.array(dst_points, dtype=np.float32)


def _compute_scale_translate(
    ref_h: list[int],
    scan_h: list[int],
    ref_v: list[int],
    scan_v: list[int],
    min_pairs: int = 2,
) -> np.ndarray | None:
    """Estimate scale + translate from matched line positions.

    Uses the outermost reliably matched line pairs per axis to compute a
    uniform scale and separate x/y translation.  More accurate than the
    pure-scale fallback (which ignores page margins) and sufficient for
    the common case where the scan is slightly resized and shifted.
    """
    h_ref, h_det = _match_line_pairs(ref_h, scan_h)
    v_ref, v_det = _match_line_pairs(ref_v, scan_v)
    if len(h_ref) < min_pairs or len(v_ref) < min_pairs:
        return None
    # Scale from the span between outermost matched pairs.
    h_span_ref = h_ref[-1] - h_ref[0]
    h_span_det = h_det[-1] - h_det[0]
    v_span_ref = v_ref[-1] - v_ref[0]
    v_span_det = v_det[-1] - v_det[0]
    if abs(h_span_ref) < 1.0 or abs(v_span_ref) < 1.0:
        return None
    scale = (h_span_det / h_span_ref + v_span_det / v_span_ref) / 2.0
    if scale <= 0 or not np.isfinite(scale):
        return None
    tx = v_det[0] - scale * v_ref[0]
    ty = h_det[0] - scale * h_ref[0]
    return np.array(
        [[scale, 0, tx], [0, scale, ty], [0, 0, 1]], dtype=np.float64
    )


def _valid_homography(matrix: np.ndarray | None, ref_w: int, ref_h: int, scan_w: int, scan_h: int) -> bool:
    if matrix is None or matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        return False
    corners = np.array([[0, 0], [ref_w, 0], [ref_w, ref_h], [0, ref_h]], dtype=np.float32).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
    if not np.isfinite(projected).all():
        return False
    area = abs(float(cv2.contourArea(projected.astype(np.float32))))
    if area < scan_w * scan_h * 0.12:
        return False
    bbox_w = float(projected[:, 0].max() - projected[:, 0].min())
    bbox_h = float(projected[:, 1].max() - projected[:, 1].min())
    if bbox_w < scan_w * 0.45 or bbox_h < scan_h * 0.45:
        return False
    if bbox_w > scan_w * 2.5 or bbox_h > scan_h * 2.5:
        return False
    return True


def _feature_homography(reference_path: str, scan_image: np.ndarray, ref_w: int, ref_h: int) -> np.ndarray | None:
    reference = cv2.imread(reference_path, cv2.IMREAD_GRAYSCALE)
    scan_gray = cv2.cvtColor(scan_image, cv2.COLOR_BGR2GRAY)
    if reference is None:
        return None

    max_dimension = 1800
    ref_scale = min(1.0, max_dimension / max(reference.shape))
    scan_scale = min(1.0, max_dimension / max(scan_gray.shape))
    ref_small = cv2.resize(reference, None, fx=ref_scale, fy=ref_scale, interpolation=cv2.INTER_AREA)
    scan_small = cv2.resize(scan_gray, None, fx=scan_scale, fy=scan_scale, interpolation=cv2.INTER_AREA)

    if hasattr(cv2, "SIFT_create"):
        detector = cv2.SIFT_create(nfeatures=3500, contrastThreshold=0.02)
        keypoints_ref, descriptors_ref = detector.detectAndCompute(ref_small, None)
        keypoints_scan, descriptors_scan = detector.detectAndCompute(scan_small, None)
        if descriptors_ref is None or descriptors_scan is None:
            return None
        matcher = cv2.BFMatcher(cv2.NORM_L2)
    else:
        detector = cv2.ORB_create(nfeatures=4000)
        keypoints_ref, descriptors_ref = detector.detectAndCompute(ref_small, None)
        keypoints_scan, descriptors_scan = detector.detectAndCompute(scan_small, None)
        if descriptors_ref is None or descriptors_scan is None:
            return None
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    pairs = matcher.knnMatch(descriptors_ref, descriptors_scan, k=2)
    good = [first for first, second in pairs if first.distance < 0.72 * second.distance]
    if len(good) < 8:
        return None

    src = np.float32([keypoints_ref[m.queryIdx].pt for m in good]) / ref_scale
    dst = np.float32([keypoints_scan[m.trainIdx].pt for m in good]) / scan_scale
    matrix, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if matrix is None or inliers is None or int(inliers.sum()) < 8:
        return None
    return matrix


@dataclass
class AlignmentResult:
    matrix: np.ndarray | None
    method: str
    confidence: str


def compute_alignment_result(scan_image_path: str, alignment_reference: dict, page_number: int) -> AlignmentResult:
    """Compute the best alignment matrix for a scanned page.

    Cascade order (most accurate first):
      1. feature — SIFT/ORB keypoint homography (perspective-capable)
      2. scale_translate — matched grid-line scale + offset (most scans)
      3. grid — line-intersection homography with NN-matched correspondences
      4. scale_only — pure corner scale (last resort, no translation)
    """
    image = cv2.imread(scan_image_path)
    if image is None:
        return AlignmentResult(None, "failed", "none")
    scan_h, scan_v = _detect_lines(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    scan_h = _cluster_positions(scan_h)
    scan_v = _cluster_positions(scan_v)
    page_ref = alignment_reference.get("pages", {}).get(str(page_number), {})
    ref_w = int(page_ref.get("width") or image.shape[1])
    ref_h = int(page_ref.get("height") or image.shape[0])

    # Method 1: Feature-based homography (most accurate, handles perspective).
    reference_path = page_ref.get("reference_image_path")
    if reference_path and Path(reference_path).exists():
        feature_matrix = _feature_homography(reference_path, image, ref_w, ref_h)
        if _valid_homography(feature_matrix, ref_w, ref_h, image.shape[1], image.shape[0]):
            return AlignmentResult(feature_matrix, "feature", "high")

    # Collect clustered reference line positions for methods 2–3.
    ref_h_lines = _cluster_positions(page_ref.get("horizontal_lines", []))
    ref_v_lines = _cluster_positions(page_ref.get("vertical_lines", []))

    # Method 2: Scale + translate from matched grid lines.
    # Sufficient for the common case where the scan is slightly resized and
    # shifted on the scanner bed — the most frequent real-world scenario.
    st_matrix = _compute_scale_translate(ref_h_lines, scan_h, ref_v_lines, scan_v)
    if st_matrix is not None:
        return AlignmentResult(st_matrix, "scale_translate", "high")

    # Method 3: Grid-based homography from NN-matched line intersections.
    src_pts, dst_pts = _collect_grid_points(alignment_reference, page_number, scan_h, scan_v)
    if src_pts.size >= 8 and dst_pts.size >= 8:
        line_matrix, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if _valid_homography(line_matrix, ref_w, ref_h, image.shape[1], image.shape[0]):
            return AlignmentResult(line_matrix, "grid", "medium")

    # Method 4: Pure scale fallback (no translation — last resort).
    scale_x = image.shape[1] / ref_w if ref_w else 1.0
    scale_y = image.shape[0] / ref_h if ref_h else 1.0
    return AlignmentResult(np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=np.float64), "scale_only", "low")


def compute_alignment_matrix(scan_image_path: str, alignment_reference: dict, page_number: int) -> np.ndarray | None:
    """Backward-compatible matrix-only helper for callers outside segmentation."""
    return compute_alignment_result(scan_image_path, alignment_reference, page_number).matrix


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
