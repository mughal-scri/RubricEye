"""Regression tests for the single-variable DashScope key contract.

The app must read the API key from exactly one name, RUBRICEYE_DASHSCOPE_API_KEY,
resolved from (in precedence order) an exported environment variable, then
backend/.env. Offline validation scripts rely on an explicitly empty env var
disabling the key even when backend/.env holds a real one, so that precedence
is locked in here too.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def make_settings(monkeypatch, env_file=None, **env):
    """Build a fresh Settings with all RUBRICEYE_/DASHSCOPE_ vars cleared.

    Args:
        monkeypatch: pytest fixture used to scrub/restore os.environ.
        env_file: dotenv path override (None disables file loading entirely,
            isolating the test from the developer's real backend/.env).
        **env: environment variables to set after the scrub.

    Returns:
        A Settings instance built from only the scrubbed env + overrides.
    """
    for name in list(os.environ):
        if name.startswith("RUBRICEYE_") or name == "DASHSCOPE_API_KEY":
            monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=env_file)


def test_prefixed_env_var_supplies_key(monkeypatch):
    settings = make_settings(monkeypatch, RUBRICEYE_DASHSCOPE_API_KEY="test-key")
    assert settings.dashscope_api_key == "test-key"


def test_legacy_generic_name_is_ignored(monkeypatch):
    # The generic DASHSCOPE_API_KEY name was removed on purpose; if it ever
    # silently comes back, the two-variable confusion returns with it.
    settings = make_settings(monkeypatch, DASHSCOPE_API_KEY="test-key")
    assert settings.dashscope_api_key is None


def test_env_file_supplies_key(tmp_path, monkeypatch):
    env_file = tmp_path / "env"
    env_file.write_text("RUBRICEYE_DASHSCOPE_API_KEY=file-key\n")
    settings = make_settings(monkeypatch, env_file=env_file)
    assert settings.dashscope_api_key == "file-key"


def test_env_var_overrides_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / "env"
    env_file.write_text("RUBRICEYE_DASHSCOPE_API_KEY=file-key\n")
    settings = make_settings(
        monkeypatch, env_file=env_file, RUBRICEYE_DASHSCOPE_API_KEY="env-key"
    )
    assert settings.dashscope_api_key == "env-key"


def test_empty_env_var_disables_env_file_key(tmp_path, monkeypatch):
    # Offline validators export RUBRICEYE_DASHSCOPE_API_KEY="" to force-disable
    # the key; that must win over a real key sitting in backend/.env.
    env_file = tmp_path / "env"
    env_file.write_text("RUBRICEYE_DASHSCOPE_API_KEY=real-key\n")
    settings = make_settings(
        monkeypatch, env_file=env_file, RUBRICEYE_DASHSCOPE_API_KEY=""
    )
    assert settings.dashscope_api_key == ""


def test_env_file_is_anchored_to_backend_dir():
    # The .env path must not depend on the process working directory, or
    # run_dev.sh (which starts uvicorn from the repo root) silently loses
    # the key configured in backend/.env.
    assert Path(Settings.model_config["env_file"]).resolve() == BACKEND_DIR / ".env"


def test_env_prefix_still_applies_to_other_fields(monkeypatch):
    settings = make_settings(monkeypatch, RUBRICEYE_GRADING_MODEL="test-model")
    assert settings.grading_model == "test-model"
