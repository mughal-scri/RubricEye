# RubricEye

A vision-native AI grading assistant for structured, handwritten exam answer booklets — built to work with **any institution's answer sheet format**, not tied to a specific exam board.

RubricEye reads a scanned answer booklet directly (text *and* diagrams, in a single pass), drafts a rubric-based score with reasoning per question, and flags anything genuinely uncertain for a human examiner's final confirmation. It never grades autonomously — human sign-off is a fixed part of the workflow, not an optional feature.

## Why This Exists

Manual grading of handwritten exams is slow and inconsistent — the same answer quality can score differently depending on who checks it. RubricEye targets that consistency problem at the institutional level (exam boards, schools) rather than trying to replace examiners.

## Core Design Principles

- **Human-in-the-loop, always.** The AI drafts a score; a human examiner confirms it. No result is final without that step.
- **Board-agnostic.** A project's answer-region layout is *derived* from an uploaded blank booklet at setup time, not hardcoded to one institution's format.
- **Rubric integrity.** Once a project is created, its rubric is locked — no one can change grading criteria mid-batch.
- **Leak-proof by design.** No identity-bearing content is ever sent to the external AI provider.
- **Cost-conscious.** Grading is batched per question (not per page), keeping API usage realistic at real-world volume.
- **Format-fair judgment.** A correct answer expressed as a diagram or flowchart is scored on concept, not penalized for not being prose.

## Status

**Feasibility stage complete.** Core architecture validated with real API calls against Alibaba Cloud's Qwen-VL-Max — see `mini_grader.py` for the working proof-of-concept grading script. Currently entering Phase 1 (core infrastructure) per the roadmap below.

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

## Getting Started

```bash
git clone <repo-url>
cd rubriceye

# Backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set your API key (never commit this)
export DASHSCOPE_API_KEY="your_key_here"

# Frontend
cd frontend
npm install
```

See `RubricEye_TechDoc.md` for the full API and data model before writing backend routes — the schema is deliberately fixed up front (rubric locking, region maps, human-confirmation fields) and shouldn't drift from it without updating the doc first.

## Testing Philosophy

Per project decision, comprehensive automated testing is deferred until the core upload → segment → grade → confirm workflow is wired end-to-end — not skipped, just sequenced later. In the meantime, validate manually against real handwritten test booklets (not synthetic data) filled out by real people, to surface genuine handwriting variance, mislabeling, and edge cases synthetic data won't produce.

## License

TBD.
