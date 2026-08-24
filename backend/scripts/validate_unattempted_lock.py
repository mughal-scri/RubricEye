#!/usr/bin/env python3
"""Verify blank answers are excluded and compound choices are selected as one unit."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from app.services.first_n_filter import apply_first_n_filter
from app.services.ink_density import InkDensityResult
from app.services.segmentation import safe_region_filename_key


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rubriceye_unattempted_") as directory:
        regions = Path(directory)
        keys = ["2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii", "3a", "3b", "4a", "4b"]
        for key in keys:
            (regions / f"{safe_region_filename_key(key)}_p2.png").write_bytes(b"fixture")

        def classify(paths: list[str], *_args):
            name = Path(paths[0]).name
            if name.startswith(f"{safe_region_filename_key('2i')}_"):
                return InkDensityResult("blank", 0.0)
            return InkDensityResult("attempted", 0.1)

        groups = [
            {
                "id": "b",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["2i", "2ii", "2iii", "2iv", "2v", "2vi", "2vii"],
                "selection_units": [["2i"], ["2ii"], ["2iii"], ["2iv"], ["2v"], ["2vi"], ["2vii"]],
                "n_required": 5,
            },
            {
                "id": "c",
                "selection_type": "choose_n_of_m",
                "question_numbers": ["3a", "3b", "4a", "4b"],
                "selection_units": [["3a", "3b"], ["4a", "4b"]],
                "n_required": 1,
            },
        ]
        with patch("app.services.first_n_filter.ink_density.classify_unit", side_effect=classify):
            result = apply_first_n_filter({key: [{}] for key in keys}, regions, keys, groups)

        assert result.skipped_blank == ["2i"], result
        assert result.skipped_beyond_n == ["2vii", "4a", "4b"], result
        assert [unit.question_number for unit in result.to_grade] == ["2ii", "2iii", "2iv", "2v", "2vi", "3a", "3b"], result
        print("Unattempted-lock regression passed: blank answers do not consume choice slots and compound choices stay together.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
