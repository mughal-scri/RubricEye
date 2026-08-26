from __future__ import annotations

import base64
import io
import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image

from app.config import settings
from app.services import grading
from app.services import storage
from app.services.pdf_pipeline import pdf_to_ordered_images
from app.services.rubric_pdf import render_rubric_pdf
from app.services.question_bank_extractor import MIN_TEXT_LAYER_CHARS, extract_question_bank
from app.services.question_grouping import canonical_question_label, sort_question_labels, sort_records_by_question
from app.db.models import QuestionBankItem


STUDIO_SYSTEM_PROMPT = """You are an assessment-rubric drafting assistant. Create a provisional marking rubric from the supplied question paper only.

Return ONLY valid JSON in this shape:
{
  "criteria": [
    {
      "question_number": "the exact printed question number or part label",
      "marks_possible": 0,
      "key_points": "concise examiner-facing criteria and acceptable evidence",
      "section_label": "the exact printed section heading, or null when none exists",
      "question_text": "the question wording, or null when unavailable",
      "provenance": "what question-paper wording supports this criterion",
      "confidence": "high | medium | low"
    }
  ]
}

Do not invent questions, marks, or requirements that are not supported by the paper. If a mark value or criterion is unclear, preserve the question number, use null for marks_possible, explain the uncertainty in key_points, set confidence to low, and leave the item for examiner review. This is a draft only; an examiner must edit and approve every criterion before grading."""


@dataclass
class StudioGenerationResult:
    status: str
    criteria: list[dict]
    warning: str | None = None


def _paper_text(path: str) -> str:
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text("text", sort=True) or "" for page in doc)
    finally:
        doc.close()


def _clean_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):]
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def _text_content(question_paper_path: str) -> tuple[str, bool, bool]:
    text = _paper_text(question_paper_path)
    truncated = len(text) > settings.studio_max_text_chars
    return text[: settings.studio_max_text_chars], len(text.strip()) >= MIN_TEXT_LAYER_CHARS, truncated


def _image_content(question_paper_path: str) -> list[dict]:
    content: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="rubriceye_studio_") as temporary_dir:
        page_paths = pdf_to_ordered_images(question_paper_path, temporary_dir)
        for page_path in page_paths[: settings.studio_max_pages]:
            with Image.open(page_path) as image:
                image = image.convert("RGB")
                if image.width > settings.image_max_width:
                    height = int(image.height * (settings.image_max_width / image.width))
                    image = image.resize((settings.image_max_width, height), Image.LANCZOS)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})
    return content


def _expected_items(question_paper_path: str) -> dict[str, int | None]:
    try:
        extraction = extract_question_bank(question_paper_path)
    except Exception:
        return {}
    return {canonical_question_label(item.question_number): item.marks_possible for item in extraction.items}


def _normalize_criteria(raw: object, expected: dict[str, int | None]) -> tuple[list[dict], list[str]]:
    if not isinstance(raw, list):
        return [], []
    criteria: list[dict] = []
    dropped_question_numbers: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_question_number = str(item.get("question_number", "")).strip()
        question_number = canonical_question_label(raw_question_number)
        if not question_number or question_number in seen:
            continue
        locally_known = not expected or question_number in expected
        if expected and not locally_known:
            dropped_question_numbers.append(question_number)
        raw_marks = item.get("marks_possible")
        marks: int | None
        if locally_known and expected.get(question_number) is not None:
            marks = expected[question_number]
        elif isinstance(raw_marks, int) and raw_marks >= 0:
            marks = raw_marks
        else:
            marks = None
        key_points = str(item.get("key_points", "")).strip()
        if not key_points:
            key_points = "Generated criterion is missing; examiner must complete it before approval."
        confidence = str(item.get("confidence", "low")).lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        provenance = str(item.get("provenance", "Question paper wording")).strip() or "Question paper wording"
        if not locally_known:
            confidence = "low"
            provenance = f"{provenance}; local label extraction could not confirm this criterion — examiner review required"
        section_label = str(item.get("section_label", "")).strip() or None
        question_text = str(item.get("question_text", "")).strip() or None
        criteria.append({
            "question_number": question_number,
            "marks_possible": marks,
            "key_points": key_points,
            "section_label": section_label,
            "question_text": question_text,
            "rubric_provenance": provenance,
            "rubric_confidence": confidence,
            "rubric_reviewed": False,
        })
        seen.add(question_number)
    return sort_records_by_question(criteria, lambda criterion: criterion["question_number"]), dropped_question_numbers


def materialize_draft(project, criteria: list[dict], db, approved: bool = False) -> None:
    """Persist a user-reviewed preview into normal QuestionBankItem rows."""
    ordered_criteria = sort_records_by_question(criteria, lambda criterion: criterion["question_number"])
    project_dir = storage.project_dir(project.id)
    storage_payload = {"status": "approved" if approved else "draft_ready", "criteria": ordered_criteria}
    storage.atomic_write_json(project_dir / "rubric_studio_draft.json", storage_payload)
    render_rubric_pdf(Path(project.rubric_file_path), project_name=project.name, source_label="Rubric Studio · examiner-reviewed draft", criteria=ordered_criteria)
    db.query(QuestionBankItem).filter(QuestionBankItem.project_id == project.id).delete()
    for criterion in ordered_criteria:
        db.add(QuestionBankItem(
            id=str(uuid.uuid4()),
            project_id=project.id,
            question_number=criterion["question_number"],
            marks_possible=criterion.get("marks_possible"),
            key_points=criterion.get("key_points"),
            section_label=criterion.get("section_label"),
            question_text=criterion.get("question_text"),
            rubric_provenance=criterion.get("rubric_provenance", "Question paper wording"),
            rubric_confidence=criterion.get("rubric_confidence", "low"),
            rubric_reviewed=bool(criterion.get("rubric_reviewed", False)),
            alignment_question_number=criterion.get("alignment_question_number"),
            alignment_status=criterion.get("alignment_status", "unreviewed"),
        ))
    project.rubric_studio_status = "approved" if approved else "draft_ready"
    project.rubric_locked = approved
    project.question_bank_confirmed = False
    db.commit()


def generate_draft(question_paper_path: str) -> StudioGenerationResult:
    """Generate one provisional paper rubric; failure always leaves the upload path available."""
    client = grading._get_client()
    if client is None:
        return StudioGenerationResult("manual_required", [], "Rubric Studio needs a configured provider key. Upload an existing rubric or configure the key and retry.")

    text, has_text, truncated = _text_content(question_paper_path)
    if truncated:
        return StudioGenerationResult("manual_required", [], f"The question paper exceeds the {settings.studio_max_text_chars} character Studio text limit. Upload an official rubric or use the manual rubric path instead.")
    expected = _expected_items(question_paper_path)
    user_content: list[dict] = []
    if has_text:
        user_content.append({"type": "text", "text": f"QUESTION PAPER:\n{text}\n\nDraft criteria for every question or part visible in this paper."})
    else:
        with fitz.open(question_paper_path) as paper:
            page_count = len(paper)
        if page_count > settings.studio_max_pages:
            return StudioGenerationResult("manual_required", [], f"This scanned question paper has {page_count} pages, above the Studio image limit of {settings.studio_max_pages}. Upload an official rubric or use the manual rubric path instead.")
        user_content.append({"type": "text", "text": "QUESTION PAPER IMAGES FOLLOW. Read the printed questions and marks from the pages, then draft criteria for every question or part visible."})
        user_content.extend(_image_content(question_paper_path))

    try:
        response = client.chat.completions.create(
            model=settings.studio_model,
            messages=[
                {"role": "system", "content": STUDIO_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        raw = response.choices[0].message.content or ""
        parsed = _clean_json(raw)
        criteria, dropped_question_numbers = _normalize_criteria(parsed.get("criteria"), expected)
    except Exception as exc:  # API and parse errors remain recoverable through manual upload.
        return StudioGenerationResult("manual_required", [], f"Rubric Studio could not complete this draft: {exc}. Upload an existing rubric instead.")

    expected_numbers = set(expected)
    generated_numbers = {criterion["question_number"] for criterion in criteria}
    missing = sort_question_labels(list(expected_numbers - generated_numbers))
    diagnostics: list[str] = []
    if dropped_question_numbers:
        dropped = sort_question_labels(dropped_question_numbers)
        preview = ", ".join(dropped[:8])
        suffix = " …" if len(dropped) > 8 else ""
        diagnostics.append(f"{len(dropped)} provider criterion(s) were not confirmed by local label extraction and were preserved for examiner review: {preview}{suffix}.")
    if missing:
        diagnostics.append(f"The draft is partial; these paper questions still need manual criteria: {', '.join(missing)}.")
    warning = " ".join(diagnostics) or None
    if not criteria:
        return StudioGenerationResult("manual_required", [], warning or "No usable rubric criteria were generated. Upload an existing rubric instead.")
    if missing:
        return StudioGenerationResult("partial", criteria, warning)
    return StudioGenerationResult("draft_ready", criteria, warning)
