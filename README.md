# RubricEye

A vision-native AI grading assistant for structured, handwritten exam answer booklets — built to work with **any institution's answer sheet format**, not tied to a specific exam board.

RubricEye reads a scanned answer booklet directly (text *and* diagrams, in a single pass), drafts a rubric-based score with reasoning per question, and flags anything genuinely uncertain for a human examiner's final confirmation. It never grades autonomously — human sign-off is a fixed part of the workflow, not an optional feature.

## Why This Exists

Manual grading of handwritten exams is slow and inconsistent — the same answer quality can score differently depending on who checks it. RubricEye targets that consistency problem at the institutional level (exam boards, schools) rather than trying to replace examiners.

## Core Design Principles

- **Human-in-the-loop, always.** The AI drafts a score; a human examiner confirms it. No result is final without that step.
- **Board-agnostic.** A project’s answer-region layout is semantically derived from the uploaded blank booklet’s own PDF anchors/vector geometry, with a vision fallback for flattened or scanned booklets; it is not hardcoded to one institution’s format.
- **Rubric integrity.** Once a project is created, its rubric is locked — no one can change grading criteria mid-batch.
- **Leak-proof by design.** No identity-bearing content is ever sent to the external AI provider.
- **Cost-conscious.** Grading is batched per question (not per page), keeping API usage realistic at real-world volume.
- **Format-fair judgment.** A correct answer expressed as a diagram or flowchart is scored on concept, not penalized for not being prose.

## Status

**Core infrastructure and Phase 2 grading integration are implemented.** The current build also includes semantic template derivation from each uploaded booklet’s own PDF anchors and vector geometry, a vision fallback contract for arbitrary layouts, learned front-matter/identity-page exclusion, validated scan-to-template feature registration, overflow-aware crops, confidence gating, alignment repairs, score-bound validation, question-group validation, project-creation failure recording, soft-delete/Trash recovery, explicit `review_required` sheet status, and evidence-first human review.

The follow-up workflow now distinguishes raw extracted marks from the effective candidate maximum for optional sections, persists compound choice units, locks blank and beyond-limit answers as local decisions, keeps ambiguous ink states examiner-resolvable, and produces persistent downloadable examiner-report PDFs after confirmation. Project creation is staged as question paper → blank booklet → rubric source → confirmation, with official PDF, pasted text, and Rubric Studio options. Ordinary booklet review presents a page-by-page label summary rather than coordinate boundaries. The optional-section parser is document-derived rather than tied to a literal section name and accepts varied exam wording. Question Bank and Rubric Studio criteria editors expand to their content instead of remaining fixed-height.

**Phase C Rubric Studio is implemented as an explicit opt-in path and as a standalone worker.** It makes one user-triggered provider call from the selected question paper, uses text first and page-image fallback for scanned papers, shows provenance and confidence for every provisional criterion, lets the examiner edit the ordered criteria without per-question confirmation checkboxes, exports the edited result as a structured PDF, and locks only after the complete draft is saved. Official PDF and pasted-text paths remain available whenever generation is unavailable or partial.

The remaining intentionally separate validation is a controlled end-to-end run against real handwritten answer booklets using a provider key. Synthetic and mocked validation are useful regression checks, but they do not replace inspecting real template maps, segmentation crops, ink-density ratios, overflow signals, and grading quality. The Studio model is configurable through `RUBRICEYE_STUDIO_MODEL`; no key or provider call is required for local validation.

## Documentation

Start here, in this order:

| File | Purpose |
|---|---|
| `RubricEye_PRD.md` | What the product does and why — functional & non-functional requirements |
| `RubricEye_Architecture.md` | System design, data flow, component diagram |
| `RubricEye_TechDoc.md` | Technical spec — data models, API design, storage layout |
| `RubricEye_Roadmap.md` | Build phases, in order, with concrete checklist items |
| `RubricEye_FutureAdditions.md` | Deliberately deferred features (multi-user, hosted deployment, branding) — not missing, just not now |

## Tech Stack

- **Frontend:** Electron + React
- **Backend:** Python + FastAPI
- **Storage:** SQLite (WAL mode) + local filesystem
- **PDF processing:** PyMuPDF
- **Grading engine:** Alibaba Cloud Qwen-VL-Max (DashScope, OpenAI-compatible API)
- **Studio vision engine:** Alibaba Cloud Model Studio `qwen3.7-plus` by default, configured independently so graphical/scanned question-paper drafting can use multimodal input without changing the grading model.

## Getting Started

```bash
git clone <repo-url>
cd rubriceye

# Backend dependencies
sudo uv pip install --system -r backend/requirements.txt

# Frontend
cd frontend
npm ci --no-audit --no-fund
npm run build

# Only for intentional real-model validation; never commit the key
export DASHSCOPE_API_KEY="your_key_here"
```

See `RubricEye_TechDoc.md` for the full API and data model before writing backend routes — the schema is deliberately fixed up front (rubric locking, region maps, human-confirmation fields) and shouldn't drift from it without updating the doc first.

## Testing

Run the no-cost regression loops from the repository root:

```bash
PYTHONPATH=backend python3 backend/scripts/validate_hardening_local.py
PYTHONPATH=backend python3 backend/scripts/validate_unlock_and_delete.py
PYTHONPATH=backend python3 backend/scripts/validate_roman_numeral_parts.py
PYTHONPATH=backend python3 backend/scripts/validate_real_template.py
PYTHONPATH=backend python3 backend/scripts/validate_real_segmentation.py
PYTHONPATH=backend python3 backend/scripts/validate_real_original_upload.py
PYTHONPATH=backend python3 backend/scripts/validate_identity_detection.py
PYTHONPATH=backend python3 backend/scripts/validate_paper_structure.py
PYTHONPATH=backend python3 backend/scripts/validate_generic_paper_structure.py
PYTHONPATH=backend python3 backend/scripts/validate_question_bank_effective_api.py
PYTHONPATH=backend python3 backend/scripts/validate_rubric_studio.py
PYTHONPATH=backend python3 backend/scripts/validate_rubric_sources.py
PYTHONPATH=backend python3 backend/scripts/validate_frontend_source_guards.py
(cd frontend && npx tsc --noEmit && npm run build)
PYTHONPATH=backend python3 backend/scripts/validate_unattempted_lock.py
PYTHONPATH=backend python3 backend/scripts/validate_report_lifecycle.py
PYTHONPATH=backend python3 backend/scripts/validate_phase1.py
(cd frontend && npm ci --no-audit --no-fund && npx tsc --noEmit && npm run build)
```

These loops cover backend hardening without billed model calls. The real-template loop validates the supplied blank booklet’s semantic labels and 11 answer regions. Set `RUBRICEYE_REAL_FIXTURES_DIR` to the directory containing the blank booklet, question paper, rubric, and answer books before running the portable real-material loops. The real-segmentation loop strips identity covers and checks all three supplied answer books for mapped region coverage, preview generation, and overflow signals; it does not grade. The original-upload loop uploads the original PDFs unchanged and verifies that identity/front-matter pages are excluded locally while page indexes remain aligned; it also does not grade. The identity-detection loop verifies a raster-only cover is excluded while a normal question containing the word “Name” is not falsely excluded. `backend/scripts/validate_phase2.py` intentionally uses real Qwen-VL-Max calls and should be run only after these local loops pass and a real API test is desired. Before submission, run the complete workflow against the three sanitized handwritten booklets and record the results.

## License

TBD.
