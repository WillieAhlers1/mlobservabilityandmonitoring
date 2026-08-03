"""Onboarding routes for models and agents."""

import json
import uuid
from datetime import date, datetime, timezone

from flask import render_template, request, redirect, url_for, flash

import data_source
from database import get_db


def register_routes(app):
    """Register onboarding routes on the Flask app."""

    @app.route("/onboard", methods=["GET", "POST"])
    def onboard():
        if request.method == "POST":
            entity_type = request.form.get("entity_type", "model")
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            industry_id = data_source.get_current_industry()

            if entity_type == "agent":
                _onboard_agent(db, now_iso, industry_id)
            else:
                _onboard_model(db, now_iso, industry_id)
            return redirect(url_for("onboard"))

        db = get_db()
        onboarded_models = [dict(r) for r in db.execute("SELECT * FROM onboarded_models ORDER BY created_date DESC").fetchall()]
        onboarded_agents = [dict(r) for r in db.execute("SELECT * FROM onboarded_agents ORDER BY created_date DESC").fetchall()]
        return render_template("onboard.html", projects=data_source.get_projects(),
                               onboarded_models=onboarded_models, onboarded_agents=onboarded_agents)


def _onboard_agent(db, now_iso, industry_id):
    """Handle agent onboarding POST."""
    agent_name = request.form.get("agent_name", "").strip()
    if not agent_name:
        return

    entity_id = f"agent-{uuid.uuid4().hex[:8]}"
    project_id = request.form.get("project_id", "")
    endpoint = request.form.get("endpoint", "")

    db.execute(
        """INSERT INTO onboarded_agents
           (entity_id, agent_name, project_id, framework, llm_backbone, description,
            version, endpoint, owner, environment,
            task_completion_threshold, groundedness_threshold,
            safety_threshold, cost_budget, latency_sla,
            tools, linked_models,
            hipaa_required, phi_handling, deid_method,
            data_classification, retention_days, created_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            entity_id,
            agent_name,
            project_id,
            request.form.get("framework", ""),
            request.form.get("llm_backbone", ""),
            request.form.get("description", ""),
            request.form.get("version", ""),
            endpoint,
            request.form.get("owner", ""),
            request.form.get("environment", "production"),
            float(request.form.get("task_completion_threshold", 0.90)),
            float(request.form.get("groundedness_threshold", 0.85)),
            float(request.form.get("safety_threshold", 0.95)),
            float(request.form.get("cost_budget", 0.10)),
            int(request.form.get("latency_sla", 3000)),
            request.form.get("tools", ""),
            request.form.get("linked_models", ""),
            1 if request.form.get("hipaa_required") else 0,
            request.form.get("phi_handling", ""),
            request.form.get("deid_method", ""),
            request.form.get("data_classification", ""),
            int(request.form.get("retention_days", 365)),
            date.today().isoformat(),
        ),
    )

    # Register in entity_registry
    metadata = json.dumps({
        "framework": request.form.get("framework", ""),
        "llm_backbone": request.form.get("llm_backbone", ""),
        "version": request.form.get("version", ""),
    })
    db.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (entity_id, "agent", industry_id, project_id, agent_name, "Unknown", metadata, now_iso, now_iso),
    )
    # Register aliases
    db.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
        (entity_id, "onboard_name", agent_name),
    )
    if endpoint:
        db.execute(
            "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
            (entity_id, "endpoint", endpoint),
        )
    source_ref = request.form.get("source_ref", "").strip()
    if source_ref:
        db.execute(
            "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
            (entity_id, "source_ref", source_ref),
        )

    db.commit()
    flash(f'Agent "{agent_name}" has been onboarded successfully!', "success")


def _onboard_model(db, now_iso, industry_id):
    """Handle model onboarding POST."""
    model_name = request.form.get("model_name", "").strip()
    if not model_name:
        return

    entity_id = f"model-{uuid.uuid4().hex[:8]}"
    project_id = request.form.get("project_id", "")
    endpoint = request.form.get("endpoint", "")

    db.execute(
        """INSERT INTO onboarded_models
           (entity_id, model_name, project_id, model_type, algorithm, description,
            version, endpoint, owner, environment, primary_metric,
            drift_method, perf_threshold, drift_threshold,
            monitoring_frequency, features, created_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            entity_id,
            model_name,
            project_id,
            request.form.get("model_type", ""),
            request.form.get("algorithm", ""),
            request.form.get("description", ""),
            request.form.get("version", ""),
            endpoint,
            request.form.get("owner", ""),
            request.form.get("environment", "production"),
            request.form.get("primary_metric", "accuracy"),
            request.form.get("drift_method", "psi"),
            float(request.form.get("perf_threshold", 0.85)),
            float(request.form.get("drift_threshold", 0.1)),
            request.form.get("monitoring_frequency", "daily"),
            request.form.get("features", ""),
            date.today().isoformat(),
        ),
    )

    # Register in entity_registry
    metadata = json.dumps({
        "model_type": request.form.get("model_type", ""),
        "algorithm": request.form.get("algorithm", ""),
        "version": request.form.get("version", ""),
    })
    db.execute(
        """INSERT INTO entity_registry
           (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (entity_id, "model", industry_id, project_id, model_name, "Unknown", metadata, now_iso, now_iso),
    )
    # Register aliases
    db.execute(
        "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
        (entity_id, "onboard_name", model_name),
    )
    if endpoint:
        db.execute(
            "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
            (entity_id, "endpoint", endpoint),
        )
    source_ref = request.form.get("source_ref", "").strip()
    if source_ref:
        db.execute(
            "INSERT INTO entity_aliases (entity_id, alias_type, alias_value) VALUES (?,?,?)",
            (entity_id, "source_ref", source_ref),
        )

    db.commit()
    flash(f'Model "{model_name}" has been onboarded successfully!', "success")
