from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.init_db import init_db
from app.routes import answer_sheets, grading, projects, question_bank, question_groups, rubric_studio, template_map
from app.services.storage import ensure_data_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dirs()
    init_db()
    yield


app = FastAPI(title="RubricEye API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(template_map.router)
app.include_router(answer_sheets.router)
app.include_router(grading.router)
app.include_router(question_bank.router)
app.include_router(question_groups.router)
app.include_router(rubric_studio.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/files/{file_path:path}")
def serve_file(file_path: str) -> FileResponse:
    base = settings.data_dir.resolve()
    requested = (settings.data_dir / file_path).resolve()
    if requested != base and base not in requested.parents:
        raise HTTPException(status_code=403, detail="Access denied.")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    headers = {}
    if requested.suffix.lower() in {".pdf", ".json", ".md"}:
        headers["Content-Disposition"] = f'attachment; filename="{requested.name}"'
    return FileResponse(str(requested), headers=headers)


if settings.data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(settings.data_dir)), name="data")
