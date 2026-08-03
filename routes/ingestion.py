"""Ingestion observability routes and webhook endpoint."""

from flask import render_template, request, redirect, url_for, flash, jsonify

import data_source
from config_loader import config
from database import get_db

# Lazy-initialized webhook connector (created on first request)
_webhook_connector = None


def _get_webhook_connector():
    """Get or create the webhook connector singleton."""
    global _webhook_connector
    if _webhook_connector is None:
        from ingestion.connectors.webhook import WebhookConnector
        webhook_config = None
        for c in config.connectors:
            if c.get("type") == "webhook":
                webhook_config = c
                break
        if webhook_config is None:
            webhook_config = {
                "id": "webhook-default",
                "type": "webhook",
                "secret_env_var": "WEBHOOK_SECRET",
            }
        _webhook_connector = WebhookConnector(webhook_config)
    return _webhook_connector


def register_routes(app):
    """Register ingestion routes on the Flask app."""

    @app.route("/ingestion/health")
    def ingestion_health():
        """Pipeline health dashboard — only accessible in live mode."""
        if data_source.DATA_SOURCE != "live":
            return redirect(url_for("cockpit"))

        from ingestion.metrics import (
            get_pipeline_stats, get_processing_lag, get_connector_health,
            get_late_event_count,
        )
        from ingestion.drift_detector import detect_schema_drift

        db = get_db()
        stats = get_pipeline_stats(db)
        lag = get_processing_lag(db)
        connectors = get_connector_health(db)
        late_events = get_late_event_count(db)
        schema_alerts = detect_schema_drift(db)

        return render_template("ingestion_health.html",
                               stats=stats, lag=lag, connectors=connectors,
                               late_events=late_events, schema_alerts=schema_alerts)

    @app.route("/ingestion/dead-letter")
    def ingestion_dead_letter():
        """Dead-letter queue — rejected CTEs with reasons."""
        if data_source.DATA_SOURCE != "live":
            return redirect(url_for("cockpit"))

        from ingestion.metrics import get_rejected_events, get_rejected_count

        db = get_db()
        page = request.args.get("page", 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        events = get_rejected_events(db, limit=per_page, offset=offset)
        total = get_rejected_count(db)
        total_pages = max(1, (total + per_page - 1) // per_page)

        return render_template("dead_letter.html",
                               events=events, total=total,
                               page=page, total_pages=total_pages)

    @app.route("/ingestion/reprocess", methods=["POST"])
    def ingestion_reprocess():
        """Reprocess a rejected CTE (reset to pending)."""
        if data_source.DATA_SOURCE != "live":
            return jsonify({"error": "Only available in live mode"}), 403

        from ingestion.metrics import reprocess_event, reprocess_all_rejected

        db = get_db()
        event_id = request.form.get("event_id")
        reprocess_all = request.form.get("reprocess_all")

        if reprocess_all:
            count = reprocess_all_rejected(db)
            flash(f"Reset {count} rejected events to pending.", "success")
        elif event_id:
            if reprocess_event(db, event_id):
                flash(f"Event {event_id[:12]}... reset to pending.", "success")
            else:
                flash(f"Event not found or not rejected.", "warning")
        else:
            flash("No event specified.", "warning")

        return redirect(url_for("ingestion_dead_letter"))

    @app.route("/api/ingest/webhook", methods=["POST"])
    def ingest_webhook():
        """Receive telemetry events via HTTP POST with HMAC authentication."""
        from ingestion.staging import insert_single_cte

        wc = _get_webhook_connector()

        # Content-Type check
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400

        # Payload size check
        content_length = request.content_length or 0
        if content_length > wc._max_payload_bytes:
            return jsonify({"error": f"Payload too large (max {wc._max_payload_bytes} bytes)"}), 400

        # Rate limit check
        if not wc.check_rate_limit():
            return jsonify({"error": "Rate limit exceeded"}), 429

        # HMAC signature verification
        raw_body = request.get_data()
        signature = request.headers.get("X-Webhook-Signature")
        if not wc.verify_signature(raw_body, signature):
            return jsonify({"error": "Invalid signature"}), 401

        # Parse JSON
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Invalid JSON body"}), 400

        # Validate payload
        valid, error = wc.validate_payload(data)
        if not valid:
            return jsonify({"error": error}), 400

        # Idempotency check
        idempotency_key = request.headers.get("X-Idempotency-Key")
        is_dup, existing_id = wc.check_idempotency(idempotency_key)
        if is_dup:
            return jsonify({"error": "Duplicate event", "event_id": existing_id}), 409

        # Create CTE and insert into staging
        cte = wc.create_cte(data)
        db = get_db()
        inserted = insert_single_cte(db, cte)

        if not inserted:
            # Event ID collision (content-based dedup)
            return jsonify({"error": "Duplicate event", "event_id": cte.event_id}), 409

        # Record idempotency key if provided
        if idempotency_key:
            wc.record_idempotency(idempotency_key, cte.event_id)

        return jsonify({"event_id": cte.event_id, "status": "accepted"}), 201
