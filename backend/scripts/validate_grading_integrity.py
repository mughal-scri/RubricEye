"""No-cost grading integrity regressions for evidence preservation and score bounds."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from app.services.first_n_filter import QuestionUnit
from app.services import grading


def _image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (24, 24), color).save(path)


def _client(payload: dict) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rubriceye_grading_integrity_") as directory:
        root = Path(directory)
        part_a = root / "3a.png"
        part_b = root / "3b.png"
        _image(part_a, (255, 0, 0))
        _image(part_b, (0, 0, 255))
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
        client = _client(payload)
        with patch.object(grading, "_get_client", return_value=client):
            results = grading.grade_batch(compound, qb)
        assert len(results) == 2 and all(result.grading_status == "complete" for result in results), results
        sent_content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        sent_images = [entry["image_url"]["url"] for entry in sent_content if entry["type"] == "image_url"]
        assert len(sent_images) == 2, "compound batch must send both distinct evidence images"
        assert "Part (a)" in sent_content[0]["text"] and "Part (b)" in sent_content[0]["text"]
        assert [result.ai_score for result in results] == [3, 5]

        bare_qb = {"2": MagicMock(marks_possible=15, key_points="all parts")}
        bare_unit = [QuestionUnit("2", "attempted", 0.4, [str(part_a), str(part_b)], None)]
        bare_payload = {
            "part_scores": [
                {"part": "i", "marks_awarded": 4, "marks_possible": 7, "rationale": "i"},
                {"part": "ii", "marks_awarded": 5, "marks_possible": 8, "rationale": "ii"},
            ],
            "total_awarded": 9,
            "total_possible": 15,
            "flags": [],
            "confidence": "medium",
        }
        bare_client = _client(bare_payload)
        with patch.object(grading, "_get_client", return_value=bare_client):
            bare_results = grading.grade_batch(bare_unit, bare_qb)
        assert bare_results[0].grading_status == "complete"
        assert bare_results[0].ai_score == 9 and bare_results[0].ai_total_possible == 15
        assert len(bare_results[0].part_scores) == 2

        invalid_payload = {
            "part_scores": [{"part": "", "marks_awarded": 9, "marks_possible": 5, "rationale": "invalid"}],
            "total_awarded": 9,
            "total_possible": 5,
            "flags": [],
            "confidence": "high",
        }
        invalid_client = _client(invalid_payload)
        with patch.object(grading, "_get_client", return_value=invalid_client):
            invalid = grading.grade_batch([QuestionUnit("3a", "attempted", 0.2, [str(part_a)], None)], {"3a": MagicMock(marks_possible=5, key_points="a")})
        assert invalid[0].grading_status == "failed" and invalid[0].ai_score is None
        assert "outside" in (invalid[0].error_message or "")

    print("Grading integrity regression passed: compound evidence, bare-question aggregation, and AI score bounds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
