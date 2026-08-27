# RubricEye

RubricEye is a privacy-conscious, human-in-the-loop grading prototype for handwritten exam booklets. Its primary analysis uses native vision-language models to understand page layout, handwriting, question structure, and answer content. OCR and deterministic checks complement that visual analysis, while an examiner remains in control of uncertain decisions.

## What it does

- Ingests scanned answer sheets and question papers.
- Detects pages, question regions, alignment, overflow, and booklet correspondence.
- Derives question groups and choice rules from the uploaded document rather than a fixed paper template.
- Uses vision-language models to inspect handwritten answers and their visual context, including crossed-out work and diagrams.
- Uses local ink-density checks to identify blank, attempted, and crossed-out answers before model grading.
- Grades against a locked rubric and produces examiner-reviewable results.
- Keeps identity detection, alignment, crop adjustments, and other low-confidence decisions in an explicit review path.

RubricEye is an assistive tool: model output is evidence for an examiner, not an autonomous final decision.

## Typical workflow

1. Start the local backend and frontend.
2. Create or select a rubric/question paper.
3. Upload an answer booklet.
4. Review page alignment, question mapping, overflow/crop warnings, and inferred choice groups.
5. Confirm or correct any flagged item.
6. Run grading and inspect the report, including the effective denominator after first-N or choice rules.

## Architecture

```text
backend/   FastAPI API, document parsing, alignment, grading, reports
frontend/  React + TypeScript examiner interface
scripts/   Local development and regression helpers
data/      Runtime data (configure a separate location for deployments)
```

The application code is intentionally document-driven. Question numbers, sections, part conventions, coordinates, and totals are read from the uploaded paper/rubric; they are not embedded for one test subject.

## Requirements

- Python 3.11+ (with a virtual environment)
- Node.js 18+ and npm
- Tesseract OCR available on `PATH` (used as a supporting extraction and validation tool)
- Optional: a DashScope/Qwen API key for native vision-language extraction or grading

## Installation

```bash
git clone https://github.com/mughal-scri/RubricEye.git
cd RubricEye

python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt

cd frontend
npm ci
npm run build
cd ..
```

## Configuration

Copy the example environment file if present and set only the values needed for your deployment. Common settings are:

```text
RUBRICEYE_DATA_DIR=/path/to/private/runtime-data
DASHSCOPE_API_KEY=your-key
RUBRICEYE_GRADING_MODEL=qwen-vl-max
RUBRICEYE_STUDIO_MODEL=qwen-vl-max
```

Keep API keys, uploaded papers, answer sheets, and generated reports outside version control. Never commit secrets to the repository.

## Run locally

From the repository root:

```bash
./scripts/run_dev.sh
```

The helper starts the API and web app using the local environment. Use `./scripts/run_dev.sh --electron` when testing the desktop shell. The default development ports are 8765 (API) and 5173 (frontend).

## Testing

Use the project virtual environment for backend checks:

```bash
backend/venv/bin/python -m compileall backend/app
backend/venv/bin/python backend/scripts/validate_hardening_local.py
```

Useful focused regressions include the crop/CRUD, reconciliation, identity-detection, question-bank, first-N, grading-integrity, and report-lifecycle suites under `backend/tests` and `scripts/`. Frontend checks can be run with:

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Some validation helpers invoke paid live-model APIs. Run those only deliberately and with an appropriate budget; the default local suite should remain no-cost and deterministic.

## Privacy and safety

- Runtime files can remain on the local machine.
- Identity signals are excluded from grading prompts and are not sent as unsolicited telemetry.
- API credentials are read from environment variables, not source files.
- Rubrics are locked and changes, confirmations, and corrections are reviewable.
- Alignment, overflow, mapping, and low-confidence attempted-status decisions can be confirmed by an examiner before grading.

## Current limitations

This is a working prototype. Vision-model results depend on scan quality, model availability, and prompt/provider behavior; supporting OCR quality also depends on the local Tesseract installation. Model-assisted extraction or grading requires network access and may incur provider charges. Authentication, multi-tenant permissions, and production deployment hardening are not included by default.

## License and permitted use

The repository is publicly readable, but it is **not open source**. Review and evaluation are permitted under the accompanying [RubricEye Source-Available License](LICENSE). Copying, mirroring, modifying, redistributing, incorporating the code into another product, or commercial/production use requires prior written permission from the copyright holder. Approved use must include attribution.

GitHub can technically allow cloning, forking, or automated retrieval of a public repository; no license can prevent those downloads. The license controls what recipients may legally do with the code after obtaining it.

## Contact

For permission requests, security reports, or collaboration proposals, contact the repository owner through the public contact channel on the author's GitHub profile.

## Project status

RubricEye is a prototype intended for demonstrations, research, and carefully supervised classroom pilots. Contributions or reuse are welcome only with the copyright holder's written approval under the accompanying license.
