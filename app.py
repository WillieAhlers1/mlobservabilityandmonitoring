"""ML Monitoring Platform – Flask application."""

import os
from pathlib import Path

from flask import Flask

import mock_data
import data_source
import database as _database
from config_loader import config
from routes import register_all_routes

# Expose DB_PATH for backward compatibility with tests that patch app.DB_PATH
DB_PATH = _database.DB_PATH


def init_db():
    """Initialize database, syncing DB_PATH to the database module."""
    _database.DB_PATH = DB_PATH
    _database.init_db()


app = Flask(__name__)
app.secret_key = config.flask_secret_key or os.urandom(24)

# Initialize database schema
init_db()

# Register teardown
app.teardown_appcontext(_database.close_db)

# Register all routes
register_all_routes(app)


@app.context_processor
def inject_industry():
    return {
        "current_industry": mock_data.INDUSTRY_META,
        "available_industries": mock_data.get_available_industries(),
        "data_source_mode": data_source.DATA_SOURCE,
    }


# ── Ingestion Scheduler (live mode only) ────────────────────────────────────
_ingestion_scheduler = None


def _start_scheduler():
    """Start the ingestion scheduler if in live mode."""
    global _ingestion_scheduler
    if config.data_source != "live":
        return
    if _ingestion_scheduler is not None:
        return

    from ingestion.scheduler import IngestionScheduler

    mappings_dir = Path(__file__).parent / "mappings"
    _ingestion_scheduler = IngestionScheduler(
        db_path=config.db_path,
        connectors_config=config.connectors,
        mappings_dir=mappings_dir,
        ingestion_config=config.ingestion,
    )
    _ingestion_scheduler.start()


def _stop_scheduler():
    """Stop the ingestion scheduler gracefully."""
    global _ingestion_scheduler
    if _ingestion_scheduler is not None:
        _ingestion_scheduler.shutdown(wait=False)
        _ingestion_scheduler = None


# Start scheduler on module load (only in live mode)
_start_scheduler()


if __name__ == "__main__":
    try:
        app.run(debug=config.flask_debug, port=config.flask_port)
    finally:
        _stop_scheduler()
