from __future__ import annotations

from pathlib import Path

import pymupdf
from fastapi import HTTPException, UploadFile

from app.config import settings


async def read_validated_upload(upload: UploadFile, field_name: str) -> bytes:
    """Read one PDF upload with a bounded read and validate its actual bytes."""
    if not upload.filename or not upload.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a PDF file.")
    data = await upload.read(settings.max_pdf_bytes + 1)
    validate_pdf_bytes(data, field_name)
    return data


def validate_pdf_bytes(data: bytes, field_name: str) -> int:
    """Validate uploaded PDF bytes and return their page count.

    The check is deliberately local and bounded. It rejects extension-only or
    malformed uploads before they can create project/answer-sheet artifacts or
    enter OpenCV/PyMuPDF processing.
    """
    if len(data) > settings.max_pdf_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{field_name} exceeds the {settings.max_pdf_bytes // (1024 * 1024)} MB PDF limit.",
        )
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail=f"{field_name} is not a valid PDF file.")
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — convert parser errors to safe API errors
        raise HTTPException(status_code=400, detail=f"{field_name} could not be opened as a PDF.") from exc
    try:
        page_count = len(document)
    finally:
        document.close()
    if page_count == 0:
        raise HTTPException(status_code=400, detail=f"{field_name} contains no pages.")
    if page_count > settings.max_pdf_pages:
        raise HTTPException(
            status_code=413,
            detail=f"{field_name} exceeds the {settings.max_pdf_pages}-page PDF limit.",
        )
    return page_count


def validate_pdf_path(path: str | Path, field_name: str) -> int:
    """Validate an existing local PDF before a service reopens it."""
    file_path = Path(path)
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} could not be read.") from exc
    return validate_pdf_bytes(data, field_name)
