"""Ports mini_grader.py's validated grading logic into a reusable backend service.

Batching strategy (not specified by the Phase 2 plan — see PHASE2_NOTES.md):
Grading units that belong to the same COMPULSORY QuestionGroup are batched into a
single API call together (this is what TechDoc §7's "one call per question, e.g. Q3
parts a+b together" example actually describes generalized past a single question).
Units in a choose-N-of-M group, or with no group at all, are graded one call each,
since only some of them survive the first-N filter and each is independently scored.

The SYSTEM_PROMPT below is copied VERBATIM from mini_grader.py — this is a locked
decision (HANDOVER.md): the diagram/prose fairness rule and crossed-out-answer rule
must not be dropped or reworded in any rewrite.
"""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from openai import OpenAI

from app.config import settings
from app.services.first_n_filter import QuestionUnit
from app.services.question_grouping import split_base_and_part

MODEL = settings.grading_model

# Copied verbatim from mini_grader.py — DO NOT reword. See HANDOVER.md.
SYSTEM_PROMPT = """You are grading a student's handwritten exam answer for a structured,
board-style exam. You will be shown one or more pages that
together form ONE continuous answer. Read all pages as a single answer, in
page order.

Grade strictly against the rubric provided. Do not give credit for a rule or
formula being stated if the worked example, substitution, or final answer
attached to it is wrong or incoherent. Check final numeric answers for
physical plausibility, not just presence of a formula.

IMPORTANT — crossed-out or abandoned answers still count as an attempt:
If a region contains an answer the student has fully struck through or
crossed out, this counts as an attempted answer, not a skipped one. Score
it 0 marks — do not search for a "better" answer elsewhere and do not treat
it as blank. Only a region with genuinely no content (nothing ever written)
counts as not attempted. Word-level or phrase-level corrections within an
otherwise valid answer (a single crossed-out word, rewritten inline) are
normal editing, not abandonment — grade the remaining legible answer
normally in that case.

IMPORTANT — judge on conceptual correctness, not format:
Students express correct understanding differently. A student may answer
using a diagram, flowchart, sketch, or equation instead of prose, even when
the question doesn't explicitly request one. If a diagram or flowchart
correctly conveys the concept the rubric requires, award full credit as you
would for an equivalent correct written answer. Do NOT flag an answer merely
for being non-textual or unconventional in form. Only flag genuine issues:
illegibility, factual/conceptual incorrectness, ambiguity about which
question it answers, or missing required content — never flag "this is a
diagram instead of text" as an issue on its own.

Return ONLY valid JSON in this exact structure:
{
  "transcription_summary": "brief summary of what each page contains",
  "part_scores": [
    {"part": "a", "marks_awarded": 0, "marks_possible": 6, "rationale": "..."},
    {"part": "b", "marks_awarded": 0, "marks_possible": 4, "rationale": "..."}
  ],
  "total_awarded": 0,
  "total_possible": 10,
  "flags": ["list any ambiguity, illegibility, mislabeling, or structural issues"],
  "confidence": "high | medium | low"
}
"""


@dataclass
class GradedUnitResult:
    question_number: str
    ai_score: int | None
    ai_total_possible: int | None
    ai_rationale: str | None
    part_scores: list[dict]
    transcription_summary: str | None
    flags: list[str]
    confidence: str
    grading_status: str  # complete | failed
    error_message: str | None = None


def _get_client() -> OpenAI | None:
    api_key = settings.dashscope_api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url=settings.dashscope_base_url)


def encode_image(path: str, max_width: int | None = None) -> str:
    max_width = max_width or settings.image_max_width
    with Image.open(path) as img:
        img = img.convert("RGB")
        if img.width > max_width:
            new_height = int(img.height * (max_width / img.width))
            img = img.resize((max_width, new_height), Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def build_batches(units: list[QuestionUnit], question_groups: list[dict]) -> list[list[QuestionUnit]]:
    groups_by_id = {g["id"]: g for g in question_groups}
    compulsory_batches: dict[str, list[QuestionUnit]] = {}
    batches: list[list[QuestionUnit]] = []

    for unit in units:
        group = groups_by_id.get(unit.group_id) if unit.group_id else None
        if group and group["selection_type"] == "compulsory":
            compulsory_batches.setdefault(unit.group_id, []).append(unit)
        else:
            batches.append([unit])

    for members in compulsory_batches.values():
        members.sort(key=lambda u: split_base_and_part(u.question_number))
        batches.append(members)

    return batches


def _build_prompt_text(batch: list[QuestionUnit], qb_items_by_number: dict) -> str:
    question_lines = []
    rubric_lines = []
    for unit in batch:
        item = qb_items_by_number[unit.question_number]
        base, part = split_base_and_part(unit.question_number)
        label = f"Part ({part})" if part else f"Q.{base}"
        marks = item.marks_possible if item.marks_possible is not None else "unknown"
        question_lines.append(f"{label} ({marks} marks)")
        rubric_lines.append(f"{label} - {marks} marks:\n{item.key_points or '(no key points recorded)'}")

    question_text = f"Q.{split_base_and_part(batch[0].question_number)[0]}\n" + "\n".join(question_lines)
    rubric_text = "\n".join(rubric_lines)
    return (
        f"QUESTION:\n{question_text}\n\nRUBRIC:\n{rubric_text}\n\n"
        f"Grade the following pages (one continuous answer per part shown, in order):"
    )


def _sentinel_error(units: list[QuestionUnit], message: str) -> list[GradedUnitResult]:
    return [
        GradedUnitResult(
            question_number=unit.question_number,
            ai_score=None,
            ai_total_possible=None,
            ai_rationale=None,
            part_scores=[],
            transcription_summary=None,
            flags=[f"grading_error: {message}"],
            confidence="low",
            grading_status="failed",
            error_message=message,
        )
        for unit in units
    ]


def _match_part_score(unit: QuestionUnit, part_scores: list[dict]) -> dict | None:
    _, part = split_base_and_part(unit.question_number)
    if len(part_scores) == 1:
        return part_scores[0]
    if not part:
        return part_scores[0] if part_scores else None
    for ps in part_scores:
        if str(ps.get("part", "")).strip().lower().strip("().") == part:
            return ps
    return None


def grade_batch(batch: list[QuestionUnit], qb_items_by_number: dict) -> list[GradedUnitResult]:
    client = _get_client()
    if client is None:
        return _sentinel_error(batch, "DASHSCOPE_API_KEY is not configured")

    image_paths: list[str] = []
    for unit in batch:
        image_paths.extend(unit.image_paths)
    if not image_paths:
        return _sentinel_error(batch, "no region images found for this question")

    content: list[dict] = [{"type": "text", "text": _build_prompt_text(batch, qb_items_by_number)}]
    try:
        for path in image_paths:
            b64 = encode_image(path)
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        )
        raw = response.choices[0].message.content or ""
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
    except Exception as exc:  # noqa: BLE001 — API/parse failures must never crash the request
        return _sentinel_error(batch, str(exc))

    part_scores = parsed.get("part_scores", [])
    flags = parsed.get("flags", []) or []
    confidence = parsed.get("confidence", "low")

    # TechDoc §7 known-bug fix (HANDOVER.md): confidence must not stay "high" when
    # flags are present. Downgrade at the point of ingestion, not left to the UI.
    if flags and confidence == "high":
        confidence = "medium"

    transcription_summary = parsed.get("transcription_summary")
    results: list[GradedUnitResult] = []

    for unit in batch:
        matched = _match_part_score(unit, part_scores)
        if matched is None:
            results.append(
                GradedUnitResult(
                    question_number=unit.question_number,
                    ai_score=None,
                    ai_total_possible=None,
                    ai_rationale=None,
                    part_scores=[],
                    transcription_summary=transcription_summary,
                    flags=flags + ["no matching part in AI response for this question"],
                    confidence="low",
                    grading_status="failed",
                    error_message="unmatched part in batched response",
                )
            )
            continue

        results.append(
            GradedUnitResult(
                question_number=unit.question_number,
                ai_score=matched.get("marks_awarded"),
                ai_total_possible=matched.get("marks_possible"),
                ai_rationale=matched.get("rationale"),
                part_scores=[matched],
                transcription_summary=transcription_summary,
                flags=list(flags),
                confidence=confidence,
                grading_status="complete",
            )
        )

    return results


def grade_units(units: list[QuestionUnit], qb_items_by_number: dict, question_groups: list[dict]) -> list[GradedUnitResult]:
    """Entry point: batches units per compulsory-group rules, grades each batch,
    and returns a flat list of per-question results in the same order as `units`.
    """
    batches = build_batches(units, question_groups)
    all_results: list[GradedUnitResult] = []
    for batch in batches:
        all_results.extend(grade_batch(batch, qb_items_by_number))
    return all_results
