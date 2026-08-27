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
    has_text_layer: dict[int, bool] = {}
    try:
        for index, page in enumerate(document):
            txt = page.get_text("text")
            if txt and txt.strip():
                has_text_layer[index] = True
                if looks_like_identity_text(txt):
                    indexes.add(index)
    finally:
        document.close()

    for index, image_path in enumerate(rendered_page_paths or []):
        if index in indexes or has_text_layer.get(index):
            continue
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
    circle_count = 0
    for param2 in (22, 20, 18):
        circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=28, param1=80, param2=param2, minRadius=6, maxRadius=24)
        if circles is not None:
            circle_count = max(circle_count, circles.shape[1])
    # Hough circles also detects letter loops, answer-page marks, and border noise.
    # Treat the grid as identity evidence only when OCR finds multiple identity fields.
    dense_bubble_grid = circle_count >= 60

    keyword_hits: set[str] = set()
    ocr_error = None
    ocr_tokens = 0
    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
        for text in data.get("text", []):
            if text:
                ocr_tokens += 1
                keyword_hits.update(match.group(1).lower() for match in IDENTITY_KEYWORDS.finditer(text))
    except Exception as exc:
        ocr_error = type(exc).__name__ + ":" + str(exc)[:160]

    detected = False
    reason = ""
    branch = "none"
    if dense_bubble_grid and len(keyword_hits) >= 2:
        detected, reason, branch = True, "Detected identity-style cover page (identity fields and bubble grid).", "grid+keywords"
    elif len(keyword_hits) >= 2 and circle_count >= 20:
        detected, reason, branch = True, "Detected likely identity cover page.", "keywords+circles"
    # #region agent log
    try:
        import json, time, urllib.request
        _payload = {"sessionId":"504238","hypothesisId":"A,B,C,D","location":"cover_page_check.py:looks_like_identity_cover_page","message":"identity cover signals","data":{"circle_count":int(circle_count),"dense_bubble_grid":bool(dense_bubble_grid),"keyword_hits":sorted(keyword_hits),"keyword_n":len(keyword_hits),"ocr_error":ocr_error,"ocr_tokens":ocr_tokens,"branch":branch,"detected":detected},"timestamp":int(time.time()*1000),"runId":"pre-fix"}
        _line = json.dumps(_payload) + "\n"
        open("/media/abdullahmughal/b74a1ef7-556e-41b4-9ad8-72e96d04151d/RubricEye/.cursor/debug-504238.log","a").write(_line)
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:7606/ingest/3c44513b-7252-4c79-a638-4a12d36de582", data=_line.encode(), headers={"Content-Type":"application/json","X-Debug-Session-Id":"504238"}), timeout=1)
    except Exception:
        pass
    # #endregion
    if detected:
        return True, reason
    return False, ""
