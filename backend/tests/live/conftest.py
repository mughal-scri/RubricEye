"""Live-fixture conftest.

This directory contains tests that make real DashScope API calls.
They are gated by RUBRICEYE_LIVE_API=1 and are typically run separately
from the offline test suite:

    cd backend && RUBRICEYE_LIVE_API=1 python -m pytest tests/live/ -v -s

The parent conftest.py sets env vars via setdefault, which is fine —
live tests override RUBRICEYE_DATA_DIR and RUBRICEYE_API_TOKEN at
module level before importing the app.
"""
