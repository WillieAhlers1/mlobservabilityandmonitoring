"""ML Monitoring Platform – Flask application."""

import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g
import mock_data

app = Flask(__name__)
app.secret_key = os.urandom(24)

DB_PATH = os.path.join(os.path.dirname(__file__), "ml_monitor.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
        owner TEXT NOT NULL, team TEXT, created_date TEXT, status TEXT DEFAULT 'Active'
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS onboarded_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT NOT NULL, project_id TEXT, model_type TEXT,
        algorithm TEXT, description TEXT, version TEXT, endpoint TEXT,
        owner TEXT, environment TEXT, primary_metric TEXT,
        drift_method TEXT, perf_threshold REAL, drift_threshold REAL,
        monitoring_frequency TEXT, features TEXT, created_date TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )""")
    db.commit()
    db.close()


init_db()


@app.route("/switch-industry/<industry_id>")
def switch_industry(industry_id):
    mock_data.set_industry(industry_id)
    flash(f'Switched to {mock_data.INDUSTRY_META.get("name", industry_id)}', "success")
    return redirect(url_for("projects"))


@app.context_processor
def inject_industry():
    return {
        "current_industry": mock_data.INDUSTRY_META,
        "available_industries": mock_data.get_available_industries(),
    }


@app.route("/")
def cockpit():
    view = request.args.get("view", "all")
    models = mock_data.MODELS
    agents = mock_data.AGENTS
    stats = mock_data.get_summary_stats_combined()
    return render_template("cockpit.html", models=models, agents=agents, stats=stats, view=view)


@app.route("/dashboard/<entity_id>")
def dashboard(entity_id):
    entity = mock_data.get_entity(entity_id)
    if not entity:
        flash("Entity not found.", "danger")
        return redirect(url_for("cockpit"))
    if entity.get("entity_type") == "agent":
        metrics = mock_data.get_agent_metrics(entity_id)
        fairness = mock_data.get_fairness_metrics(entity_id)
        lineage_data = mock_data.get_agent_lineage(entity_id)
        return render_template("agent_dashboard.html", agent=entity, metrics=metrics,
                               fairness=fairness, lineage=lineage_data)
    # Model dashboard
    model = entity
    metrics = mock_data.get_model_metrics(entity_id)
    fairness = mock_data.get_fairness_metrics(entity_id)
    lineage = mock_data.get_model_lineage(entity_id)
    return render_template("dashboard.html", model=model, metrics=metrics,
                           fairness=fairness, lineage=lineage)


@app.route("/lineage/<entity_id>")
def lineage(entity_id):
    entity = mock_data.get_entity(entity_id)
    if not entity:
        flash("Entity not found.", "danger")
        return redirect(url_for("cockpit"))
    if entity.get("entity_type") == "agent":
        lineage_data = mock_data.get_agent_lineage(entity_id)
    else:
        lineage_data = mock_data.get_model_lineage(entity_id)
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
    all_projects = mock_data.get_projects()
    for cp in custom_projects:
        cp["model_count"] = 0
        cp["models"] = []
        cp["agent_count"] = 0
        cp["agents"] = []
        all_projects.append(cp)
    return render_template("projects.html", projects=all_projects)


@app.route("/onboard", methods=["GET", "POST"])
def onboard():
    if request.method == "POST":
        model_name = request.form.get("model_name", "").strip()
        if model_name:
            from datetime import date
            db = get_db()
            db.execute(
                """INSERT INTO onboarded_models
                   (model_name, project_id, model_type, algorithm, description,
                    version, endpoint, owner, environment, primary_metric,
                    drift_method, perf_threshold, drift_threshold,
                    monitoring_frequency, features, created_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    model_name,
                    request.form.get("project_id", ""),
                    request.form.get("model_type", ""),
                    request.form.get("algorithm", ""),
                    request.form.get("description", ""),
                    request.form.get("version", ""),
                    request.form.get("endpoint", ""),
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
            db.commit()
            flash(f'Model "{model_name}" has been onboarded successfully!', "success")
        return redirect(url_for("onboard"))
    db = get_db()
    onboarded = [dict(r) for r in db.execute("SELECT * FROM onboarded_models ORDER BY created_date DESC").fetchall()]
    return render_template("onboard.html", projects=mock_data.get_projects(), onboarded=onboarded)


@app.route("/alerts")
def alerts():
    all_alerts = mock_data.get_alerts()
    severity_filter = request.args.get("severity", "all")
    type_filter = request.args.get("type", "all")
    if severity_filter != "all":
        all_alerts = [a for a in all_alerts if a["severity"] == severity_filter]
    if type_filter != "all":
        all_alerts = [a for a in all_alerts if a["type"] == type_filter]
    stats = {
        "total": len(mock_data.get_alerts()),
        "critical": len([a for a in mock_data.get_alerts() if a["severity"] == "critical"]),
        "warning": len([a for a in mock_data.get_alerts() if a["severity"] == "warning"]),
        "acknowledged": len([a for a in mock_data.get_alerts() if a["acknowledged"]]),
    }
    return render_template("alerts.html", alerts=all_alerts, stats=stats,
                           severity_filter=severity_filter, type_filter=type_filter)


@app.route("/compare")
def compare():
    model_a_id = request.args.get("model_a", "model-1")
    model_b_id = request.args.get("model_b", "model-2")
    model_a = mock_data.get_model(model_a_id)
    model_b = mock_data.get_model(model_b_id)
    metrics_a = mock_data.get_model_metrics(model_a_id) if model_a else None
    metrics_b = mock_data.get_model_metrics(model_b_id) if model_b else None
    return render_template("compare.html", models=mock_data.MODELS, agents=mock_data.AGENTS,
                           model_a=model_a, model_b=model_b,
                           metrics_a=metrics_a, metrics_b=metrics_b,
                           selected_a=model_a_id, selected_b=model_b_id)


@app.route("/api/model/<model_id>/metrics")
def api_model_metrics(model_id):
    metrics = mock_data.get_model_metrics(model_id)
    if not metrics:
        return jsonify({"error": "Model not found"}), 404
    return jsonify(metrics)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
