"""Core routes: cockpit, dashboard, lineage, projects, compare, alerts, API."""

from flask import render_template, request, redirect, url_for, flash, jsonify

import data_source
import mock_data
from database import get_db


def register_routes(app):
    """Register core routes on the Flask app."""

    @app.route("/switch-industry/<industry_id>")
    def switch_industry(industry_id):
        data_source.set_industry(industry_id)
        flash(f'Switched to {mock_data.INDUSTRY_META.get("name", industry_id)}', "success")
        return redirect(url_for("projects"))

    @app.route("/")
    def cockpit():
        view = request.args.get("view", "all")
        models = data_source.get_models()
        agents = data_source.get_agents()
        stats = data_source.get_summary_stats_combined()
        return render_template("cockpit.html", models=models, agents=agents, stats=stats, view=view)

    @app.route("/dashboard/<entity_id>")
    def dashboard(entity_id):
        entity = data_source.get_entity(entity_id)
        if not entity:
            flash("Entity not found.", "danger")
            return redirect(url_for("cockpit"))
        if entity.get("entity_type") == "agent":
            metrics = data_source.get_agent_metrics(entity_id)
            fairness = data_source.get_fairness_metrics(entity_id)
            lineage_data = data_source.get_agent_lineage(entity_id)
            return render_template("agent_dashboard.html", agent=entity, metrics=metrics,
                                   fairness=fairness, lineage=lineage_data)
        # Model dashboard
        model = entity
        metrics = data_source.get_model_metrics(entity_id)
        fairness = data_source.get_fairness_metrics(entity_id)
        lineage = data_source.get_model_lineage(entity_id)
        return render_template("dashboard.html", model=model, metrics=metrics,
                               fairness=fairness, lineage=lineage)

    @app.route("/lineage/<entity_id>")
    def lineage(entity_id):
        entity = data_source.get_entity(entity_id)
        if not entity:
            flash("Entity not found.", "danger")
            return redirect(url_for("cockpit"))
        if entity.get("entity_type") == "agent":
            lineage_data = data_source.get_agent_lineage(entity_id)
        else:
            lineage_data = data_source.get_model_lineage(entity_id)
        return render_template("lineage.html", model=entity, lineage=lineage_data)

    @app.route("/projects", methods=["GET", "POST"])
    def projects():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            owner = request.form.get("owner", "").strip()
            description = request.form.get("description", "").strip()
            team = request.form.get("team", "").strip()
            if name and owner:
                from datetime import date
                db = get_db()
                proj_id = "proj-custom-" + name.lower().replace(" ", "-")[:20]
                db.execute(
                    "INSERT OR IGNORE INTO projects (id, name, description, owner, team, created_date) VALUES (?,?,?,?,?,?)",
                    (proj_id, name, description, owner, team, date.today().isoformat()),
                )
                db.commit()
                flash(f'Project "{name}" created successfully!', "success")
            return redirect(url_for("projects"))
        db = get_db()
        custom_projects = [dict(r) for r in db.execute("SELECT * FROM projects").fetchall()]
        all_projects = data_source.get_projects()
        existing_ids = {p["id"] for p in all_projects}
        for cp in custom_projects:
            if cp["id"] in existing_ids:
                continue
            cp["model_count"] = 0
            cp["models"] = []
            cp["agent_count"] = 0
            cp["agents"] = []
            all_projects.append(cp)
        return render_template("projects.html", projects=all_projects)

    @app.route("/alerts")
    def alerts():
        all_alerts = data_source.get_alerts()
        severity_filter = request.args.get("severity", "all")
        type_filter = request.args.get("type", "all")
        unfiltered = list(all_alerts)
        if severity_filter != "all":
            all_alerts = [a for a in all_alerts if a["severity"] == severity_filter]
        if type_filter != "all":
            all_alerts = [a for a in all_alerts if a["type"] == type_filter]
        stats = {
            "total": len(unfiltered),
            "critical": len([a for a in unfiltered if a["severity"] == "critical"]),
            "warning": len([a for a in unfiltered if a["severity"] == "warning"]),
            "acknowledged": len([a for a in unfiltered if a.get("acknowledged")]),
        }
        return render_template("alerts.html", alerts=all_alerts, stats=stats,
                               severity_filter=severity_filter, type_filter=type_filter)

    @app.route("/compare")
    def compare():
        models = data_source.get_models()
        agents = data_source.get_agents()
        # Default to first two available models if no selection provided
        default_a = models[0]["id"] if len(models) > 0 else ""
        default_b = models[1]["id"] if len(models) > 1 else default_a
        model_a_id = request.args.get("model_a", default_a)
        model_b_id = request.args.get("model_b", default_b)
        model_a = data_source.get_model(model_a_id)
        model_b = data_source.get_model(model_b_id)
        metrics_a = data_source.get_model_metrics(model_a_id) if model_a else None
        metrics_b = data_source.get_model_metrics(model_b_id) if model_b else None
        return render_template("compare.html", models=models, agents=agents,
                               model_a=model_a, model_b=model_b,
                               metrics_a=metrics_a, metrics_b=metrics_b,
                               selected_a=model_a_id, selected_b=model_b_id)

    @app.route("/api/model/<model_id>/metrics")
    def api_model_metrics(model_id):
        metrics = data_source.get_model_metrics(model_id)
        if not metrics:
            return jsonify({"error": "Model not found"}), 404
        return jsonify(metrics)
