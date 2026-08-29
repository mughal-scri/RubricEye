"""Live-fixture conftest.

This directory contains tests that make real DashScope API calls.
They are gated by RUBRICEYE_LIVE_API=1 and are typically run separately
from the offline test suite:

    cd backend && RUBRICEYE_LIVE_API=1 python -m pytest tests/live/ -v -s

The parent conftest.py sets env vars via setdefault, which is fine —
live tests override RUBRICEYE_DATA_DIR and RUBRICEYE_API_TOKEN at
module level before importing the app.
"""

from __future__ import annotations

import os

# Live test modules override RUBRICEYE_API_TOKEN and RUBRICEYE_DATA_DIR at
# module level and then import the app, so merely COLLECTING them during an
# offline run bakes the live token into the shared settings singleton and
# every later offline test fails auth with 401. Exclude them from collection
# entirely unless live mode is enabled; the per-test skipif alone is not
# enough because import-time side effects run regardless of skip status.
if os.environ.get("RUBRICEYE_LIVE_API", "").strip() != "1":
    collect_ignore_glob = ["test_*.py"]
