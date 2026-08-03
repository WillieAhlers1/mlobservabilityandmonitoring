"""Settings route and configuration schemas."""

from flask import render_template, request, redirect, url_for, flash

import mock_data
from config_loader import config

SETTINGS_SCHEMA = {
    "data_source": {
        "label": "Data Source Mode",
        "type": "select",
        "options": ["mock", "live"],
        "help": "\"mock\" uses deterministic generators, \"live\" queries the metric store via ingestion pipeline.",
    },
    "db_path": {
        "label": "Database Path",
        "type": "text",
        "help": "Path to the SQLite database (relative to project root or absolute).",
        "placeholder": "ml_monitor.db",
    },
    "default_industry": {
        "label": "Default Industry",
        "type": "select",
        "options": list(mock_data.AVAILABLE_INDUSTRIES.keys()),
        "help": "Industry loaded on startup.",
    },
}

FLASK_SCHEMA = {
    "debug": {
        "label": "Debug Mode",
        "type": "select",
        "options": [False, True],
        "option_labels": {False: "Off", True: "On"},
        "help": "Enable Flask debug/auto-reload (requires restart).",
    },
    "port": {
        "label": "Port",
        "type": "number",
        "min": 1024,
        "max": 65535,
        "help": "TCP port the Flask server listens on (requires restart).",
    },
}

INGESTION_SCHEMA = {
    "batch_size": {
        "label": "Batch Size",
        "type": "number",
        "min": 100,
        "max": 50000,
        "step": 100,
        "help": "Number of events processed per ingestion cycle.",
    },
    "grace_period_hours": {
        "label": "Grace Period (hours)",
        "type": "select",
        "options": [1, 2, 3, 6, 12, 24],
        "help": "Hours to wait before flagging late events.",
    },
    "max_lag_alert_minutes": {
        "label": "Max Lag Alert (minutes)",
        "type": "select",
        "options": [5, 10, 15, 30, 60, 120],
        "help": "Lag threshold in minutes before an alert is raised.",
    },
    "poll_interval_seconds": {
        "label": "Poll Interval (seconds)",
        "type": "select",
        "options": [10, 15, 30, 60, 120, 300],
        "help": "How often connectors poll for new data.",
    },
}

AGGREGATION_SCHEMA = {
    "default_bucket": {
        "label": "Default Bucket Size",
        "type": "select",
        "options": ["5m", "15m", "30m", "1h", "6h", "12h", "24h"],
        "help": "Default time-series aggregation bucket.",
    },
    "retention_days": {
        "label": "Retention (days)",
        "type": "select",
        "options": [7, 14, 30, 60, 90, 180, 365],
        "help": "How many days of metric data to keep.",
    },
}


def register_routes(app):
    """Register settings routes on the Flask app."""

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            raw = config.get_raw()

            # Top-level scalars
            raw["data_source"] = request.form.get("data_source", "mock")
            raw["db_path"] = request.form.get("db_path", "ml_monitor.db").strip() or "ml_monitor.db"
            raw["default_industry"] = request.form.get("default_industry", "hls")

            # Flask
            flask_section = raw.get("flask", {}) or {}
            flask_section["debug"] = request.form.get("flask_debug") == "True"
            port_str = request.form.get("flask_port", "5000")
            try:
                flask_section["port"] = max(1024, min(65535, int(port_str)))
            except ValueError:
                flask_section["port"] = 5000
            raw["flask"] = flask_section

            # Ingestion
            ing = raw.get("ingestion", {}) or {}
            for key in ("batch_size", "grace_period_hours", "max_lag_alert_minutes", "poll_interval_seconds"):
                val = request.form.get(f"ingestion_{key}", "")
                try:
                    ing[key] = int(val)
                except ValueError:
                    pass
            raw["ingestion"] = ing

            # Aggregation
            agg = raw.get("aggregation", {}) or {}
            agg["default_bucket"] = request.form.get("aggregation_default_bucket", "1h")
            ret_str = request.form.get("aggregation_retention_days", "90")
            try:
                agg["retention_days"] = int(ret_str)
            except ValueError:
                agg["retention_days"] = 90
            raw["aggregation"] = agg

            # Connectors (each connector's editable fields)
            connectors = raw.get("connectors", []) or []
            for i, conn in enumerate(connectors):
                ctype = conn.get("type", "")
                if ctype == "file_drop":
                    conn["watch_directory"] = request.form.get(f"connector_{i}_watch_directory", conn.get("watch_directory", ""))
                    conn["processed_directory"] = request.form.get(f"connector_{i}_processed_directory", conn.get("processed_directory", ""))
                    conn["file_pattern"] = request.form.get(f"connector_{i}_file_pattern", conn.get("file_pattern", "*.csv"))
                elif ctype == "webhook":
                    conn["path"] = request.form.get(f"connector_{i}_path", conn.get("path", ""))
                    rl = request.form.get(f"connector_{i}_rate_limit", "")
                    rc = request.form.get(f"connector_{i}_rate_capacity", "")
                    mp = request.form.get(f"connector_{i}_max_payload_bytes", "")
                    try:
                        conn["rate_limit"] = int(rl)
                    except ValueError:
                        pass
                    try:
                        conn["rate_capacity"] = int(rc)
                    except ValueError:
                        pass
                    try:
                        conn["max_payload_bytes"] = int(mp)
                    except ValueError:
                        pass
            raw["connectors"] = connectors

            config.save(raw)
            flash("Settings saved. Some changes may require a restart to take effect.", "success")
            return redirect(url_for("settings"))

        raw = config.get_raw()
        return render_template(
            "settings.html",
            raw=raw,
            settings_schema=SETTINGS_SCHEMA,
            flask_schema=FLASK_SCHEMA,
            ingestion_schema=INGESTION_SCHEMA,
            aggregation_schema=AGGREGATION_SCHEMA,
        )
