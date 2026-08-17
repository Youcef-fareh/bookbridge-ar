"""Pytest configuration and shared fixtures for BookBridge."""

import os
import shutil
import tempfile
from pathlib import Path
import pytest
from bookbridge.config.settings import settings
from bookbridge.database.connection import DatabaseManager, db
from bookbridge.database.migrations import run_migrations


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    temp_dir = tempfile.mkdtemp(prefix="bookbridge_test_")
    test_data_dir = Path(temp_dir)
    settings.data_dir = test_data_dir
    settings.ensure_directories()

    # Re-initialize DB
    db.db_path = settings.db_path
    run_migrations()

    yield test_data_dir

    db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)
