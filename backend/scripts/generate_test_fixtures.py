#!/usr/bin/env python3
"""Generate minimal test PDFs for Phase 1 manual validation."""

from pathlib import Path

import fitz


def make_blank_booklet(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Q.1 a)", fontsize=12)
    page.draw_rect(fitz.Rect(72, 90, 520, 220), color=(0, 0, 0), width=1)
    page.insert_text((72, 250), "Q.1 b)", fontsize=12)
    page.draw_rect(fitz.Rect(72, 268, 520, 398), color=(0, 0, 0), width=1)
    page.insert_text((72, 430), "Q.2", fontsize=12)
    page.draw_rect(fitz.Rect(72, 448, 520, 620), color=(0, 0, 0), width=1)
    doc.save(path)
    doc.close()


def make_answer_sheet(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((90, 110), "Sample handwritten answer for 1a", fontsize=11)
    page.insert_text((90, 290), "Sample answer for 1b", fontsize=11)
    page.insert_text((90, 470), "Sample answer for Q2", fontsize=11)
    doc.save(path)
    doc.close()


def make_simple_pdf(path: Path, title: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), title, fontsize=14)
    doc.save(path)
    doc.close()


def main() -> None:
    out = Path(__file__).resolve().parent / "test_fixtures"
    out.mkdir(exist_ok=True)
    make_blank_booklet(out / "blank_booklet.pdf")
    make_answer_sheet(out / "answer_sheet.pdf")
    make_simple_pdf(out / "rubric.pdf", "Rubric: Q1(a)=6, Q1(b)=4, Q2=10")
    make_simple_pdf(out / "question_paper.pdf", "Question Paper: Physics Sample")
    print(f"Created fixtures in {out}")


if __name__ == "__main__":
    main()
