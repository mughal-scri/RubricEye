from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import verify_token
from app.config import settings
from app.db.init_db import init_db
from app.routes import answer_sheets, grading, projects, question_bank, question_groups, rubric_studio, template_map
from app.routes.grading import get_job_status
from app.schemas.models import JobStatusResponse
from app.services.grading_worker import grading_worker_loop, recover_stale_jobs
from app.services.storage import ensure_data_dirs

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dirs()
    settings.ensure_token()
    init_db()
    await recover_stale_jobs()

    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(grading_worker_loop(stop_event))
    app.state.grading_worker_stop_event = stop_event
    app.state.grading_worker_task = worker_task

    yield

    stop_event.set()
    await asyncio.wait_for(worker_task, timeout=30)


app = FastAPI(
    title="RubricEye API",
    version="0.2.0",
    lifespan=lifespan,
)

# Phase 2: CORS scoped to known local origins (no wildcard + credentials combo).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 2: token auth applied per-router. Exempt endpoints (/health, /config,
# /files/{path}) are registered directly on the app without the dependency.
_auth = [Depends(verify_token)]
app.include_router(projects.router, dependencies=_auth)
app.include_router(template_map.router, dependencies=_auth)
app.include_router(answer_sheets.router, dependencies=_auth)
app.include_router(grading.router, dependencies=_auth)
app.include_router(question_bank.router, dependencies=_auth)
app.include_router(question_groups.router, dependencies=_auth)
app.include_router(rubric_studio.router, dependencies=_auth)

# Top-level job status endpoint (Phase 1): requires token auth.
app.add_api_route(
    "/jobs/{job_id}", get_job_status,
    response_model=JobStatusResponse,
    methods=["GET"],
    dependencies=_auth,
)


# Top-level endpoints exempt from token auth: /health and /config.
# /health is a simple liveness probe; /config lets the frontend fetch the
# token on first load (CORS restricts who can call it).

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def app_config() -> dict[str, str]:
    """Return non-secret client config. The frontend calls this on startup
    to obtain the API token for authenticated requests."""
    return {"api_token": settings.api_token or ""}


@app.get("/files/{file_path:path}")
def serve_file(
    file_path: str,
    token: str | None = Query(None, alias="token"),
) -> FileResponse:
    base = settings.data_dir.resolve()
    requested = (settings.data_dir / file_path).resolve()
    if requested != base and base not in requested.parents:
        raise HTTPException(status_code=403, detail="Access denied.")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    # Token auth: accept via query param for <img src> and <a href> contexts
    # where custom headers are not available.
    effective_token = token
    if effective_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token.")
    headers = {}
    if requested.suffix.lower() in {".pdf", ".json", ".md"}:
        headers["Content-Disposition"] = f'attachment; filename="{requested.name}"'
    return FileResponse(str(requested), headers=headers)


# Phase 2: /data StaticFiles mount removed. All file access goes through
# /files/{path} which has both the path-traversal guard and token auth.
