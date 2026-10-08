"""
Pytest configuration file.

This file ensures that the project root is in the Python path,
allowing tests to import from the api and open_notebook modules.
"""

import os
import sys
from pathlib import Path

# Ensure password auth is disabled for tests BEFORE any imports
# The PasswordAuthMiddleware skips auth when this env var is not set
# Set to empty string instead of deleting to prevent it from being reloaded
os.environ["OPEN_NOTEBOOK_PASSWORD"] = ""

# Load environment variables from .env file
# This must be done BEFORE any imports that depend on environment variables
from dotenv import load_dotenv

# Load .env file from project root
dotenv_path = Path(__file__).parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f"Loaded environment variables from {dotenv_path}")
else:
    print(f"Warning: .env file not found at {dotenv_path}")

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def stage_writes(request, monkeypatch):
    """Record ingestion stage writes instead of sending them to a database.

    Tests that exercise the real writes mark themselves `real_stage_writes`.
    Each recorded call is (source_id, stage, fields).
    """
    if "real_stage_writes" in request.keywords:
        yield None
        return
    calls = []

    async def fake_set(source_id, stage, fields):
        calls.append((str(source_id), stage, dict(fields)))

    monkeypatch.setattr("open_notebook.domain.ingestion._set", fake_set)
    yield calls


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_stage_writes: send ingestion stage writes to repo_query"
    )
