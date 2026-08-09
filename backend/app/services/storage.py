import json
import os
import shutil
from pathlib import Path
from typing import Any

from app.config import settings


def ensure_data_dirs() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.projects_dir.mkdir(parents=True, exist_ok=True)


def project_dir(project_id: str) -> Path:
    path = settings.projects_dir / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def answer_sheet_dir(project_id: str, answer_sheet_id: str) -> Path:
    path = project_dir(project_id) / "answer_sheets" / answer_sheet_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def blank_booklet_images_dir(project_id: str) -> Path:
    path = project_dir(project_id) / "blank_booklet_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_bytes(dest: Path, data: bytes) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    return dest


def atomic_write_text(dest: Path, text: str, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(dest, text.encode(encoding))


def atomic_write_json(dest: Path, payload: Any) -> Path:
    return atomic_write_text(dest, json.dumps(payload, indent=2))


def save_upload(dest: Path, file_bytes: bytes) -> Path:
    return atomic_write_bytes(dest, file_bytes)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_file_atomic(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)
    return dest
