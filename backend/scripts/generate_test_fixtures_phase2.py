#!/usr/bin/env python3
"""Generate test PDFs for Phase 2 manual/automated validation.

Layout (one page):
  Q.1 a) / Q.1 b)  -> compulsory 2-part question (tests batched grading, one API call)
  Q.2 / Q.3 / Q.4  -> choose-2-of-3 group (tests the first-N filter + skip-beyond-N)

Rubric marks: 1a=6, 1b=4, 2=5, 3=5, 4=5  (extracted total = 25)
Question paper states "Total Marks: 25" to match (Edge Case H happy-path check).
"""

from pathlib import Path

import fitz

BOXES = {
    "1a": (72, 90, 520, 200),
    "1b": (72, 220, 520, 330),
    "2": (72, 350, 520, 460),
    "3": (72, 480, 520, 590),
    "4": (72, 610, 520, 720),
}


def make_blank_booklet(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 80), "Q.1 a)", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["1a"]), color=(0, 0, 0), width=1)
    page.insert_text((72, 210), "Q.1 b)", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["1b"]), color=(0, 0, 0), width=1)
    page.insert_text((72, 340), "Q.2", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["2"]), color=(0, 0, 0), width=1)
    page.insert_text((72, 470), "Q.3", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["3"]), color=(0, 0, 0), width=1)
    page.insert_text((72, 600), "Q.4", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["4"]), color=(0, 0, 0), width=1)
    doc.save(path)
    doc.close()


def make_answer_sheet(path: Path) -> None:
    """All five regions attempted (Q3 and Q4 both attempted so the choose-2-of-3
    filter has something real to exclude beyond N=2).

    Draws the SAME box outlines as the blank booklet -- a real scanned answer
    booklet is the same pre-printed pages the student wrote in, so it always has
    these lines. Alignment.py's structural-grid homography needs them to lock
    onto; text with no lines at all (an earlier version of this fixture) gives
    the aligner nothing to match against and produces silently wrong crops.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 80), "Q.1 a)", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["1a"]), color=(0, 0, 0), width=1)
    page.insert_text((90, 130), "Sample handwritten answer text for part 1a, several lines of content here.", fontsize=11)
    page.insert_text((90, 150), "Filling more of the box with additional ink and detail for realism.", fontsize=11)

    page.insert_text((72, 210), "Q.1 b)", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["1b"]), color=(0, 0, 0), width=1)
    page.insert_text((90, 260), "Sample handwritten answer text for part 1b, filling the box with ink.", fontsize=11)
    page.insert_text((90, 280), "A second line of content to raise ink coverage realistically.", fontsize=11)

    page.insert_text((72, 340), "Q.2", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["2"]), color=(0, 0, 0), width=1)
    page.insert_text((90, 390), "Sample handwritten answer for Q2, attempted and legible.", fontsize=11)
    page.insert_text((90, 410), "Additional supporting detail for the answer.", fontsize=11)

    page.insert_text((72, 470), "Q.3", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["3"]), color=(0, 0, 0), width=1)
    page.insert_text((90, 520), "Sample handwritten answer for Q3, also attempted.", fontsize=11)
    page.insert_text((90, 540), "Additional supporting detail for the answer.", fontsize=11)

    page.insert_text((72, 600), "Q.4", fontsize=12)
    page.draw_rect(fitz.Rect(*BOXES["4"]), color=(0, 0, 0), width=1)
    page.insert_text((90, 650), "Sample handwritten answer for Q4, attempted too.", fontsize=11)
    page.insert_text((90, 670), "Additional supporting detail for the answer.", fontsize=11)
    doc.save(path)
    doc.close()


def make_rubric(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = (
        "Q.1\n"
        "Part (a) - 6 marks:\n"
        "  - Correct definition (3 marks)\n"
        "  - Correct example (3 marks)\n"
        "Part (b) - 4 marks:\n"
        "  - Correct method (4 marks)\n"
        "\n"
        "Q.2 (5 marks)\n"
        "  - Full correct explanation required for 5 marks\n"
        "\n"
        "Q.3 (5 marks)\n"
        "  - Full correct explanation required for 5 marks\n"
        "\n"
        "Q.4 (5 marks)\n"
        "  - Full correct explanation required for 5 marks\n"
    )
    page.insert_text((72, 72), text, fontsize=10)
    doc.save(path)
    doc.close()


def make_question_paper(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "Physics Sample Paper\n\nAttempt Q.1 (compulsory) and any TWO of Q.2, Q.3, Q.4.\n\nTotal Marks: 25",
        fontsize=12,
    )
    doc.save(path)
    doc.close()


def main() -> None:
    out = Path(__file__).resolve().parent / "test_fixtures_phase2"
    out.mkdir(exist_ok=True)
    make_blank_booklet(out / "blank_booklet.pdf")
    make_answer_sheet(out / "answer_sheet.pdf")
    make_rubric(out / "rubric.pdf")
    make_question_paper(out / "question_paper.pdf")
    print(f"Created Phase 2 fixtures in {out}")


if __name__ == "__main__":
    main()
