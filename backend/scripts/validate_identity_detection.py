#!/usr/bin/env python3
"""No-cost acceptance checks for raster-only identity-page detection."""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import pymupdf
from PIL import Image, ImageDraw, ImageFont

from app.services.cover_page_check import identity_page_indexes, looks_like_identity_cover_page


def make_page(path: Path, identity: bool) -> None:
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    if identity:
        lines = ["Name:", "Father Name:", "Roll Number:", "Signature:"]
        for index, line in enumerate(lines):
            draw.text((100, 120 + index * 110), line, fill="black", font=font)
        for row in range(6):
            for col in range(10):
                cx = 150 + col * 90
                cy = 750 + row * 90
                draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), outline="black", width=4)
    else:
        draw.text((100, 180), "Name three causes of friction.", fill="black", font=font)
        draw.text((100, 310), "Write your answer below.", fill="black", font=small)
        for y in range(500, 1400, 90):
            draw.line((100, y, 1100, y), fill=(180, 180, 180), width=2)
    image.save(path)


def pdf_from_image(image_path: Path, pdf_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_image(page.rect, filename=str(image_path))
    doc.save(pdf_path)
    doc.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rubriceye_identity_acceptance_") as directory:
        root = Path(directory)
        identity_png = root / "identity.png"
        normal_png = root / "normal.png"
        identity_pdf = root / "identity.pdf"
        normal_pdf = root / "normal.pdf"
        make_page(identity_png, True)
        make_page(normal_png, False)
        pdf_from_image(identity_png, identity_pdf)
        pdf_from_image(normal_png, normal_pdf)

        identity_detected, _ = looks_like_identity_cover_page(str(identity_png))
        normal_detected, _ = looks_like_identity_cover_page(str(normal_png))
        assert identity_detected, "Raster-only identity cover was not detected."
        assert not normal_detected, "Normal question containing 'Name' was falsely detected."
        assert identity_page_indexes(str(identity_pdf), [str(identity_png)]) == [0]
        assert identity_page_indexes(str(normal_pdf), [str(normal_png)]) == []
    print("Raster-only identity detection acceptance passed; normal question false-positive check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
