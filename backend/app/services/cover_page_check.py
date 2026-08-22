from __future__ import annotations

import re

import cv2
import numpy as np
import pymupdf
import pytesseract
from pytesseract import Output

IDENTITY_KEYWORDS = re.compile(r"\b(signature|roll\s*(?:no|number)|candidate\s*(?:id|number)?|father|name|date)\b", re.IGNORECASE)
QUESTION_MARKER = re.compile(r"\bq(?:uestion)?\s*\.?\s*\d+", re.IGNORECASE)


def looks_like_identity_text(text: str) -> bool:
    normalized = " ".join(text.split())
    if not normalized or QUESTION_MARKER.search(normalized):
        return False
    hits = {match.group(1).lower() for match in IDENTITY_KEYWORDS.finditer(normalized)}
    return len(hits) >= 2


def identity_page_indexes(pdf_path: str, rendered_page_paths: list[str] | None = None) -> list[int]:
    """Return identity-page indexes using both PDF text and rendered-image signals.

    Scanned answer books commonly have no PDF text layer, so text-only detection
    is insufficient. Image detection is run on the rendered pages as a second,
    independent privacy signal. A page is excluded if either signal fires.
    """
    try:
        document = pymupdf.open(pdf_path)
    except Exception:
        return []
    indexes: set[int] = set()
    try:
        for index, page in enumerate(document):
            if looks_like_identity_text(page.get_text("text")):
                indexes.add(index)
    finally:
        document.close()

    for index, image_path in enumerate(rendered_page_paths or []):
        detected, _reason = looks_like_identity_cover_page(image_path)
        if detected:
            indexes.add(index)
    return sorted(indexes)


def looks_like_identity_cover_page(image_path: str) -> tuple[bool, str]:
    image = cv2.imread(image_path)
    if image is None:
        return False, ""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=12, param1=80, param2=18, minRadius=4, maxRadius=18)
    circle_count = 0 if circles is None else circles.shape[1]
    dense_bubble_grid = circle_count >= 40

    keyword_hits: set[str] = set()
    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
        for text in data.get("text", []):
            if text:
                keyword_hits.update(match.group(1).lower() for match in IDENTITY_KEYWORDS.finditer(text))
    except Exception:
        pass

    if dense_bubble_grid and keyword_hits:
        return True, "Detected identity-style cover page (bubble grid + identity keywords)."
    if len(keyword_hits) >= 2 and circle_count >= 10:
        return True, "Detected likely identity cover page."
    return False, ""
