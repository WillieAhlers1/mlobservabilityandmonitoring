"""Shared test fixtures for ML Monitoring test suite."""

import os
import sqlite3
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with the full schema via init_db()."""
    db_path = str(tmp_path / "test.db")
    # Patch DB_PATH before importing app module
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    yield db_path
    app_module.DB_PATH = original_path


@pytest.fixture
def test_client(tmp_path):
    """Flask test client with a fresh temp database."""
    db_path = str(tmp_path / "test_app.db")
    import app as app_module
    original_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        with app_module.app.app_context():
            yield client
    app_module.DB_PATH = original_path


@pytest.fixture
def db_conn(tmp_db):
    """Return a sqlite3 connection to the temp DB."""
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
