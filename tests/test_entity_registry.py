"""Tests for Session 1: Entity Registry and Metric Store Schema."""

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestSchemaCreation:
    """Verify init_db() creates all required tables."""

    EXPECTED_TABLES = [
        "projects",
        "onboarded_models",
        "onboarded_agents",
        "entity_registry",
        "entity_aliases",
        "metric_timeseries",
        "drift_snapshots",
        "cohort_metrics",
        "feature_importance",
        "data_quality",
        "agent_traces",
        "agent_trace_steps",
        "alerts",
        "lineage_events",
        "staging_events",
        "connector_health",
        "schema_version",
    ]

    def test_all_tables_created(self, tmp_db):
        """init_db() creates all metric store tables."""
        conn = sqlite3.connect(tmp_db)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        for table in self.EXPECTED_TABLES:
            assert table in tables, f"Table '{table}' not found in database"

    def test_idempotent_creation(self, tmp_db):
        """Calling init_db() twice does not error."""
        import app as app_module
        # Already called once by fixture; call again
        app_module.init_db()
        conn = sqlite3.connect(tmp_db)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        for table in self.EXPECTED_TABLES:
            assert table in tables

    def test_entity_id_column_in_onboarded_models(self, tmp_db):
        """onboarded_models has entity_id column."""
        conn = sqlite3.connect(tmp_db)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(onboarded_models)").fetchall()]
        conn.close()
        assert "entity_id" in columns

    def test_entity_id_column_in_onboarded_agents(self, tmp_db):
        """onboarded_agents has entity_id column."""
        conn = sqlite3.connect(tmp_db)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(onboarded_agents)").fetchall()]
        conn.close()
        assert "entity_id" in columns

    def test_entity_registry_constraints(self, db_conn):
        """entity_registry rejects invalid entity_type."""
        with pytest.raises(sqlite3.IntegrityError):
            db_conn.execute(
                """INSERT INTO entity_registry
                   (entity_id, entity_type, industry_id, project_id, name, status, metadata, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                ("test-1", "invalid_type", "hls", "proj-1", "Test", "Unknown", "{}", "2026-01-01", "2026-01-01"),
            )

    def test_indexes_created(self, tmp_db):
        """Key indexes exist."""
        conn = sqlite3.connect(tmp_db)
        indexes = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        ]
        conn.close()
        assert "idx_metric_ts_entity_time" in indexes
        assert "idx_staging_status" in indexes
        assert "idx_staging_entity" in indexes


class TestOnboardModel:
    """Verify model onboarding writes to entity_registry."""

    def test_onboard_model_creates_entity(self, test_client):
        """POST model form creates entity_registry row."""
        response = test_client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Churn Predictor",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "algorithm": "XGBoost",
            "description": "Predicts patient churn",
            "version": "v1.0.0",
            "endpoint": "/api/v1/predict/churn",
            "owner": "Dr. Smith",
            "environment": "production",
            "primary_metric": "accuracy",
            "drift_method": "psi",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
            "monitoring_frequency": "daily",
            "features": "age,gender,visits",
        }, follow_redirects=True)
        assert response.status_code == 200

        # Check entity_registry
        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM entity_registry WHERE entity_type='model'").fetchone()
        conn.close()
        assert row is not None
        assert row["name"] == "Churn Predictor"
        assert row["entity_type"] == "model"
        assert row["industry_id"] == "hls"
        assert row["entity_id"].startswith("model-")

    def test_onboard_model_creates_aliases(self, test_client):
        """POST model form creates entity_aliases rows."""
        test_client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Risk Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "/api/risk",
            "owner": "Team A",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        aliases = conn.execute("SELECT * FROM entity_aliases").fetchall()
        conn.close()
        alias_types = [a["alias_type"] for a in aliases]
        alias_values = [a["alias_value"] for a in aliases]
        assert "onboard_name" in alias_types
        assert "endpoint" in alias_types
        assert "Risk Model" in alias_values
        assert "/api/risk" in alias_values

    def test_onboard_model_sets_entity_id_in_onboarded_models(self, test_client):
        """POST model form sets entity_id in onboarded_models."""
        test_client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Test Model",
            "project_id": "proj-hls-1",
            "model_type": "regression",
            "version": "v2.0.0",
            "endpoint": "",
            "owner": "Owner",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM onboarded_models").fetchone()
        conn.close()
        assert row is not None
        assert row["entity_id"] is not None
        assert row["entity_id"].startswith("model-")

    def test_onboard_model_no_endpoint_alias_when_empty(self, test_client):
        """No endpoint alias created when endpoint is empty."""
        test_client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "No Endpoint Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        aliases = conn.execute("SELECT * FROM entity_aliases WHERE alias_type='endpoint'").fetchall()
        conn.close()
        assert len(aliases) == 0

    def test_duplicate_names_get_different_entity_ids(self, test_client):
        """Two models with same name get distinct entity_ids."""
        for _ in range(2):
            test_client.post("/onboard", data={
                "entity_type": "model",
                "model_name": "Same Name",
                "project_id": "proj-hls-1",
                "model_type": "classification",
                "version": "v1.0.0",
                "endpoint": "",
                "owner": "Team",
                "perf_threshold": "0.85",
                "drift_threshold": "0.1",
            }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT entity_id FROM entity_registry WHERE entity_type='model'").fetchall()
        conn.close()
        ids = [r["entity_id"] for r in rows]
        assert len(ids) == 2
        assert ids[0] != ids[1]


class TestOnboardAgent:
    """Verify agent onboarding writes to entity_registry."""

    def test_onboard_agent_creates_entity(self, test_client):
        """POST agent form creates entity_registry row."""
        response = test_client.post("/onboard", data={
            "entity_type": "agent",
            "agent_name": "Clinical Copilot",
            "project_id": "proj-hls-2",
            "framework": "LangChain",
            "llm_backbone": "GPT-4o",
            "description": "Clinical decision support",
            "version": "v1.2.0",
            "endpoint": "/api/agent/clinical",
            "owner": "AI Team",
            "environment": "production",
            "task_completion_threshold": "0.90",
            "groundedness_threshold": "0.85",
            "safety_threshold": "0.95",
            "cost_budget": "0.10",
            "latency_sla": "3000",
            "tools": "EHR Lookup,Drug DB",
            "linked_models": "model-1",
            "retention_days": "365",
        }, follow_redirects=True)
        assert response.status_code == 200

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM entity_registry WHERE entity_type='agent'").fetchone()
        conn.close()
        assert row is not None
        assert row["name"] == "Clinical Copilot"
        assert row["entity_type"] == "agent"
        assert row["entity_id"].startswith("agent-")

    def test_onboard_agent_creates_aliases(self, test_client):
        """POST agent form creates entity_aliases rows."""
        test_client.post("/onboard", data={
            "entity_type": "agent",
            "agent_name": "Billing Agent",
            "project_id": "proj-hls-1",
            "framework": "Semantic Kernel",
            "llm_backbone": "GPT-4",
            "version": "v1.0.0",
            "endpoint": "/api/agent/billing",
            "owner": "Team B",
            "task_completion_threshold": "0.90",
            "groundedness_threshold": "0.85",
            "safety_threshold": "0.95",
            "cost_budget": "0.10",
            "latency_sla": "3000",
            "retention_days": "365",
        }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        aliases = conn.execute("SELECT * FROM entity_aliases").fetchall()
        conn.close()
        alias_types = [a["alias_type"] for a in aliases]
        alias_values = [a["alias_value"] for a in aliases]
        assert "onboard_name" in alias_types
        assert "endpoint" in alias_types
        assert "Billing Agent" in alias_values
        assert "/api/agent/billing" in alias_values

    def test_onboard_agent_sets_entity_id(self, test_client):
        """POST agent form sets entity_id in onboarded_agents."""
        test_client.post("/onboard", data={
            "entity_type": "agent",
            "agent_name": "Test Agent",
            "project_id": "proj-hls-1",
            "framework": "LangChain",
            "llm_backbone": "GPT-4",
            "version": "v1.0.0",
            "endpoint": "",
            "owner": "Owner",
            "task_completion_threshold": "0.90",
            "groundedness_threshold": "0.85",
            "safety_threshold": "0.95",
            "cost_budget": "0.10",
            "latency_sla": "3000",
            "retention_days": "365",
        }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entity_id FROM onboarded_agents").fetchone()
        conn.close()
        assert row is not None
        assert row["entity_id"] is not None
        assert row["entity_id"].startswith("agent-")


class TestEntityLookupByAlias:
    """Verify entities can be found via their aliases."""

    def test_lookup_by_name_alias(self, test_client):
        """Entity can be found by onboard_name alias."""
        test_client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Findable Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "/api/find",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT entity_id FROM entity_aliases WHERE alias_value = ?",
            ("Findable Model",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["entity_id"].startswith("model-")

    def test_lookup_by_endpoint_alias(self, test_client):
        """Entity can be found by endpoint alias."""
        test_client.post("/onboard", data={
            "entity_type": "model",
            "model_name": "Endpoint Model",
            "project_id": "proj-hls-1",
            "model_type": "classification",
            "version": "v1.0.0",
            "endpoint": "/api/unique-endpoint",
            "owner": "Team",
            "perf_threshold": "0.85",
            "drift_threshold": "0.1",
        }, follow_redirects=True)

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT entity_id FROM entity_aliases WHERE alias_type='endpoint' AND alias_value=?",
            ("/api/unique-endpoint",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["entity_id"].startswith("model-")


class TestMigrationScript:
    """Test the seed_entity_registry migration script."""

    def test_migrates_existing_models(self, tmp_db):
        """Migration script converts models without entity_id."""
        conn = sqlite3.connect(tmp_db)
        # Insert a model without entity_id (simulating old schema)
        conn.execute(
            """INSERT INTO onboarded_models
               (model_name, project_id, model_type, algorithm, version, endpoint, owner, created_date)
               VALUES (?,?,?,?,?,?,?,?)""",
            ("Legacy Model", "proj-1", "classification", "RF", "v0.5", "/old/endpoint", "Old Owner", "2025-01-01"),
        )
        conn.commit()
        conn.close()

        from migrations.seed_entity_registry import migrate
        result = migrate(tmp_db)
        assert result["models"] == 1
        assert result["agents"] == 0

        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        model_row = conn.execute("SELECT entity_id FROM onboarded_models").fetchone()
        assert model_row["entity_id"] is not None
        assert model_row["entity_id"].startswith("model-")

        reg_row = conn.execute("SELECT * FROM entity_registry").fetchone()
        assert reg_row["name"] == "Legacy Model"
        assert reg_row["entity_type"] == "model"

        aliases = conn.execute("SELECT * FROM entity_aliases").fetchall()
        alias_values = [a["alias_value"] for a in aliases]
        assert "Legacy Model" in alias_values
        assert "/old/endpoint" in alias_values
        conn.close()

    def test_migrates_existing_agents(self, tmp_db):
        """Migration script converts agents without entity_id."""
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            """INSERT INTO onboarded_agents
               (agent_name, project_id, framework, llm_backbone, version, endpoint, owner, created_date,
                task_completion_threshold, groundedness_threshold, safety_threshold, cost_budget, latency_sla, retention_days)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("Legacy Agent", "proj-2", "LangChain", "GPT-4", "v0.1", "/old/agent", "Old Team", "2025-06-01",
             0.9, 0.85, 0.95, 0.1, 3000, 365),
        )
        conn.commit()
        conn.close()

        from migrations.seed_entity_registry import migrate
        result = migrate(tmp_db)
        assert result["models"] == 0
        assert result["agents"] == 1

        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        agent_row = conn.execute("SELECT entity_id FROM onboarded_agents").fetchone()
        assert agent_row["entity_id"] is not None
        assert agent_row["entity_id"].startswith("agent-")

        reg_row = conn.execute("SELECT * FROM entity_registry").fetchone()
        assert reg_row["name"] == "Legacy Agent"
        assert reg_row["entity_type"] == "agent"
        conn.close()

    def test_skips_already_migrated(self, tmp_db):
        """Re-running migration skips rows that already have entity_id."""
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            """INSERT INTO onboarded_models
               (entity_id, model_name, project_id, model_type, version, owner, created_date)
               VALUES (?,?,?,?,?,?,?)""",
            ("model-existing", "Already Migrated", "proj-1", "classification", "v1.0", "Owner", "2026-01-01"),
        )
        conn.commit()
        conn.close()

        from migrations.seed_entity_registry import migrate
        result = migrate(tmp_db)
        assert result["models"] == 0
        assert result["agents"] == 0
