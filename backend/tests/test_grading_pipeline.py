"""Offline tests for the grading pipeline (Phase 4).

Covers ink-density classification, score validation with mocked DashScope,
template derivation escalation seams, and Phase 3 audit-trail fields.
Converted from validate_grading_integrity.py, validate_hardening_local.py,
validate_template_derivation_escalation.py, and ink_density.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.services import grading
from app.services.first_n_filter import QuestionUnit
from app.services.ink_density import InkDensityResult, classify_region, classify_unit, measure_ink_density


# ---------------------------------------------------------------------------
# Ink density classification
# ---------------------------------------------------------------------------


def _make_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (24, 24), color).save(path)


def test_ink_density_blank_image():
    """A pure-white image should classify as blank."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_ink_") as d:
        white = Path(d) / "white.png"
        _make_image(white, (255, 255, 255))
        result = classify_region(str(white))
        assert result.status == "blank", f"Expected blank, got {result.status} (ratio={result.ratio})"
        assert result.ratio < 0.01


def test_ink_density_attempted_image():
    """A pure-black image should classify as attempted."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_ink_") as d:
        black = Path(d) / "black.png"
        _make_image(black, (0, 0, 0))
        result = classify_region(str(black))
        assert result.status == "attempted", f"Expected attempted, got {result.status} (ratio={result.ratio})"
        assert result.ratio > 0.9


@pytest.mark.parametrize(
    "ratio,expected_status",
    [
        (0.005, "blank"),
        (0.015, "blank"),
        (0.025, "ambiguous"),
        (0.05, "attempted"),
        (0.5, "attempted"),
    ],
)
def test_ink_density_threshold_boundaries(ratio, expected_status):
    """Verify the three-way classification boundaries."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_ink_") as d:
        img = Path(d) / "test.png"
        _make_image(img, (255, 255, 255))
        result = classify_region(
            str(img),
            blank_threshold=0.02,
            ambiguous_threshold=0.04,
        )
        # Force a specific ratio by patching measure_ink_density
        with patch("app.services.ink_density.measure_ink_density", return_value=ratio):
            result = classify_region(
                str(img),
                blank_threshold=0.02,
                ambiguous_threshold=0.04,
            )
        assert result.status == expected_status, (
            f"ratio={ratio}: expected {expected_status}, got {result.status}"
        )


def test_classify_unit_any_attempted_wins():
    """A multi-crop unit where any crop is attempted → whole unit is attempted."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_ink_") as d:
        blank = Path(d) / "blank.png"
        attempted = Path(d) / "attempted.png"
        _make_image(blank, (255, 255, 255))
        _make_image(attempted, (0, 0, 0))
        result = classify_unit([str(blank), str(attempted)])
        assert result.status == "attempted"


def test_classify_unit_empty_paths_is_blank():
    """No images → blank."""
    result = classify_unit([])
    assert result.status == "blank"
    assert result.ratio == 0.0


# ---------------------------------------------------------------------------
# Score validation with mocked DashScope
# ---------------------------------------------------------------------------


def _mock_client(payload: dict) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def test_compound_batch_evidence_and_scores():
    """Compound batch must send both distinct evidence images and split scores correctly.

    From validate_grading_integrity.py — the core evidence-preservation test.
    """
    with tempfile.TemporaryDirectory(prefix="rubriceye_grading_") as d:
        root = Path(d)
        part_a = root / "3a.png"
        part_b = root / "3b.png"
        _make_image(part_a, (255, 0, 0))
        _make_image(part_b, (0, 0, 255))

        qb = {
            "3a": MagicMock(marks_possible=4, key_points="a"),
            "3b": MagicMock(marks_possible=6, key_points="b"),
        }
        compound = [
            QuestionUnit("3a", "attempted", 0.2, [str(part_a)], "choice", "choice:0", [str(part_a), str(part_b)]),
            QuestionUnit("3b", "attempted", 0.3, [str(part_b)], "choice", "choice:0", [str(part_a), str(part_b)]),
        ]
        payload = {
            "transcription_summary": "Both parts visible.",
            "part_scores": [
                {"part": "a", "marks_awarded": 3, "marks_possible": 4, "rationale": "A evidence."},
                {"part": "b", "marks_awarded": 5, "marks_possible": 6, "rationale": "B evidence."},
            ],
            "total_awarded": 8,
            "total_possible": 10,
            "flags": [],
            "confidence": "high",
        }
        client = _mock_client(payload)
        with patch.object(grading, "_get_client", return_value=client):
            results = grading.grade_batch(compound, qb)

        assert len(results) == 2
        assert all(r.grading_status == "complete" for r in results)

        # Verify evidence images were sent
        sent_content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        sent_images = [e["image_url"]["url"] for e in sent_content if e["type"] == "image_url"]
        assert len(sent_images) == 2, "compound batch must send both distinct evidence images"

        # Verify scores split correctly
        assert [r.ai_score for r in results] == [3, 5]


def test_compound_batch_blank_part_scores_zero():
    """A blank part in a selected compound unit scores 0 without bleeding marks.

    Acceptance Test B (Section C half): the first-N filter selects the unit
    because one part is attempted; this pins the grading side — the blank
    part keeps its own rubric row and scores 0 while the attempted part's
    marks stay with the attempted part.
    """
    with tempfile.TemporaryDirectory(prefix="rubriceye_grading_") as d:
        root = Path(d)
        part_a = root / "10a.png"
        part_b = root / "10b.png"
        _make_image(part_a, (255, 0, 0))
        _make_image(part_b, (255, 255, 255))

        qb = {
            "10a": MagicMock(marks_possible=4, key_points="a"),
            "10b": MagicMock(marks_possible=6, key_points="b"),
        }
        compound = [
            QuestionUnit("10a", "attempted", 0.2, [str(part_a)], "choice", "choice:0", [str(part_a), str(part_b)]),
            QuestionUnit("10b", "attempted", 0.0, [str(part_b)], "choice", "choice:0", [str(part_a), str(part_b)]),
        ]
        payload = {
            "transcription_summary": "Part (a) answered, part (b) blank.",
            "part_scores": [
                {"part": "a", "marks_awarded": 3, "marks_possible": 4, "rationale": "A evidence."},
                {"part": "b", "marks_awarded": 0, "marks_possible": 6, "rationale": "Blank."},
            ],
            "total_awarded": 3,
            "total_possible": 10,
            "flags": [],
            "confidence": "high",
        }
        client = _mock_client(payload)
        with patch.object(grading, "_get_client", return_value=client):
            results = grading.grade_batch(compound, qb)

        assert len(results) == 2
        assert all(r.grading_status == "complete" for r in results)
        assert [r.ai_score for r in results] == [3, 0], (
            f"Blank part must score 0 without bleeding: {[r.ai_score for r in results]}"
        )
        assert results[0].ai_total_possible == 4
        assert results[1].ai_total_possible == 6


def test_bare_question_aggregates_parts():
    """Bare question (no part label) aggregates part scores into total."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_grading_") as d:
        root = Path(d)
        img = root / "img.png"
        _make_image(img, (128, 128, 128))

        qb = {"2": MagicMock(marks_possible=15, key_points="all parts")}
        unit = [QuestionUnit("2", "attempted", 0.4, [str(img)], None)]
        payload = {
            "part_scores": [
                {"part": "i", "marks_awarded": 4, "marks_possible": 7, "rationale": "i"},
                {"part": "ii", "marks_awarded": 5, "marks_possible": 8, "rationale": "ii"},
            ],
            "total_awarded": 9,
            "total_possible": 15,
            "flags": [],
            "confidence": "medium",
        }
        client = _mock_client(payload)
        with patch.object(grading, "_get_client", return_value=client):
            results = grading.grade_batch(unit, qb)

        assert results[0].grading_status == "complete"
        assert results[0].ai_score == 9
        assert results[0].ai_total_possible == 15
        assert len(results[0].part_scores) == 2


def test_invalid_score_rejected():
    """AI scores exceeding the authoritative maximum must fail grading."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_grading_") as d:
        root = Path(d)
        img = root / "img.png"
        _make_image(img, (128, 128, 128))

        payload = {
            "part_scores": [{"part": "", "marks_awarded": 9, "marks_possible": 5, "rationale": "invalid"}],
            "total_awarded": 9,
            "total_possible": 5,
            "flags": [],
            "confidence": "high",
        }
        client = _mock_client(payload)
        with patch.object(grading, "_get_client", return_value=client):
            results = grading.grade_batch(
                [QuestionUnit("3a", "attempted", 0.2, [str(img)], None)],
                {"3a": MagicMock(marks_possible=5, key_points="a")},
            )

        assert results[0].grading_status == "failed"
        assert results[0].ai_score is None
        assert "outside" in (results[0].error_message or "")


def test_audit_fields_populated_on_success():
    """Phase 3: model_name, prompt_version, raw_response_json, request_payload_summary."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_audit_") as d:
        root = Path(d)
        img = root / "img.png"
        _make_image(img, (128, 128, 128))

        payload = {
            "transcription_summary": "Test.",
            "part_scores": [{"part": "", "marks_awarded": 3, "marks_possible": 5, "rationale": "ok"}],
            "total_awarded": 3,
            "total_possible": 5,
            "flags": [],
            "confidence": "high",
        }
        client = _mock_client(payload)
        with patch.object(grading, "_get_client", return_value=client):
            results = grading.grade_batch(
                [QuestionUnit("1", "attempted", 0.3, [str(img)], None)],
                {"1": MagicMock(marks_possible=5, key_points="k")},
            )

        r = results[0]
        assert r.grading_status == "complete"
        assert r.model_name is not None, "model_name must be populated"
        assert r.prompt_version is not None, "prompt_version must be populated"
        assert r.raw_response_json is not None, "raw_response_json must be populated"
        assert r.request_payload_summary is not None, "request_payload_summary must be populated"
        # Verify payload summary contains expected keys
        summary = json.loads(r.request_payload_summary)
        assert "image_count" in summary
        assert "prompt_version" in summary
        assert "model" in summary


def test_audit_fields_populated_on_failure():
    """Phase 3: audit fields must be present even when grading fails validation."""
    with tempfile.TemporaryDirectory(prefix="rubriceye_audit_fail_") as d:
        root = Path(d)
        img = root / "img.png"
        _make_image(img, (128, 128, 128))

        payload = {
            "part_scores": [{"part": "", "marks_awarded": 99, "marks_possible": 5, "rationale": "bad"}],
            "total_awarded": 99,
            "total_possible": 5,
            "flags": [],
            "confidence": "high",
        }
        client = _mock_client(payload)
        with patch.object(grading, "_get_client", return_value=client):
            results = grading.grade_batch(
                [QuestionUnit("1", "attempted", 0.3, [str(img)], None)],
                {"1": MagicMock(marks_possible=5, key_points="k")},
            )

        r = results[0]
        assert r.grading_status == "failed"
        assert r.model_name is not None, "audit fields must be populated even on failure"
        assert r.prompt_version is not None


# ---------------------------------------------------------------------------
# Template derivation escalation (from validate_template_derivation_escalation.py)
# ---------------------------------------------------------------------------


def test_template_derivation_strong_local_no_fallback():
    """Strong local evidence must NOT trigger vision fallback."""
    from app.services.template_derivation import derive_template_map
    from app.services.template_types import DetectedRegion
    from app.services.template_vision_fallback import VisionDerivationResult

    local_regions = [
        DetectedRegion(question_number="1", part_label="", bbox=[10, 20, 200, 180]),
        DetectedRegion(question_number="2", part_label="", bbox=[10, 220, 200, 380]),
    ]
    call_count = 0

    def fake_fallback(_paths):
        nonlocal call_count
        call_count += 1
        return VisionDerivationResult(pages={}, alignment_reference={}, confidence="low")

    with patch("app.services.template_derivation._raster_page_alignment", return_value={}), \
         patch("app.services.template_derivation.extract_regions_with_vision", side_effect=fake_fallback), \
         patch("app.services.template_derivation._derive_page_from_raster", return_value=(local_regions, {})):
        result = derive_template_map(["synthetic-page.png"])

    assert result.confidence == "high"
    assert not result.used_vision_fallback
    assert call_count == 0, "vision fallback should NOT have been called"


def test_template_derivation_weak_local_uses_fallback():
    """Weak local evidence (no regions) must escalate to vision fallback."""
    from app.services.template_derivation import derive_template_map
    from app.services.template_vision_fallback import VisionDerivationResult

    call_count = 0

    def fake_fallback(_paths):
        nonlocal call_count
        call_count += 1
        return VisionDerivationResult(pages={}, alignment_reference={}, confidence="low")

    with patch("app.services.template_derivation._raster_page_alignment", return_value={}), \
         patch("app.services.template_derivation.extract_regions_with_vision", side_effect=fake_fallback), \
         patch("app.services.template_derivation._derive_page_from_raster", return_value=([], {})):
        result = derive_template_map(["synthetic-page.png"])

    assert result.used_vision_fallback
    assert call_count == 1, "vision fallback should have been called exactly once"


# ---------------------------------------------------------------------------
# Template gating (from validate_hardening_local.py)
# ---------------------------------------------------------------------------


def test_template_gating_empty_labels():
    """_assign_boxes_to_labels with no labels returns empty list."""
    from app.services.template_derivation import _assign_boxes_to_labels

    boxes = [[10, 10, 100, 100], [10, 120, 100, 220]]
    assert _assign_boxes_to_labels([], boxes) == []
