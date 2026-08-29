"""Shared pytest configuration for RubricEye backend tests (Phase 4).

Sets environment variables BEFORE any app imports so that the database
engine, config settings, and auth token all resolve to test-safe values.
Also adds backend/scripts/ to sys.path for legacy helper imports.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# --- Environment setup (must precede all app imports) ---
_TEST_DATA_DIR = os.environ.setdefault(
    "RUBRICEYE_DATA_DIR", tempfile.mkdtemp(prefix="rubriceye_pytest_")
)
os.environ.setdefault("RUBRICEYE_DASHSCOPE_API_KEY", "fake-key-for-offline-tests")
# Override any external token (e.g. CI's RUBRICEYE_API_TOKEN) so the test
# client and the app always share the same deterministic token.
os.environ["RUBRICEYE_API_TOKEN"] = "test-token-for-offline-tests"

# Legacy scripts path (some validate_*.py helpers are imported by name).
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# --- Constants used across test files ---
TEST_AUTH_HEADERS = {"Authorization": "Bearer test-token-for-offline-tests"}
