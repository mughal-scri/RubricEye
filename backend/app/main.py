from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.init_db import init_db
from app.routes import answer_sheets, projects, template_map
from app.services.storage import ensure_data_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dirs()
    init_db()
    yield


app = FastAPI(title="RubricEye API", version="0.1.0", lifespan=lifespan)

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/files/{file_path:path}")
def serve_file(file_path: str) -> FileResponse:
    base = settings.data_dir.resolve()
    requested = (settings.data_dir / file_path).resolve()
    if not str(requested).startswith(str(base)):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(str(requested))


if settings.data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(settings.data_dir)), name="data")
