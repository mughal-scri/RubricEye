from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract
from pytesseract import Output


IDENTITY_KEYWORDS = re.compile(r"(signature|roll\s*no|candidate|father|name)", re.IGNORECASE)


def looks_like_identity_cover_page(image_path: str) -> tuple[bool, str]:
    image = cv2.imread(image_path)
    if image is None:
        return False, ""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=12,
        param1=80,
        param2=18,
        minRadius=4,
        maxRadius=18,
    )
    circle_count = 0 if circles is None else circles.shape[1]
    dense_bubble_grid = circle_count >= 40

    keyword_hits = 0
    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
        for text in data.get("text", []):
            if text and IDENTITY_KEYWORDS.search(text):
                keyword_hits += 1
    except Exception:
        pass

    if dense_bubble_grid and keyword_hits >= 1:
        return True, "Detected identity-style cover page (bubble grid + identity keywords)."
    if keyword_hits >= 2 and circle_count >= 20:
        return True, "Detected likely identity cover page."
    return False, ""
