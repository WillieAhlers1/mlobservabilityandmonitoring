"""Synthetic telemetry data generator for ML Works.

Generates realistic CSV files covering all CTE event types for testing the
telemetry ingestion pipeline without access to live systems.

Usage:
    python tools/generate_synthetic_data.py --help
    python tools/generate_synthetic_data.py --industry hls --days 90 --seed 42
    python tools/generate_synthetic_data.py --days 7 --entities 2 --output-dir data/synthetic/quick
"""

import argparse
import csv
import json
import math
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Industry entity definitions ─────────────────────────────────────────────

INDUSTRY_ENTITIES = {
    "hls": {
        "models": [
            {"name": "Patient Readmission Risk", "model_type": "classification", "project_id": "proj-hls-1", "features": ["length_of_stay", "prior_admissions", "comorbidity_index", "discharge_code", "diagnosis_icd10", "med_count", "lab_abnormal", "insurance_type", "days_since_ed", "social_risk"]},
            {"name": "Adverse Drug Event Detector", "model_type": "classification", "project_id": "proj-hls-1", "features": ["drug_interactions", "dosage_ratio", "renal_function", "liver_function", "allergy_flag", "age", "weight", "concurrent_meds", "route", "frequency"]},
            {"name": "Clinical Trial Enrollment Predictor", "model_type": "classification", "project_id": "proj-hls-2", "features": ["site_capacity", "protocol_complexity", "disease_prevalence", "competition_score", "pi_experience", "geo_distance", "insurance_coverage", "demographics_match", "referral_network", "seasonal_factor"]},
            {"name": "Disease Progression Forecaster", "model_type": "regression", "project_id": "proj-hls-2", "features": ["baseline_severity", "biomarker_trend", "treatment_adherence", "comorbidity_count", "age", "bmi", "activity_level", "genetic_risk", "environmental_exposure", "social_support"]},
            {"name": "Medical Image Anomaly Detector", "model_type": "classification", "project_id": "proj-hls-3", "features": ["pixel_intensity_mean", "texture_entropy", "shape_regularity", "contrast_ratio", "edge_density", "region_size", "symmetry_score", "calcification_count", "density_category", "prior_finding_flag"]},
            {"name": "Length of Stay Predictor", "model_type": "regression", "project_id": "proj-hls-3", "features": ["admission_type", "diagnosis_group", "procedure_count", "age", "insurance_type", "ed_arrival", "acuity_score", "bed_availability", "staffing_ratio", "day_of_week"]},
            {"name": "Claim Denial Risk Scorer", "model_type": "classification", "project_id": "proj-hls-4", "features": ["cpt_code", "icd10_primary", "modifier_count", "prior_auth_flag", "payer_type", "provider_specialty", "claim_amount", "days_to_submit", "documentation_score", "historic_denial_rate"]},
            {"name": "Drug Efficacy Predictor", "model_type": "regression", "project_id": "proj-hls-4", "features": ["molecular_weight", "logp", "hbd_count", "hba_count", "rotatable_bonds", "tpsa", "target_affinity", "selectivity_score", "solubility", "bioavailability"]},
        ],
        "agents": [
            {"name": "Clinical Decision Support Agent", "project_id": "proj-hls-1", "tools": ["EHR Lookup", "Drug Interaction DB", "Clinical Guidelines", "Lab Results API", "Risk Calculator"]},
            {"name": "Prior Authorization Agent", "project_id": "proj-hls-2", "tools": ["Payer Portal", "Documentation Extractor", "CPT Lookup", "Appeal Generator", "Status Tracker"]},
            {"name": "Clinical Trial Matching Agent", "project_id": "proj-hls-3", "tools": ["Trial Registry", "Patient Screener", "Eligibility Checker", "Site Matcher", "Consent Coordinator"]},
            {"name": "Radiology Copilot", "project_id": "proj-hls-4", "tools": ["Image Analyzer", "Finding Comparator", "Report Generator", "Follow-up Scheduler", "Quality Checker"]},
        ],
        "projects": ["proj-hls-1", "proj-hls-2", "proj-hls-3", "proj-hls-4"],
    },
    "retail": {
        "models": [
            {"name": "Customer Churn Predictor", "model_type": "classification", "project_id": "proj-ret-1", "features": ["days_since_purchase", "order_frequency", "avg_order_value", "returns_rate", "loyalty_tier", "email_engagement", "app_sessions", "support_tickets", "promo_usage", "category_diversity"]},
            {"name": "Demand Forecaster", "model_type": "regression", "project_id": "proj-ret-1", "features": ["historical_sales", "seasonality", "price_elasticity", "promo_calendar", "weather_index", "competitor_activity", "inventory_level", "day_of_week", "holiday_flag", "trend_component"]},
            {"name": "Product Recommendation Engine", "model_type": "classification", "project_id": "proj-ret-2", "features": ["browsing_history", "purchase_history", "cart_contents", "user_segment", "time_of_day", "device_type", "page_dwell_time", "search_query", "price_sensitivity", "brand_affinity"]},
            {"name": "Fraud Detection Model", "model_type": "classification", "project_id": "proj-ret-2", "features": ["transaction_amount", "velocity_1h", "geo_distance", "device_fingerprint", "time_since_last", "card_present", "merchant_category", "avs_match", "cvv_match", "account_age"]},
        ],
        "agents": [
            {"name": "Customer Service Agent", "project_id": "proj-ret-1", "tools": ["Order Lookup", "Return Processor", "FAQ Search", "Escalation Router", "Satisfaction Survey"]},
            {"name": "Merchandising Copilot", "project_id": "proj-ret-2", "tools": ["Trend Analyzer", "Price Optimizer", "Assortment Planner", "Markdown Calculator", "Competitor Monitor"]},
        ],
        "projects": ["proj-ret-1", "proj-ret-2"],
    },
    "industrials": {
        "models": [
            {"name": "Equipment Failure Predictor", "model_type": "classification", "project_id": "proj-ind-1", "features": ["vibration_rms", "bearing_temp", "motor_current", "hours_since_overhaul", "oil_viscosity", "pressure_diff", "cycle_count", "ambient_temp", "maintenance_score", "equipment_age"]},
            {"name": "Defect Classification Model", "model_type": "classification", "project_id": "proj-ind-2", "features": ["pixel_intensity", "edge_count", "texture_score", "symmetry_index", "size_mm", "color_deviation", "surface_roughness", "contour_match", "region_density", "defect_history"]},
            {"name": "Demand Forecaster", "model_type": "regression", "project_id": "proj-ind-3", "features": ["historical_orders", "lead_time", "seasonality", "raw_material_price", "supplier_reliability", "production_capacity", "backlog_days", "economic_index", "competitor_activity", "holiday_flag"]},
            {"name": "Energy Consumption Optimizer", "model_type": "regression", "project_id": "proj-ind-1", "features": ["power_draw_kw", "ambient_temp", "production_volume", "shift_type", "equipment_age", "cooling_efficiency", "occupancy_rate", "time_of_day", "day_of_week", "weather_index"]},
            {"name": "Safety Incident Predictor", "model_type": "classification", "project_id": "proj-ind-2", "features": ["near_miss_count", "training_hours", "shift_fatigue_index", "equipment_condition", "weather_severity", "overtime_hours", "incident_history", "ppe_compliance", "housekeeping_score", "experience_years"]},
            {"name": "Yield Optimization Model", "model_type": "regression", "project_id": "proj-ind-3", "features": ["temperature_setpoint", "pressure_psi", "feed_rate", "catalyst_age", "humidity_pct", "batch_size", "raw_material_grade", "mixing_duration", "cooling_rate", "additive_concentration"]},
        ],
        "agents": [
            {"name": "Maintenance Planning Agent", "project_id": "proj-ind-1", "tools": ["CMMS Lookup", "Spare Parts Inventory", "Work Order Generator", "Schedule Optimizer", "Failure Mode DB"]},
            {"name": "Quality Inspection Agent", "project_id": "proj-ind-2", "tools": ["Image Analyzer", "Defect Classifier", "Root Cause Finder", "SPC Chart Generator", "Corrective Action DB"]},
            {"name": "Supply Chain Agent", "project_id": "proj-ind-3", "tools": ["ERP Connector", "Supplier Portal", "Demand Planner", "Route Optimizer", "Risk Assessor"]},
        ],
        "projects": ["proj-ind-1", "proj-ind-2", "proj-ind-3"],
    },
    "hospitality": {
        "models": [
            {"name": "Guest Satisfaction Predictor", "model_type": "classification", "project_id": "proj-hosp-1", "features": ["stay_duration", "room_type", "amenity_usage", "service_requests", "loyalty_tier", "prior_stays", "booking_channel", "check_in_wait", "dining_spend", "spa_usage"]},
            {"name": "Dynamic Pricing Model", "model_type": "regression", "project_id": "proj-hosp-2", "features": ["occupancy_rate", "day_of_week", "season", "competitor_rate", "event_proximity", "booking_window", "room_type", "demand_forecast", "cancellation_rate", "channel_mix"]},
            {"name": "No-Show Predictor", "model_type": "classification", "project_id": "proj-hosp-3", "features": ["booking_lead_days", "deposit_paid", "loyalty_tier", "prior_no_shows", "group_size", "rate_type", "day_of_week", "weather_forecast", "event_flag", "cancellation_policy"]},
            {"name": "Revenue Forecast Model", "model_type": "regression", "project_id": "proj-hosp-2", "features": ["historical_revenue", "occupancy_trend", "adr_trend", "market_demand", "group_bookings", "seasonal_index", "competitor_supply", "event_calendar", "economic_index", "marketing_spend"]},
            {"name": "Housekeeping Optimizer", "model_type": "regression", "project_id": "proj-hosp-3", "features": ["checkout_count", "stay_overs", "room_type", "floor_level", "special_requests", "staff_available", "time_per_room", "priority_guests", "late_checkouts", "maintenance_flags"]},
        ],
        "agents": [
            {"name": "Concierge Assistant", "project_id": "proj-hosp-1", "tools": ["Reservation System", "Local Recommendations", "Transportation Booker", "Dining Reservations", "Activity Planner"]},
            {"name": "Revenue Management Agent", "project_id": "proj-hosp-2", "tools": ["Rate Shopper", "Demand Forecaster", "Channel Manager", "Competitor Monitor", "Yield Analyzer"]},
            {"name": "Guest Service Agent", "project_id": "proj-hosp-3", "tools": ["CRM Lookup", "Service Request Handler", "Complaint Resolver", "Loyalty Manager", "Feedback Analyzer"]},
        ],
        "projects": ["proj-hosp-1", "proj-hosp-2", "proj-hosp-3"],
    },
}

# Scenarios define how metrics evolve over time
SCENARIOS = {
    "healthy": {"base_perf": 0.94, "trend": 0.0, "noise": 0.01, "drift_base": 0.05, "drift_trend": 0.0},
    "degrading": {"base_perf": 0.92, "trend": -0.001, "noise": 0.015, "drift_base": 0.08, "drift_trend": 0.002},
    "critical": {"base_perf": 0.88, "trend": -0.002, "noise": 0.02, "drift_base": 0.15, "drift_trend": 0.004},
    "recovering": {"base_perf": 0.85, "trend": 0.0015, "noise": 0.015, "drift_base": 0.20, "drift_trend": -0.002},
    "operational": {"base_perf": 0.92, "trend": 0.0, "noise": 0.02, "drift_base": 0.0, "drift_trend": 0.0},
    "agent_degraded": {"base_perf": 0.85, "trend": -0.001, "noise": 0.03, "drift_base": 0.0, "drift_trend": 0.0},
}

# ── Project metadata per industry ───────────────────────────────────────────
PROJECT_META = {
    "hls": {
        "proj-hls-1": {"name": "Patient Safety", "description": "Adverse event detection and patient risk stratification", "owner": "Dr. James Okafor", "team": "Clinical AI"},
        "proj-hls-2": {"name": "Clinical Trials", "description": "Patient enrollment prediction and protocol optimization", "owner": "Dr. Sarah Chen", "team": "Research Analytics"},
        "proj-hls-3": {"name": "Medical Imaging", "description": "Automated radiology analysis and anomaly detection", "owner": "Dr. Lisa Park", "team": "Imaging AI"},
        "proj-hls-4": {"name": "Revenue Cycle", "description": "Claims denial prediction and authorization optimization", "owner": "Michael Torres", "team": "Operations Analytics"},
    },
    "retail": {
        "proj-ret-1": {"name": "Customer Intelligence", "description": "Churn prediction and lifetime value modeling", "owner": "Jessica Liu", "team": "Data Science"},
        "proj-ret-2": {"name": "Merchandising", "description": "Product recommendations and fraud detection", "owner": "Marcus Johnson", "team": "ML Platform"},
    },
    "industrials": {
        "proj-ind-1": {"name": "Predictive Maintenance", "description": "Equipment failure prediction and energy optimization", "owner": "Karl Jenssen", "team": "Industrial AI"},
        "proj-ind-2": {"name": "Quality Control", "description": "Defect classification and safety incident prevention", "owner": "Mei-Lin Huang", "team": "Quality Engineering"},
        "proj-ind-3": {"name": "Supply Chain", "description": "Demand forecasting and yield optimization", "owner": "David Okonkwo", "team": "Operations Research"},
    },
    "hospitality": {
        "proj-hosp-1": {"name": "Guest Experience", "description": "Guest satisfaction prediction and personalized service", "owner": "Elena Vasquez", "team": "Guest Intelligence"},
        "proj-hosp-2": {"name": "Revenue Management", "description": "Dynamic pricing and revenue forecasting", "owner": "Raj Krishnamurthy", "team": "Revenue Analytics"},
        "proj-hosp-3": {"name": "Operations", "description": "No-show prediction and housekeeping optimization", "owner": "Tomoko Yamada", "team": "Ops Analytics"},
    },
}

# ── Industry-specific compliance templates ──────────────────────────────────
COMPLIANCE_TEMPLATES = {
    "hls": {
        "phi_handling": "De-identified per Safe Harbor",
        "data_classification": "PHI",
        "encryption_at_rest": True,
        "encryption_in_transit": True,
        "access_control": "Role-Based (RBAC)",
        "audit_logging": True,
        "baa_signed": True,
        "last_risk_assessment": "2026-06-15",
        "deid_method": "Safe Harbor",
        "min_necessary": True,
        "retention_days": 2555,
        "compliant": True,
    },
    "retail": {
        "phi_handling": "PII Protected",
        "data_classification": "Customer Data",
        "encryption_at_rest": True,
        "encryption_in_transit": True,
        "access_control": "Role-Based (RBAC)",
        "audit_logging": True,
        "baa_signed": False,
        "last_risk_assessment": "2026-06-10",
        "deid_method": "Pseudonymization",
        "min_necessary": True,
        "retention_days": 1095,
        "compliant": True,
    },
    "industrials": {
        "phi_handling": "N/A - No PHI",
        "data_classification": "Proprietary",
        "encryption_at_rest": True,
        "encryption_in_transit": True,
        "access_control": "Role-Based (RBAC)",
        "audit_logging": True,
        "baa_signed": False,
        "last_risk_assessment": "2026-06-01",
        "deid_method": "N/A",
        "min_necessary": True,
        "retention_days": 1825,
        "compliant": True,
    },
    "hospitality": {
        "phi_handling": "PII Protected",
        "data_classification": "Guest PII",
        "encryption_at_rest": True,
        "encryption_in_transit": True,
        "access_control": "Role-Based (RBAC)",
        "audit_logging": True,
        "baa_signed": False,
        "last_risk_assessment": "2026-06-15",
        "deid_method": "Pseudonymization",
        "min_necessary": True,
        "retention_days": 1095,
        "compliant": True,
    },
}

# ── Model algorithm assignments ─────────────────────────────────────────────
ALGORITHMS = ["XGBoost", "LightGBM", "Random Forest", "Neural Network", "Logistic Regression",
              "Gradient Boosting", "CatBoost", "Linear Regression"]

AGENT_FRAMEWORKS = ["LangChain", "Semantic Kernel", "AutoGen", "CrewAI"]
AGENT_LLM_BACKBONES = ["GPT-4o", "Claude 3.5 Sonnet", "Gemini Pro", "Llama 3.1 70B"]

DEFAULT_SCENARIOS_MODELS = ["healthy", "degrading", "critical", "recovering", "healthy", "healthy", "degrading", "healthy"]
DEFAULT_SCENARIOS_AGENTS = ["operational", "agent_degraded", "operational", "operational"]


def _generate_entity_ref(entity_type, name, index):
    """Generate a stable source_entity_ref for an entity."""
    slug = name.lower().replace(" ", "-").replace("&", "and")[:30]
    if entity_type == "model":
        return f"mlflow://experiment-{index + 1}/{slug}"
    return f"agent://{slug}"


def _generate_entity_id(entity_type, index):
    """Generate a deterministic entity_id."""
    return f"{entity_type}-synth-{index + 1:03d}"


class SyntheticDataGenerator:
    """Generates synthetic telemetry CSVs for testing."""

    def __init__(self, industry="hls", days=90, seed=42, entities=None,
                 scenarios=None, include_edge_cases=True, output_dir="data/synthetic"):
        self.industry = industry
        self.days = days
        self.seed = seed
        self.include_edge_cases = include_edge_cases
        self.output_dir = Path(output_dir)
        self.rng = random.Random(seed)
        self.now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
        self.start = self.now - timedelta(days=days)

        industry_data = INDUSTRY_ENTITIES.get(industry, INDUSTRY_ENTITIES["hls"])
        all_models = industry_data["models"]
        all_agents = industry_data["agents"]

        # Limit entities if requested
        if entities is not None:
            n_models = max(1, int(entities * 0.7))
            n_agents = max(1, entities - n_models)
            all_models = all_models[:n_models]
            all_agents = all_agents[:n_agents]

        # Assign scenarios
        if scenarios:
            model_scenarios = scenarios
        else:
            model_scenarios = DEFAULT_SCENARIOS_MODELS

        agent_scenarios = DEFAULT_SCENARIOS_AGENTS

        # Build entity list
        self.entities = []
        for i, model_def in enumerate(all_models):
            scenario = model_scenarios[i % len(model_scenarios)]
            project_id = model_def["project_id"]
            proj_meta = PROJECT_META.get(industry, {}).get(project_id, {})
            compliance = dict(COMPLIANCE_TEMPLATES.get(industry, COMPLIANCE_TEMPLATES["industrials"]))
            self.entities.append({
                "entity_id": _generate_entity_id("model", i),
                "entity_type": "model",
                "source_entity_ref": _generate_entity_ref("model", model_def["name"], i),
                "name": model_def["name"],
                "model_type": model_def["model_type"],
                "algorithm": ALGORITHMS[i % len(ALGORITHMS)],
                "version": f"{self.rng.randint(1, 4)}.{self.rng.randint(0, 9)}.{self.rng.randint(0, 9)}",
                "owner": proj_meta.get("owner", "Unknown"),
                "description": model_def["name"] + " — production model",
                "scenario": scenario,
                "project_id": project_id,
                "features": model_def["features"],
                "hipaa": compliance,
                "predictions_today": self.rng.randint(1000, 20000),
                "avg_latency_ms": self.rng.randint(20, 150),
            })

        for i, agent_def in enumerate(all_agents):
            scenario = agent_scenarios[i % len(agent_scenarios)]
            project_id = agent_def["project_id"]
            proj_meta = PROJECT_META.get(industry, {}).get(project_id, {})
            compliance = dict(COMPLIANCE_TEMPLATES.get(industry, COMPLIANCE_TEMPLATES["industrials"]))
            self.entities.append({
                "entity_id": _generate_entity_id("agent", i),
                "entity_type": "agent",
                "source_entity_ref": _generate_entity_ref("agent", agent_def["name"], i),
                "name": agent_def["name"],
                "framework": AGENT_FRAMEWORKS[i % len(AGENT_FRAMEWORKS)],
                "llm_backbone": AGENT_LLM_BACKBONES[i % len(AGENT_LLM_BACKBONES)],
                "version": f"{self.rng.randint(1, 3)}.{self.rng.randint(0, 5)}.0",
                "owner": proj_meta.get("owner", "Unknown"),
                "description": agent_def["name"] + " — AI assistant",
                "scenario": scenario,
                "project_id": project_id,
                "tools": agent_def["tools"],
                "hipaa": compliance,
            })

        self.models = [e for e in self.entities if e["entity_type"] == "model"]
        self.agents = [e for e in self.entities if e["entity_type"] == "agent"]

    def generate_all(self):
        """Generate all CSV files and manifest."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rng = random.Random(self.seed)  # Reset for determinism

        files = []
        files.append(self._generate_model_metrics())
        files.append(self._generate_agent_metrics())
        files.append(self._generate_drift_events())
        files.append(self._generate_alerts())
        files.append(self._generate_agent_traces())
        files.append(self._generate_lifecycle_events())
        files.append(self._generate_data_quality())
        files.append(self._generate_cohort_metrics())
        files.append(self._generate_feature_importance())

        # Edge cases
        edge_cases = {"duplicate_event_ids": 0, "late_arrivals": 0,
                      "out_of_order": 0, "missing_fields": 0, "schema_violations": 0}
        if self.include_edge_cases:
            edge_cases = self._inject_edge_cases(files)

        manifest = self._generate_manifest(files, edge_cases)
        return manifest

    def _generate_model_metrics(self):
        """Generate model_metrics.csv."""
        filepath = self.output_dir / "model_metrics.csv"
        rows = []
        metric_names_cls = ["accuracy", "precision", "recall", "f1_score", "auc_roc"]
        metric_names_reg = ["r2_score", "mae", "rmse", "mape"]

        for model in self.models:
            scenario = SCENARIOS[model["scenario"]]
            metrics = metric_names_cls if model["model_type"] == "classification" else metric_names_reg

            for day in range(self.days):
                ts = self.start + timedelta(days=day, hours=self.rng.randint(0, 23))
                for metric_name in metrics:
                    base = scenario["base_perf"]
                    if metric_name in ("mae", "rmse"):
                        base = (1 - scenario["base_perf"]) * 50
                        value = base - scenario["trend"] * day * 50 + self.rng.gauss(0, scenario["noise"] * 20)
                        value = max(0.1, value)
                    elif metric_name == "mape":
                        base = (1 - scenario["base_perf"]) * 100
                        value = base - scenario["trend"] * day * 100 + self.rng.gauss(0, scenario["noise"] * 10)
                        value = max(0.1, value)
                    else:
                        value = base + scenario["trend"] * day + self.rng.gauss(0, scenario["noise"])
                        value = max(0, min(1, value))

                    rows.append({
                        "source_entity_ref": model["source_entity_ref"],
                        "metric_name": metric_name,
                        "metric_value": round(value, 4),
                        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "model_type": model["model_type"],
                        "dimensions": json.dumps({"cohort": "all"}),
                    })

        self._write_csv(filepath, rows, ["source_entity_ref", "metric_name", "metric_value", "timestamp", "model_type", "dimensions"])
        return {"path": "model_metrics.csv", "row_count": len(rows), "event_type": "metric"}

    def _generate_agent_metrics(self):
        """Generate agent_metrics.csv with daily time-series for agents."""
        filepath = self.output_dir / "agent_metrics.csv"
        rows = []
        agent_metric_names = ["task_completion", "groundedness", "safety",
                              "input_tokens", "output_tokens", "cost_per_day"]

        for agent in self.agents:
            scenario = SCENARIOS[agent["scenario"]]
            for day in range(self.days):
                ts = self.start + timedelta(days=day, hours=self.rng.randint(0, 23))
                for metric_name in agent_metric_names:
                    if metric_name in ("task_completion", "groundedness", "safety"):
                        base = scenario["base_perf"]
                        value = base + scenario["trend"] * day + self.rng.gauss(0, scenario["noise"])
                        value = max(0.5, min(1.0, value))
                    elif metric_name == "input_tokens":
                        value = self.rng.randint(800, 4000) + (50 if agent["scenario"] == "agent_degraded" else 0)
                    elif metric_name == "output_tokens":
                        value = self.rng.randint(300, 2500)
                    else:  # cost_per_day
                        value = round(self.rng.uniform(1.0, 20.0), 2)

                    rows.append({
                        "source_entity_ref": agent["source_entity_ref"],
                        "metric_name": metric_name,
                        "metric_value": round(value, 4) if isinstance(value, float) else value,
                        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "model_type": "agent",
                        "dimensions": json.dumps({"cohort": "all"}),
                    })

        self._write_csv(filepath, rows, ["source_entity_ref", "metric_name", "metric_value", "timestamp", "model_type", "dimensions"])
        return {"path": "agent_metrics.csv", "row_count": len(rows), "event_type": "metric"}

    def _generate_feature_importance(self):
        """Generate feature_importance.csv."""
        filepath = self.output_dir / "feature_importance.csv"
        rows = []

        for model in self.models:
            features = model.get("features", [])
            n = len(features)
            if n == 0:
                continue
            # Generate decreasing importance values that sum to ~1.0
            raw = sorted([self.rng.random() for _ in range(n)], reverse=True)
            total = sum(raw)
            importances = [round(v / total, 4) for v in raw]

            for feat, imp in zip(features, importances):
                rows.append({
                    "source_entity_ref": model["source_entity_ref"],
                    "feature": feat,
                    "importance": imp,
                    "timestamp": self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

        self._write_csv(filepath, rows, ["source_entity_ref", "feature", "importance", "timestamp"])
        return {"path": "feature_importance.csv", "row_count": len(rows), "event_type": "feature_importance"}

    def _generate_drift_events(self):
        """Generate drift_events.csv."""
        filepath = self.output_dir / "drift_events.csv"
        rows = []

        for model in self.models:
            scenario = SCENARIOS[model["scenario"]]
            features = model.get("features", ["feature_1", "feature_2", "feature_3"])

            for day in range(0, self.days, max(1, self.days // 30)):
                ts = self.start + timedelta(days=day, hours=6)
                # Overall drift
                drift_val = scenario["drift_base"] + scenario["drift_trend"] * day + self.rng.gauss(0, 0.02)
                drift_val = max(0, min(1, drift_val))
                status = "critical" if drift_val > 0.25 else "warning" if drift_val > 0.1 else "normal"
                rows.append({
                    "source_entity_ref": model["source_entity_ref"],
                    "drift_type": "psi",
                    "scope": "overall",
                    "value": round(drift_val, 4),
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "status": status,
                })
                # Per-feature drift (top 3 features)
                for feat in features[:3]:
                    feat_drift = drift_val + self.rng.gauss(0, 0.05)
                    feat_drift = max(0, min(1, feat_drift))
                    feat_status = "critical" if feat_drift > 0.25 else "warning" if feat_drift > 0.1 else "normal"
                    rows.append({
                        "source_entity_ref": model["source_entity_ref"],
                        "drift_type": "psi",
                        "scope": f"feature:{feat}",
                        "value": round(feat_drift, 4),
                        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": feat_status,
                    })

        self._write_csv(filepath, rows, ["source_entity_ref", "drift_type", "scope", "value", "timestamp", "status"])
        return {"path": "drift_events.csv", "row_count": len(rows), "event_type": "drift"}

    def _generate_alerts(self):
        """Generate alerts.csv."""
        filepath = self.output_dir / "alerts.csv"
        rows = []
        alert_templates = [
            {"severity": "critical", "alert_type": "drift_threshold", "title": "PSI Exceeded Critical Threshold", "desc": "Overall PSI {val:.3f} exceeds 0.25 threshold"},
            {"severity": "warning", "alert_type": "drift_threshold", "title": "PSI Exceeded Warning Threshold", "desc": "Overall PSI {val:.3f} exceeds 0.10 threshold"},
            {"severity": "critical", "alert_type": "performance_drop", "title": "Performance Below Minimum", "desc": "{metric} dropped to {val:.3f}, below 0.80 threshold"},
            {"severity": "warning", "alert_type": "performance_drop", "title": "Performance Degradation", "desc": "{metric} dropped to {val:.3f}, below 0.90 threshold"},
            {"severity": "warning", "alert_type": "latency_spike", "title": "High Latency Detected", "desc": "Average latency {val:.0f}ms exceeds 500ms threshold"},
            {"severity": "critical", "alert_type": "safety_violation", "title": "Safety Guardrail Triggered", "desc": "PHI detected in agent response, session blocked"},
            {"severity": "warning", "alert_type": "cost_spike", "title": "Cost Budget Warning", "desc": "Daily cost ${val:.2f} approaching budget limit"},
            {"severity": "info", "alert_type": "retrain_triggered", "title": "Automated Retrain Started", "desc": "Model retrain triggered due to drift detection"},
        ]

        for entity in self.entities:
            scenario = SCENARIOS[entity["scenario"]]
            # Number of alerts proportional to severity
            n_alerts = self.rng.randint(1, 3) if entity["scenario"] == "healthy" else self.rng.randint(3, 8)
            if entity["scenario"] == "critical":
                n_alerts = self.rng.randint(6, 12)

            for _ in range(n_alerts):
                template = self.rng.choice(alert_templates)
                day = self.rng.randint(0, self.days - 1)
                ts = self.start + timedelta(days=day, hours=self.rng.randint(0, 23), minutes=self.rng.randint(0, 59))
                val = self.rng.uniform(0.5, 1.0) if "performance" in template["alert_type"] else self.rng.uniform(0.1, 0.5)
                rows.append({
                    "source_entity_ref": entity["source_entity_ref"],
                    "severity": template["severity"],
                    "alert_type": template["alert_type"],
                    "title": template["title"],
                    "description": template["desc"].format(val=val, metric="accuracy"),
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

        self._write_csv(filepath, rows, ["source_entity_ref", "severity", "alert_type", "title", "description", "timestamp"])
        return {"path": "alerts.csv", "row_count": len(rows), "event_type": "alert"}

    def _generate_agent_traces(self):
        """Generate agent_traces.csv."""
        filepath = self.output_dir / "agent_traces.csv"
        rows = []
        queries = [
            "What is the patient's current risk level?",
            "Summarize the latest lab results",
            "Check for drug interactions with current medications",
            "What clinical trials is this patient eligible for?",
            "Generate a discharge summary draft",
            "Review the prior authorization status",
            "What are the recommended follow-up actions?",
            "Analyze the imaging findings from today's scan",
        ]
        responses = [
            "Based on the analysis, the patient shows moderate risk...",
            "The latest results indicate normal ranges for most markers...",
            "No significant interactions found with the current regimen...",
            "Found 3 matching trials based on inclusion criteria...",
            "Draft summary generated with key findings and recommendations...",
            "Prior authorization approved for the requested procedure...",
            "Recommended follow-up includes lab work in 2 weeks...",
            "Imaging analysis complete, no significant abnormalities detected...",
        ]

        for agent in self.agents:
            scenario = SCENARIOS[agent["scenario"]]
            tools = agent.get("tools", ["Tool A", "Tool B", "Tool C"])
            traces_per_day = max(1, self.rng.randint(5, 20))

            for day in range(self.days):
                n_traces = traces_per_day + self.rng.randint(-2, 2)
                for t in range(max(1, n_traces)):
                    ts = self.start + timedelta(days=day, hours=self.rng.randint(8, 18), minutes=self.rng.randint(0, 59))
                    trace_id = f"trace-{agent['entity_id']}-d{day:03d}-t{t:03d}"

                    # Generate steps
                    n_steps = self.rng.randint(1, min(4, len(tools)))
                    steps = []
                    total_latency = 0
                    for s in range(n_steps):
                        tool = tools[s % len(tools)]
                        lat = self.rng.randint(50, 800)
                        if agent["scenario"] == "agent_degraded":
                            lat = int(lat * 1.5)
                        total_latency += lat
                        steps.append({
                            "tool": tool,
                            "latency_ms": lat,
                            "status": "success" if self.rng.random() > 0.05 else "error",
                        })

                    voice_score = scenario["base_perf"] + self.rng.gauss(0, 0.03)
                    voice_score = max(0.5, min(1.0, voice_score))
                    policy_pass = self.rng.random() > (0.05 if agent["scenario"] == "operational" else 0.15)
                    token_count = self.rng.randint(500, 2000)

                    rows.append({
                        "source_entity_ref": agent["source_entity_ref"],
                        "trace_id": trace_id,
                        "query": self.rng.choice(queries),
                        "response": self.rng.choice(responses),
                        "total_latency_ms": total_latency,
                        "token_count": token_count,
                        "voice_score": round(voice_score, 3),
                        "policy_pass": str(policy_pass).lower(),
                        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "steps_json": json.dumps(steps),
                    })

        self._write_csv(filepath, rows, ["source_entity_ref", "trace_id", "query", "response", "total_latency_ms", "token_count", "voice_score", "policy_pass", "timestamp", "steps_json"])
        return {"path": "agent_traces.csv", "row_count": len(rows), "event_type": "trace"}

    def _generate_lifecycle_events(self):
        """Generate lifecycle_events.csv."""
        filepath = self.output_dir / "lifecycle_events.csv"
        rows = []
        triggers = ["Scheduled retrain", "Drift threshold exceeded", "Performance degradation",
                    "New training data", "Manual request", "Prompt optimization",
                    "Tool integration update", "Safety guardrail update"]

        for entity in self.entities:
            # Generate 2-5 lifecycle events per entity
            n_events = self.rng.randint(2, 5)
            if entity["scenario"] == "recovering":
                n_events = self.rng.randint(4, 6)

            for i in range(n_events):
                day = int(self.days * i / n_events) + self.rng.randint(0, max(1, self.days // n_events - 1))
                day = min(day, self.days - 1)
                ts = self.start + timedelta(days=day, hours=self.rng.randint(6, 18))

                if entity["entity_type"] == "model":
                    event_type = self.rng.choice(["deployed", "retrained", "config_change"])
                    version = f"v{i + 1}.{self.rng.randint(0, 3)}.{self.rng.randint(0, 9)}"
                    metadata = {
                        "training_records": self.rng.randint(10000, 500000),
                        "training_duration_min": self.rng.randint(15, 480),
                        "status": "Production" if i == n_events - 1 else "Retired",
                        "champion_challenger": "Champion" if i == n_events - 1 else "Retired",
                    }
                else:
                    event_type = self.rng.choice(["deployed", "config_change", "config_change"])
                    version = f"v{i + 1}.{self.rng.randint(0, 5)}.0"
                    metadata = {
                        "status": "Production" if i == n_events - 1 else "Retired",
                        "champion_challenger": "Champion" if i == n_events - 1 else "Retired",
                    }

                rows.append({
                    "source_entity_ref": entity["source_entity_ref"],
                    "event_type": event_type,
                    "version": version,
                    "trigger": self.rng.choice(triggers),
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "metadata_json": json.dumps(metadata),
                })

        self._write_csv(filepath, rows, ["source_entity_ref", "event_type", "version", "trigger", "timestamp", "metadata_json"])
        return {"path": "lifecycle_events.csv", "row_count": len(rows), "event_type": "lifecycle"}

    def _generate_data_quality(self):
        """Generate data_quality.csv."""
        filepath = self.output_dir / "data_quality.csv"
        rows = []

        for model in self.models:
            features = model.get("features", ["feat_1", "feat_2", "feat_3"])
            scenario = SCENARIOS[model["scenario"]]

            for day in range(0, self.days, max(1, self.days // 30)):
                ts = self.start + timedelta(days=day, hours=2)
                for feat in features:
                    missing_base = 0.01 if model["scenario"] == "healthy" else 0.03
                    missing_rate = missing_base + self.rng.gauss(0, 0.005)
                    missing_rate = max(0, min(0.3, missing_rate))

                    outlier_rate = 0.005 + self.rng.gauss(0, 0.002)
                    outlier_rate = max(0, min(0.1, outlier_rate))

                    schema_valid = "true" if self.rng.random() > 0.02 else "false"
                    row_count = self.rng.randint(5000, 50000)

                    rows.append({
                        "source_entity_ref": model["source_entity_ref"],
                        "feature": feat,
                        "missing_rate": round(missing_rate, 4),
                        "outlier_rate": round(outlier_rate, 4),
                        "schema_valid": schema_valid,
                        "row_count": row_count,
                        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })

        self._write_csv(filepath, rows, ["source_entity_ref", "feature", "missing_rate", "outlier_rate", "schema_valid", "row_count", "timestamp"])
        return {"path": "data_quality.csv", "row_count": len(rows), "event_type": "metric"}

    def _generate_cohort_metrics(self):
        """Generate cohort_metrics.csv."""
        filepath = self.output_dir / "cohort_metrics.csv"
        rows = []
        cohort_definitions = {
            "age_group": ["18-30", "31-45", "46-60", "61-75", "75+"],
            "sex": ["Female", "Male", "Other"],
            "insurance": ["Commercial", "Medicare", "Medicaid", "Self-pay"],
        }

        for model in self.models:
            scenario = SCENARIOS[model["scenario"]]

            for day in range(0, self.days, max(1, self.days // 15)):
                ts = self.start + timedelta(days=day, hours=4)
                for dim_name, cohorts in cohort_definitions.items():
                    for cohort in cohorts:
                        base = scenario["base_perf"] + scenario["trend"] * day
                        variation = self.rng.uniform(-0.08, 0.03)
                        value = max(0.5, min(1.0, base + variation + self.rng.gauss(0, 0.01)))
                        sample_size = self.rng.randint(100, 5000)

                        rows.append({
                            "source_entity_ref": model["source_entity_ref"],
                            "cohort_name": cohort,
                            "cohort_dim": dim_name,
                            "metric_name": "accuracy" if model["model_type"] == "classification" else "r2_score",
                            "value": round(value, 4),
                            "sample_size": sample_size,
                            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        })

        self._write_csv(filepath, rows, ["source_entity_ref", "cohort_name", "cohort_dim", "metric_name", "value", "sample_size", "timestamp"])
        return {"path": "cohort_metrics.csv", "row_count": len(rows), "event_type": "prediction"}

    def _inject_edge_cases(self, files):
        """Inject edge cases into existing CSV files."""
        edge_cases = {
            "duplicate_event_ids": 0,
            "late_arrivals": 0,
            "out_of_order": 0,
            "missing_fields": 0,
            "schema_violations": 0,
        }

        # Duplicates: append duplicate rows to model_metrics.csv
        metrics_path = self.output_dir / "model_metrics.csv"
        if metrics_path.exists():
            with open(metrics_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_rows = list(reader)
                fieldnames = reader.fieldnames

            # Pick 15 random rows to duplicate
            n_dups = min(15, len(all_rows))
            dup_indices = self.rng.sample(range(len(all_rows)), n_dups)
            for idx in dup_indices:
                all_rows.append(dict(all_rows[idx]))
            edge_cases["duplicate_event_ids"] = n_dups

            # Late arrivals: modify 30 rows to have timestamp 8h behind
            n_late = min(30, len(all_rows))
            late_indices = self.rng.sample(range(len(all_rows)), n_late)
            for idx in late_indices:
                row = all_rows[idx]
                try:
                    ts = datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
                    row["timestamp"] = (ts - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
                except (ValueError, KeyError):
                    pass
            edge_cases["late_arrivals"] = n_late

            # Out-of-order: shuffle 50 rows
            n_shuffle = min(50, len(all_rows) - 1)
            for _ in range(n_shuffle):
                i = self.rng.randint(0, len(all_rows) - 2)
                all_rows[i], all_rows[i + 1] = all_rows[i + 1], all_rows[i]
            edge_cases["out_of_order"] = n_shuffle

            # Missing fields: blank out metric_value in 10 rows
            n_missing = min(10, len(all_rows))
            missing_indices = self.rng.sample(range(len(all_rows)), n_missing)
            for idx in missing_indices:
                all_rows[idx]["metric_value"] = ""
            edge_cases["missing_fields"] = n_missing

            # Schema violations: put non-numeric in metric_value for 5 rows
            n_violations = min(5, len(all_rows))
            violation_indices = self.rng.sample(range(len(all_rows)), n_violations)
            for idx in violation_indices:
                all_rows[idx]["metric_value"] = "NOT_A_NUMBER"
            edge_cases["schema_violations"] = n_violations

            # Rewrite the file
            with open(metrics_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)

            # Update row count in files list
            for file_info in files:
                if file_info["path"] == "model_metrics.csv":
                    file_info["row_count"] = len(all_rows)

        return edge_cases

    def _generate_manifest(self, files, edge_cases):
        """Generate manifest.json with enriched entity metadata."""
        # Include all entity fields except internal-only ones
        entity_list = []
        for e in self.entities:
            entry = {k: v for k, v in e.items() if k not in ("tools", "features")}
            # Include tools/features in manifest for loader to store
            if "features" in e:
                entry["features"] = e["features"]
            if "tools" in e:
                entry["tools"] = e["tools"]
            entity_list.append(entry)

        project_meta = PROJECT_META.get(self.industry, {})
        projects = []
        for pid, meta in project_meta.items():
            projects.append({"id": pid, **meta})

        manifest = {
            "generated_at": self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": self.seed,
            "industry": self.industry,
            "days": self.days,
            "projects": projects,
            "entities": entity_list,
            "files": files,
            "edge_cases": edge_cases,
        }
        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return manifest

    def _write_csv(self, filepath, rows, fieldnames):
        """Write rows to a CSV file."""
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic telemetry data for ML Works testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python tools/generate_synthetic_data.py --industry hls --days 90 --seed 42
  python tools/generate_synthetic_data.py --days 7 --entities 2 --output-dir data/synthetic/quick
  python tools/generate_synthetic_data.py --industry retail --include-edge-cases
""",
    )
    parser.add_argument("--industry", default="hls", choices=["hls", "retail", "industrials", "hospitality"],
                        help="Industry dataset to use (default: hls)")
    parser.add_argument("--days", type=int, default=90,
                        help="Number of days of historical data (default: 90)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--entities", type=int, default=None,
                        help="Limit total number of entities (default: all)")
    parser.add_argument("--scenarios", type=str, default=None,
                        help="Comma-separated model scenarios (default: auto)")
    parser.add_argument("--include-edge-cases", action="store_true", default=True,
                        help="Include edge cases: duplicates, late arrivals, etc. (default: True)")
    parser.add_argument("--no-edge-cases", action="store_true",
                        help="Disable edge case injection")
    parser.add_argument("--output-dir", default="data/synthetic",
                        help="Output directory (default: data/synthetic)")

    args = parser.parse_args()

    scenarios = None
    if args.scenarios:
        scenarios = [s.strip() for s in args.scenarios.split(",")]

    include_edge_cases = args.include_edge_cases and not args.no_edge_cases

    gen = SyntheticDataGenerator(
        industry=args.industry,
        days=args.days,
        seed=args.seed,
        entities=args.entities,
        scenarios=scenarios,
        include_edge_cases=include_edge_cases,
        output_dir=args.output_dir,
    )

    manifest = gen.generate_all()

    print(f"Generated synthetic data in: {args.output_dir}")
    print(f"  Industry: {args.industry}")
    print(f"  Days: {args.days}")
    print(f"  Seed: {args.seed}")
    print(f"  Entities: {len(manifest['entities'])} ({len(gen.models)} models, {len(gen.agents)} agents)")
    print(f"  Files:")
    for f in manifest["files"]:
        print(f"    {f['path']}: {f['row_count']:,} rows ({f['event_type']})")
    if include_edge_cases:
        ec = manifest["edge_cases"]
        print(f"  Edge cases: {ec['duplicate_event_ids']} duplicates, {ec['late_arrivals']} late, "
              f"{ec['missing_fields']} missing, {ec['schema_violations']} violations")
    print(f"  Manifest: manifest.json")


if __name__ == "__main__":
    main()
