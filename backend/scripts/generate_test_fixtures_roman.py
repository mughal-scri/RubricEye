#!/usr/bin/env python3
"""Generates fixtures for validate_roman_numeral_parts.py -- a Q2-style question
with seven roman-numeral sub-parts (i-vii), matching the real structure found in
Abdullah's RubricEye_MockExam_Question_Paper.pdf during Phase 3 material review.
"""

from pathlib import Path

import fitz

PARTS = ["i", "ii", "iii", "iv", "v", "vi", "vii"]
Y_START = 80
ROW_H = 100


def make_booklet(path: Path, with_answers: bool) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for idx, part in enumerate(PARTS):
        y = Y_START + idx * ROW_H
        page.insert_text((72, y), f"Q2({part})", fontsize=11)
        page.draw_rect(fitz.Rect(72, y + 10, 520, y + ROW_H - 15), color=(0, 0, 0), width=1)
        if with_answers:
            page.insert_text((90, y + 32), f"Answer content for part {part}, attempted and legible.", fontsize=9)
            page.insert_text((90, y + 48), f"A second supporting line of handwriting for part {part}.", fontsize=9)
            page.insert_text((90, y + 64), "Additional detail to raise ink coverage realistically.", fontsize=9)
    doc.save(path)
    doc.close()


def make_rubric(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    lines = ["Q2"] + [f"{part}. Rubric for part {part} - 4 marks" for part in PARTS]
    page.insert_text((72, 72), "\n".join(lines), fontsize=10)
    doc.save(path)
    doc.close()


def make_question_paper(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    lines = ["Q2: Attempt Only 5 Questions."] + [f"{part}. ... [4]" for part in PARTS] + ["", "Maximum Marks: 20"]
    page.insert_text((72, 72), "\n".join(lines), fontsize=10)
    doc.save(path)
    doc.close()


def main() -> None:
    out = Path(__file__).resolve().parent / "test_fixtures_roman"
    out.mkdir(exist_ok=True)
    make_booklet(out / "blank_booklet.pdf", with_answers=False)
    make_booklet(out / "answer_sheet.pdf", with_answers=True)
    make_rubric(out / "rubric.pdf")
    make_question_paper(out / "question_paper.pdf")
    print(f"Created roman-numeral fixtures in {out}")


if __name__ == "__main__":
    main()
