"""Centralized configuration loader for ML Works.

Reads config/app.yaml and allows environment variable overrides.
Environment variables are prefixed with ML_WORKS_ and use uppercase
(e.g., data_source → ML_WORKS_DATA_SOURCE, db_path → ML_WORKS_DB_PATH).

Usage:
    from config_loader import config
    print(config.data_source)       # "mock" or "live"
    print(config.db_path)           # absolute path to SQLite DB
    print(config.ingestion)         # dict of ingestion settings
"""

import os
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "app.yaml"

ENV_PREFIX = "ML_WORKS_"


def _load_yaml() -> dict:
    """Load the YAML config file. Returns empty dict if missing."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _env_override(key: str, default):
    """Check for an environment variable override for a top-level key."""
    env_key = f"{ENV_PREFIX}{key.upper()}"
    val = os.environ.get(env_key)
    if val is None:
        return default
    # Coerce to the same type as the default
    if isinstance(default, bool):
        return val.lower() in ("1", "true", "yes")
    if isinstance(default, int):
        try:
            return int(val)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(val)
        except ValueError:
            return default
    return val


class _Config:
    """Application configuration singleton."""

    def __init__(self):
        self._raw = _load_yaml()
        self._resolve()

    def _resolve(self):
        """Resolve final values: YAML defaults → env overrides."""
        # Top-level scalars
        self.data_source: str = _env_override(
            "data_source", self._raw.get("data_source", "mock")
        )

        raw_db = self._raw.get("db_path", "ml_monitor.db")
        env_db = os.environ.get(f"{ENV_PREFIX}DB_PATH")
        if env_db:
            raw_db = env_db
        # Resolve relative paths against project root
        db_path = Path(raw_db)
        if not db_path.is_absolute():
            db_path = _PROJECT_ROOT / db_path
        self.db_path: str = str(db_path)

        self.default_industry: str = _env_override(
            "default_industry", self._raw.get("default_industry", "hls")
        )

        # Flask settings
        flask_raw = self._raw.get("flask", {})
        self.flask_debug: bool = _env_override(
            "flask_debug", flask_raw.get("debug", False)
        )
        self.flask_port: int = _env_override(
            "flask_port", flask_raw.get("port", 5000)
        )
        secret = os.environ.get(f"{ENV_PREFIX}SECRET_KEY")
        self.flask_secret_key: str | None = secret  # None → app.py generates random

        # Ingestion settings (dict, no env override for nested)
        self.ingestion: dict = self._raw.get("ingestion", {
            "batch_size": 1000,
            "grace_period_hours": 6,
            "max_lag_alert_minutes": 30,
            "poll_interval_seconds": 60,
        })

        # Aggregation settings
        self.aggregation: dict = self._raw.get("aggregation", {
            "default_bucket": "1h",
            "retention_days": 90,
        })

        # Connectors list (expanded in Session 6)
        self.connectors: list = self._raw.get("connectors", [])

    def reload(self):
        """Re-read config from disk and env. Useful for testing."""
        self._raw = _load_yaml()
        self._resolve()


# Module-level singleton
config = _Config()
