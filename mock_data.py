"""Mock data generator for ML Monitoring prototype."""

import random
from datetime import datetime, timedelta

random.seed(42)

PROJECTS = [
    {
        "id": "proj-1",
        "name": "Clinical Trials",
        "description": "Clinical trial optimization, patient enrollment, and outcome prediction",
        "owner": "Dr. Sarah Chen",
        "created_date": "2024-03-15",
        "status": "Active",
    },
    {
        "id": "proj-2",
        "name": "Patient Safety",
        "description": "Adverse event detection and pharmacovigilance models",
        "owner": "Dr. James Wilson",
        "created_date": "2024-01-20",
        "status": "Active",
    },
    {
        "id": "proj-3",
        "name": "Population Health",
        "description": "Chronic disease progression and population health analytics",
        "owner": "Dr. Maria Garcia",
        "created_date": "2024-05-10",
        "status": "Active",
    },
    {
        "id": "proj-4",
        "name": "Drug Discovery",
        "description": "Compound screening and molecular property prediction",
        "owner": "Dr. David Park",
        "created_date": "2024-02-28",
        "status": "Active",
    },
    {
        "id": "proj-5",
        "name": "Medical Imaging",
        "description": "Radiology AI and pathology image analysis",
        "owner": "Dr. Lisa Thompson",
        "created_date": "2024-04-05",
        "status": "Active",
    },
    {
        "id": "proj-6",
        "name": "Revenue Cycle & Operations",
        "description": "Claims optimization, denial prediction, and operational efficiency",
        "owner": "Alex Kumar",
        "created_date": "2024-06-01",
        "status": "Active",
    },
]

MODELS = [
    {
        "id": "model-1",
        "name": "Patient Readmission Risk",
        "project_id": "proj-3",
        "project_name": "Population Health",
        "owner": "Dr. Maria Garcia",
        "model_type": "classification",
        "algorithm": "XGBoost",
        "version": "v2.3.1",
        "status": "Healthy",
        "status_color": "success",
        "drift_score": 0.08,
        "performance_score": 0.94,
        "dqm_score": 0.96,
        "last_updated": "2024-11-28",
        "endpoint": "/api/v2/readmission/predict",
        "predictions_today": 15420,
        "avg_latency_ms": 45,
        "description": "Predicts 30-day hospital readmission risk based on patient demographics, diagnoses, and prior utilization.",
        "features": [
            "age", "bmi", "num_prior_admissions", "length_of_stay",
            "num_comorbidities", "discharge_disposition", "payer_type",
            "medication_count", "lab_result_abnormal_count", "ed_visits_6mo",
        ],
        "hipaa": {
            "phi_handling": "De-identified",
            "data_classification": "Limited Dataset",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-10-15",
            "deid_method": "Safe Harbor",
            "min_necessary": True,
            "retention_days": 365,
            "compliant": True,
        },
    },
    {
        "id": "model-2",
        "name": "Adverse Drug Event Detector",
        "project_id": "proj-2",
        "project_name": "Patient Safety",
        "owner": "Dr. James Wilson",
        "model_type": "classification",
        "algorithm": "LightGBM",
        "version": "v3.1.0",
        "status": "Warning",
        "status_color": "warning",
        "drift_score": 0.22,
        "performance_score": 0.89,
        "dqm_score": 0.91,
        "last_updated": "2024-11-27",
        "endpoint": "/api/v1/ade/detect",
        "predictions_today": 89340,
        "avg_latency_ms": 12,
        "description": "Real-time detection of adverse drug events from EHR medication records and clinical notes.",
        "features": [
            "drug_class", "dose_amount", "patient_weight", "renal_function",
            "hepatic_function", "drug_interactions_count", "allergy_flag",
            "age_group", "polypharmacy_score", "admin_route",
        ],
        "hipaa": {
            "phi_handling": "Tokenized",
            "data_classification": "PHI",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-09-20",
            "deid_method": "Tokenization",
            "min_necessary": True,
            "retention_days": 730,
            "compliant": True,
        },
    },
    {
        "id": "model-3",
        "name": "Disease Progression Forecaster",
        "project_id": "proj-3",
        "project_name": "Population Health",
        "owner": "Dr. Maria Garcia",
        "model_type": "regression",
        "algorithm": "Prophet + LSTM",
        "version": "v1.8.2",
        "status": "Healthy",
        "status_color": "success",
        "drift_score": 0.05,
        "performance_score": 0.91,
        "dqm_score": 0.97,
        "last_updated": "2024-11-28",
        "endpoint": "/api/v1/disease/forecast",
        "predictions_today": 240,
        "avg_latency_ms": 320,
        "description": "Forecasts chronic disease progression (HbA1c trajectory) for diabetic patients using longitudinal EHR data.",
        "features": [
            "baseline_hba1c", "fasting_glucose", "medication_adherence",
            "bmi_trend", "physical_activity_score", "diet_quality_index",
            "comorbidity_index", "time_since_diagnosis", "family_history_score", "age",
        ],
        "hipaa": {
            "phi_handling": "De-identified",
            "data_classification": "Limited Dataset",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-11-01",
            "deid_method": "Expert Determination",
            "min_necessary": True,
            "retention_days": 365,
            "compliant": True,
        },
    },
    {
        "id": "model-4",
        "name": "Molecular Activity Predictor",
        "project_id": "proj-4",
        "project_name": "Drug Discovery",
        "owner": "Dr. David Park",
        "model_type": "classification",
        "algorithm": "Graph Neural Network",
        "version": "v4.0.3",
        "status": "Degraded",
        "status_color": "danger",
        "drift_score": 0.31,
        "performance_score": 0.78,
        "dqm_score": 0.85,
        "last_updated": "2024-11-26",
        "endpoint": "/api/v2/molecule/predict",
        "predictions_today": 234560,
        "avg_latency_ms": 28,
        "description": "Predicts molecular bioactivity against target proteins for virtual compound screening in drug discovery.",
        "features": [
            "molecular_weight", "logP", "num_h_donors", "num_h_acceptors",
            "tpsa", "num_rotatable_bonds", "aromatic_rings",
            "fingerprint_similarity", "binding_affinity_proxy", "toxicity_score",
        ],
        "hipaa": {
            "phi_handling": "N/A – No PHI",
            "data_classification": "Non-PHI",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC",
            "audit_logging": False,
            "baa_signed": False,
            "last_risk_assessment": "2024-08-10",
            "deid_method": "N/A",
            "min_necessary": False,
            "retention_days": 180,
            "compliant": True,
        },
    },
    {
        "id": "model-5",
        "name": "Clinical Trial Dropout Predictor",
        "project_id": "proj-1",
        "project_name": "Clinical Trials",
        "owner": "Dr. Sarah Chen",
        "model_type": "classification",
        "algorithm": "Gradient Boosting",
        "version": "v2.5.0",
        "status": "Critical",
        "status_color": "danger",
        "drift_score": 0.45,
        "performance_score": 0.72,
        "dqm_score": 0.78,
        "last_updated": "2024-11-25",
        "endpoint": "/api/v1/trial/dropout",
        "predictions_today": 5670,
        "avg_latency_ms": 85,
        "description": "Predicts patient dropout probability in active clinical trials based on engagement and protocol compliance.",
        "features": [
            "visit_compliance_rate", "distance_to_site", "adverse_event_count",
            "protocol_complexity", "treatment_arm", "patient_age",
            "comorbidity_burden", "prior_trial_participation", "socioeconomic_index", "caregiver_support",
        ],
        "hipaa": {
            "phi_handling": "Tokenized",
            "data_classification": "PHI",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-07-18",
            "deid_method": "Tokenization",
            "min_necessary": True,
            "retention_days": 2555,
            "compliant": False,
        },
    },
    {
        "id": "model-6",
        "name": "Radiology Anomaly Detector",
        "project_id": "proj-5",
        "project_name": "Medical Imaging",
        "owner": "Dr. Lisa Thompson",
        "model_type": "classification",
        "algorithm": "EfficientNet-B7",
        "version": "v1.2.0",
        "status": "Healthy",
        "status_color": "success",
        "drift_score": 0.06,
        "performance_score": 0.93,
        "dqm_score": 0.95,
        "last_updated": "2024-11-28",
        "endpoint": "/api/v1/radiology/detect",
        "predictions_today": 1250,
        "avg_latency_ms": 150,
        "description": "Detects pulmonary nodules and consolidations on chest X-rays to assist radiologist triage.",
        "features": [
            "image_resolution", "pixel_spacing", "patient_age",
            "image_orientation", "exposure_index", "body_part",
            "manufacturer", "slice_thickness", "contrast_flag", "prior_study_available",
        ],
        "hipaa": {
            "phi_handling": "De-identified",
            "data_classification": "Limited Dataset",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-10-30",
            "deid_method": "DICOM De-identification",
            "min_necessary": True,
            "retention_days": 2555,
            "compliant": True,
        },
    },
    {
        "id": "model-7",
        "name": "Clinical Notes NLP Classifier",
        "project_id": "proj-2",
        "project_name": "Patient Safety",
        "owner": "Dr. James Wilson",
        "model_type": "classification",
        "algorithm": "BioBERT Fine-tuned",
        "version": "v3.0.1",
        "status": "Warning",
        "status_color": "warning",
        "drift_score": 0.18,
        "performance_score": 0.87,
        "dqm_score": 0.82,
        "last_updated": "2024-11-27",
        "endpoint": "/api/v1/notes/classify",
        "predictions_today": 45680,
        "avg_latency_ms": 65,
        "description": "Extracts and classifies safety signals from unstructured clinical notes and discharge summaries.",
        "features": [
            "note_length", "section_count", "medical_entity_count",
            "negation_count", "temporal_references", "medication_mentions",
            "symptom_mentions", "procedure_mentions", "abbreviation_density", "note_type",
        ],
        "hipaa": {
            "phi_handling": "Pseudonymized",
            "data_classification": "PHI",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-09-05",
            "deid_method": "Safe Harbor",
            "min_necessary": True,
            "retention_days": 365,
            "compliant": False,
        },
    },
    {
        "id": "model-8",
        "name": "Claims Denial Predictor",
        "project_id": "proj-6",
        "project_name": "Revenue Cycle & Operations",
        "owner": "Alex Kumar",
        "model_type": "classification",
        "algorithm": "CatBoost",
        "version": "v1.5.0",
        "status": "Healthy",
        "status_color": "success",
        "drift_score": 0.04,
        "performance_score": 0.96,
        "dqm_score": 0.98,
        "last_updated": "2024-11-28",
        "endpoint": "/api/v1/claims/deny-predict",
        "predictions_today": 8900,
        "avg_latency_ms": 120,
        "description": "Predicts probability of insurance claim denial before submission to reduce revenue leakage.",
        "features": [
            "cpt_code", "icd10_code", "payer_id", "provider_specialty",
            "prior_auth_flag", "modifier_count", "charge_amount",
            "days_since_service", "patient_plan_type", "historical_denial_rate",
        ],
        "hipaa": {
            "phi_handling": "De-identified",
            "data_classification": "Limited Dataset",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-11-10",
            "deid_method": "Safe Harbor",
            "min_necessary": True,
            "retention_days": 2555,
            "compliant": True,
        },
    },
]


def _generate_time_series(base_value, noise_level, trend=0, num_days=90,
                          anomaly_start=None, anomaly_magnitude=0):
    dates = []
    values = []
    today = datetime.now()
    for i in range(num_days):
        date = today - timedelta(days=num_days - 1 - i)
        dates.append(date.strftime("%Y-%m-%d"))
        value = base_value + trend * i / num_days
        value += random.gauss(0, noise_level)
        if anomaly_start and i >= anomaly_start:
            value -= anomaly_magnitude * (i - anomaly_start) / (num_days - anomaly_start)
        value = max(0, min(1, value))
        values.append(round(value, 4))
    return dates, values


def _generate_drift_series(base_drift, increase_rate=0, num_days=90, spike_day=None):
    dates = []
    values = []
    today = datetime.now()
    for i in range(num_days):
        date = today - timedelta(days=num_days - 1 - i)
        dates.append(date.strftime("%Y-%m-%d"))
        value = base_drift + increase_rate * i / num_days
        value += random.gauss(0, 0.02)
        if spike_day and i >= spike_day:
            value += 0.15
        value = max(0, min(1, value))
        values.append(round(value, 4))
    return dates, values


def _generate_prediction_cohorts(model):
    cohort_definitions = {
        "model-1": {"name": "Patient Age Group", "segments": ["18-30", "31-45", "46-60", "61-75", "75+"]},
        "model-2": {"name": "Drug Class", "segments": ["Antibiotics", "Opioids", "Anticoagulants", "Immunosuppressants", "Chemotherapy"]},
        "model-3": {"name": "Disease Stage", "segments": ["Pre-diabetic", "Early Stage", "Moderate", "Advanced", "Severe"]},
        "model-4": {"name": "Target Family", "segments": ["Kinases", "GPCRs", "Ion Channels", "Nuclear Receptors", "Proteases"]},
        "model-5": {"name": "Trial Phase", "segments": ["Phase I", "Phase II", "Phase IIb", "Phase III", "Phase IV"]},
        "model-6": {"name": "Imaging Modality", "segments": ["Chest X-ray", "CT Scan", "MRI", "Ultrasound", "PET Scan"]},
        "model-7": {"name": "Note Type", "segments": ["Discharge Summary", "Progress Note", "Radiology Report", "Pathology Report", "Operative Note"]},
        "model-8": {"name": "Payer Type", "segments": ["Medicare", "Medicaid", "Commercial", "Self-Pay", "Workers Comp"]},
    }
    cohort_def = cohort_definitions.get(model["id"], {"name": "Segment", "segments": ["A", "B", "C", "D", "E"]})
    base_perf = model["performance_score"]
    cohorts = []
    for segment in cohort_def["segments"]:
        variation = random.uniform(-0.12, 0.05)
        perf = max(0.5, min(1.0, base_perf + variation))
        cohorts.append({
            "name": segment,
            "accuracy": round(perf, 3),
            "precision": round(max(0.5, perf - random.uniform(0, 0.05)), 3),
            "recall": round(max(0.5, perf - random.uniform(0, 0.08)), 3),
            "sample_size": random.randint(200, 5000),
        })
    return {"category_name": cohort_def["name"], "segments": cohorts}


def _generate_feature_importance(model):
    features = model["features"]
    importances = sorted([random.uniform(0.02, 0.25) for _ in features], reverse=True)
    total = sum(importances)
    importances = [round(v / total, 4) for v in importances]
    return [{"feature": f, "importance": imp} for f, imp in zip(features, importances)]


def _generate_feature_drift(model):
    features = model["features"]
    base_drift = model["drift_score"]
    drifts = []
    for f in features:
        psi = max(0, base_drift + random.gauss(0, 0.08))
        drifts.append({
            "feature": f,
            "psi": round(psi, 4),
            "status": "Critical" if psi > 0.25 else "Warning" if psi > 0.1 else "Normal",
        })
    return sorted(drifts, key=lambda x: x["psi"], reverse=True)


def _generate_feature_accuracy_drop(model):
    features = model["features"]
    drops = []
    for f in features:
        drop = random.uniform(-0.02, 0.08) if model["status"] != "Healthy" else random.uniform(-0.01, 0.03)
        drops.append({
            "feature": f,
            "accuracy_drop": round(drop, 4),
            "cohort_affected": random.choice(["Low values", "High values", "Missing values", "Outliers", "Distribution shift"]),
        })
    return sorted(drops, key=lambda x: x["accuracy_drop"], reverse=True)


def _generate_data_quality(model):
    features = model["features"]
    base_quality = model["dqm_score"]
    feature_quality = []
    for f in features:
        missing_rate = max(0, random.gauss((1 - base_quality) * 0.5, 0.02))
        outlier_rate = max(0, random.gauss((1 - base_quality) * 0.3, 0.01))
        feature_quality.append({
            "feature": f,
            "missing_rate": round(missing_rate * 100, 2),
            "outlier_rate": round(outlier_rate * 100, 2),
            "distribution_shift": round(random.uniform(0, 0.15 if model["status"] == "Healthy" else 0.35), 3),
            "schema_valid": random.random() > 0.05,
        })
    return {
        "overall_score": model["dqm_score"],
        "total_records_today": model["predictions_today"] * random.randint(1, 3),
        "freshness_minutes": random.randint(1, 30),
        "schema_violations": random.randint(0, 5) if model["status"] != "Healthy" else 0,
        "features": feature_quality,
    }


def _generate_confusion_matrix(model):
    n = model["predictions_today"] // 10
    perf = model["performance_score"]
    tp = int(n * perf * 0.5)
    tn = int(n * perf * 0.5)
    fp = int(n * (1 - perf) * 0.6)
    fn = int(n * (1 - perf) * 0.4)
    return {"labels": ["Positive", "Negative"], "matrix": [[tp, fp], [fn, tn]]}


def _get_classification_metrics(model):
    perf = model["performance_score"]
    trend_configs = {
        "Healthy":  {"noise": 0.01, "trend": 0.01,  "anomaly": None},
        "Warning":  {"noise": 0.02, "trend": -0.03, "anomaly": None},
        "Degraded": {"noise": 0.02, "trend": -0.08, "anomaly": 60},
        "Critical": {"noise": 0.03, "trend": -0.15, "anomaly": 45},
    }
    cfg = trend_configs.get(model["status"], trend_configs["Healthy"])

    dates, accuracy  = _generate_time_series(perf, cfg["noise"], cfg["trend"], anomaly_start=cfg["anomaly"], anomaly_magnitude=0.1)
    _, precision     = _generate_time_series(perf - 0.02, cfg["noise"], cfg["trend"] * 0.8, anomaly_start=cfg["anomaly"], anomaly_magnitude=0.08)
    _, recall        = _generate_time_series(perf - 0.01, cfg["noise"] * 1.2, cfg["trend"] * 1.1, anomaly_start=cfg["anomaly"], anomaly_magnitude=0.12)
    _, f1            = _generate_time_series(perf - 0.015, cfg["noise"], cfg["trend"] * 0.9, anomaly_start=cfg["anomaly"], anomaly_magnitude=0.09)
    _, auc_roc       = _generate_time_series(perf + 0.02, cfg["noise"] * 0.8, cfg["trend"] * 0.7, anomaly_start=cfg["anomaly"], anomaly_magnitude=0.06)

    drift_dates, drift_values = _generate_drift_series(
        model["drift_score"] - 0.05 if model["status"] != "Healthy" else model["drift_score"],
        increase_rate=0.1 if model["status"] in ("Warning", "Degraded", "Critical") else 0,
        spike_day=50 if model["status"] == "Critical" else None,
    )

    return {
        "model": model,
        "metric_type": "classification",
        "dates": dates,
        "metrics": {
            "accuracy":  {"values": accuracy,  "current": accuracy[-1],  "label": "Accuracy"},
            "precision": {"values": precision, "current": precision[-1], "label": "Precision"},
            "recall":    {"values": recall,    "current": recall[-1],    "label": "Recall"},
            "f1_score":  {"values": f1,        "current": f1[-1],       "label": "F1 Score"},
            "auc_roc":   {"values": auc_roc,   "current": auc_roc[-1],  "label": "AUC-ROC"},
        },
        "drift": {"dates": drift_dates, "values": drift_values, "current": drift_values[-1]},
        "cohorts": _generate_prediction_cohorts(model),
        "feature_importance": _generate_feature_importance(model),
        "feature_drift": _generate_feature_drift(model),
        "feature_accuracy_drop": _generate_feature_accuracy_drop(model),
        "data_quality": _generate_data_quality(model),
        "confusion_matrix": _generate_confusion_matrix(model),
    }


def _get_regression_metrics(model):
    perf = model["performance_score"]
    trend_configs = {
        "Healthy":  {"noise": 0.01, "trend": 0.01,  "anomaly": None},
        "Warning":  {"noise": 0.02, "trend": -0.03, "anomaly": None},
        "Degraded": {"noise": 0.02, "trend": -0.08, "anomaly": 60},
        "Critical": {"noise": 0.03, "trend": -0.15, "anomaly": 45},
    }
    cfg = trend_configs.get(model["status"], trend_configs["Healthy"])

    dates, r2 = _generate_time_series(perf, cfg["noise"], cfg["trend"], anomaly_start=cfg["anomaly"], anomaly_magnitude=0.1)

    base_mae = (1 - perf) * 100
    _, mae_raw = _generate_time_series(0.5, cfg["noise"], -cfg["trend"])
    mae = [round(base_mae + (v - 0.5) * base_mae * 2, 2) for v in mae_raw]

    _, rmse_raw = _generate_time_series(0.5, cfg["noise"], -cfg["trend"])
    rmse = [round(base_mae * 1.3 + (v - 0.5) * base_mae * 2, 2) for v in rmse_raw]

    _, mape_raw = _generate_time_series(0.5, cfg["noise"], -cfg["trend"])
    mape = [round(5 + (1 - perf) * 20 + (v - 0.5) * 5, 2) for v in mape_raw]

    drift_dates, drift_values = _generate_drift_series(
        model["drift_score"] - 0.05 if model["status"] != "Healthy" else model["drift_score"],
        increase_rate=0.1 if model["status"] in ("Warning", "Degraded", "Critical") else 0,
    )

    return {
        "model": model,
        "metric_type": "regression",
        "dates": dates,
        "metrics": {
            "r2_score": {"values": r2,   "current": r2[-1],   "label": "R\u00b2 Score"},
            "mae":      {"values": mae,  "current": mae[-1],  "label": "MAE"},
            "rmse":     {"values": rmse, "current": rmse[-1], "label": "RMSE"},
            "mape":     {"values": mape, "current": mape[-1], "label": "MAPE (%)"},
        },
        "drift": {"dates": drift_dates, "values": drift_values, "current": drift_values[-1]},
        "cohorts": _generate_prediction_cohorts(model),
        "feature_importance": _generate_feature_importance(model),
        "feature_drift": _generate_feature_drift(model),
        "feature_accuracy_drop": _generate_feature_accuracy_drop(model),
        "data_quality": _generate_data_quality(model),
        "confusion_matrix": None,
    }


# ── Public API ──────────────────────────────────────────────────────────────

AGENTS = [
    {
        "id": "agent-1",
        "name": "Clinical Decision Support Agent",
        "entity_type": "agent",
        "project_id": "proj-2",
        "project_name": "Patient Safety",
        "owner": "Dr. James Wilson",
        "framework": "Semantic Kernel",
        "llm_backbone": "GPT-4o",
        "version": "v1.4.0",
        "status": "Operational",
        "status_color": "success",
        "task_completion_rate": 0.92,
        "groundedness_score": 0.88,
        "safety_score": 0.95,
        "avg_cost_per_interaction": 0.12,
        "last_updated": "2024-11-28",
        "endpoint": "/api/v1/agent/clinical-copilot",
        "sessions_today": 1240,
        "avg_latency_ms": 2800,
        "description": "Assists clinicians with real-time risk assessment and medication safety checks using patient EHR data.",
        "tool_models": ["model-1", "model-2"],
        "tools": ["Patient Readmission Risk", "Adverse Drug Event Detector", "EHR Lookup API", "Drug Interaction DB"],
        "hipaa": {
            "phi_handling": "Tokenized",
            "data_classification": "PHI",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-10-20",
            "deid_method": "Tokenization",
            "min_necessary": True,
            "retention_days": 365,
            "compliant": True,
        },
    },
    {
        "id": "agent-2",
        "name": "Prior Authorization Agent",
        "entity_type": "agent",
        "project_id": "proj-6",
        "project_name": "Revenue Cycle & Operations",
        "owner": "Alex Kumar",
        "framework": "LangGraph",
        "llm_backbone": "GPT-4o-mini",
        "version": "v2.1.0",
        "status": "Degraded",
        "status_color": "danger",
        "task_completion_rate": 0.74,
        "groundedness_score": 0.81,
        "safety_score": 0.97,
        "avg_cost_per_interaction": 0.08,
        "last_updated": "2024-11-26",
        "endpoint": "/api/v1/agent/prior-auth",
        "sessions_today": 560,
        "avg_latency_ms": 4200,
        "description": "Automates prior auth submissions with denial prediction pre-screening and payer-specific form generation.",
        "tool_models": ["model-8"],
        "tools": ["Claims Denial Predictor", "Payer Rules Engine", "CPT/ICD Validator", "Fax Gateway API"],
        "hipaa": {
            "phi_handling": "De-identified",
            "data_classification": "PHI",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-09-15",
            "deid_method": "Safe Harbor",
            "min_necessary": True,
            "retention_days": 2555,
            "compliant": True,
        },
    },
    {
        "id": "agent-3",
        "name": "Clinical Trial Matching Agent",
        "entity_type": "agent",
        "project_id": "proj-1",
        "project_name": "Clinical Trials",
        "owner": "Dr. Sarah Chen",
        "framework": "AutoGen",
        "llm_backbone": "GPT-4o",
        "version": "v1.0.2",
        "status": "Operational",
        "status_color": "success",
        "task_completion_rate": 0.89,
        "groundedness_score": 0.91,
        "safety_score": 0.93,
        "avg_cost_per_interaction": 0.18,
        "last_updated": "2024-11-27",
        "endpoint": "/api/v1/agent/trial-match",
        "sessions_today": 185,
        "avg_latency_ms": 5600,
        "description": "Matches eligible patients to active clinical trials using EHR data and inclusion/exclusion criteria parsing.",
        "tool_models": ["model-5"],
        "tools": ["Trial Dropout Predictor", "ClinicalTrials.gov API", "EHR Patient Summarizer", "Eligibility Criteria Parser"],
        "hipaa": {
            "phi_handling": "Pseudonymized",
            "data_classification": "PHI",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-11-01",
            "deid_method": "Expert Determination",
            "min_necessary": True,
            "retention_days": 730,
            "compliant": True,
        },
    },
    {
        "id": "agent-4",
        "name": "Radiology Triage Agent",
        "entity_type": "agent",
        "project_id": "proj-5",
        "project_name": "Medical Imaging",
        "owner": "Dr. Lisa Thompson",
        "framework": "Semantic Kernel",
        "llm_backbone": "GPT-4o",
        "version": "v1.2.1",
        "status": "Warning",
        "status_color": "warning",
        "task_completion_rate": 0.85,
        "groundedness_score": 0.78,
        "safety_score": 0.90,
        "avg_cost_per_interaction": 0.15,
        "last_updated": "2024-11-27",
        "endpoint": "/api/v1/agent/rad-triage",
        "sessions_today": 890,
        "avg_latency_ms": 3400,
        "description": "Prioritizes radiology worklist by AI-detected urgency and generates preliminary findings summaries.",
        "tool_models": ["model-6"],
        "tools": ["Radiology Anomaly Detector", "PACS Integration API", "Report Template Generator", "Urgency Classifier"],
        "hipaa": {
            "phi_handling": "De-identified",
            "data_classification": "Limited Dataset",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC + MFA",
            "audit_logging": True,
            "baa_signed": True,
            "last_risk_assessment": "2024-10-25",
            "deid_method": "DICOM De-identification",
            "min_necessary": True,
            "retention_days": 2555,
            "compliant": False,
        },
    },
]

# Tag all models with entity_type for unified handling
for _m in MODELS:
    _m.setdefault("entity_type", "model")


def get_agent(agent_id):
    return next((a for a in AGENTS if a["id"] == agent_id), None)


def get_agent_metrics(agent_id):
    """Generate agent-specific monitoring metrics."""
    agent = next((a for a in AGENTS if a["id"] == agent_id), None)
    if not agent:
        return None
    random.seed(hash(agent_id + "_metrics"))

    trend_configs = {
        "Operational": {"noise": 0.02, "trend": 0.01},
        "Warning":     {"noise": 0.03, "trend": -0.04},
        "Degraded":    {"noise": 0.03, "trend": -0.10},
    }
    cfg = trend_configs.get(agent["status"], trend_configs["Operational"])

    dates, completion = _generate_time_series(agent["task_completion_rate"], cfg["noise"], cfg["trend"])
    _, groundedness = _generate_time_series(agent["groundedness_score"], cfg["noise"] * 0.8, cfg["trend"] * 0.7)
    _, safety = _generate_time_series(agent["safety_score"], 0.01, cfg["trend"] * 0.3)

    # Token usage trends
    base_input_tokens = random.randint(800, 2000)
    base_output_tokens = random.randint(200, 600)
    token_dates = dates
    input_tokens = [max(100, int(base_input_tokens + random.gauss(0, 150))) for _ in dates]
    output_tokens = [max(50, int(base_output_tokens + random.gauss(0, 80))) for _ in dates]
    cost_per_day = [round((it * 0.000005 + ot * 0.000015) * agent["sessions_today"], 2) for it, ot in zip(input_tokens, output_tokens)]

    # Tool usage breakdown
    tool_usage = []
    for tool_name in agent["tools"]:
        calls = random.randint(50, 500)
        success_rate = round(random.uniform(0.85, 0.99), 3)
        avg_lat = random.randint(50, 800)
        tool_usage.append({
            "name": tool_name,
            "calls_today": calls,
            "success_rate": success_rate,
            "avg_latency_ms": avg_lat,
            "is_model": tool_name in [m["name"] for m in MODELS],
        })

    # Safety events
    safety_events = []
    event_types = ["PHI detected in response", "Hallucination flagged", "Content filter triggered",
                   "Unauthorized tool call blocked", "Guardrail override attempted", "PII leak prevented"]
    for i in range(random.randint(5, 20)):
        hours_ago = random.randint(0, 168 * 4)
        ts = datetime.now() - timedelta(hours=hours_ago)
        safety_events.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M"),
            "event_type": random.choice(event_types),
            "severity": random.choice(["low", "medium", "high"]),
            "resolved": random.random() > 0.2,
        })
    safety_events.sort(key=lambda e: e["timestamp"], reverse=True)

    # Task categories
    task_categories = {
        "agent-1": ["Risk Assessment", "Medication Review", "Alert Triage", "Discharge Planning", "Order Verification"],
        "agent-2": ["Prior Auth Submission", "Denial Appeal", "Coverage Check", "Document Gathering", "Status Follow-up"],
        "agent-3": ["Patient Screening", "Criteria Matching", "Site Recommendation", "Consent Coordination", "Eligibility Report"],
        "agent-4": ["Worklist Prioritization", "Findings Summary", "Comparison Study", "Follow-up Recommendation", "Quality Check"],
    }
    categories = task_categories.get(agent_id, ["Task A", "Task B", "Task C"])
    task_breakdown = []
    for cat in categories:
        rate = round(random.uniform(0.7, 0.98), 3)
        vol = random.randint(20, 300)
        task_breakdown.append({"category": cat, "completion_rate": rate, "volume": vol})

    return {
        "agent": agent,
        "dates": dates,
        "task_completion": {"values": completion, "current": completion[-1]},
        "groundedness": {"values": groundedness, "current": groundedness[-1]},
        "safety": {"values": safety, "current": safety[-1]},
        "tokens": {
            "dates": token_dates,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_per_day": cost_per_day,
            "total_cost_30d": round(sum(cost_per_day[-30:]), 2),
            "avg_cost_per_interaction": agent["avg_cost_per_interaction"],
        },
        "tool_usage": tool_usage,
        "safety_events": safety_events,
        "task_breakdown": task_breakdown,
        "linked_model_health": _get_linked_model_health(agent),
    }


def _get_linked_model_health(agent):
    """Get health status of models used by an agent."""
    linked = []
    for mid in agent.get("tool_models", []):
        m = get_model(mid)
        if m:
            linked.append({
                "id": m["id"], "name": m["name"],
                "status": m["status"], "performance_score": m["performance_score"],
                "drift_score": m["drift_score"],
            })
    return linked


def get_agent_lineage(agent_id):
    """Generate version history for an agent (prompt/tool changes)."""
    agent = next((a for a in AGENTS if a["id"] == agent_id), None)
    if not agent:
        return None
    random.seed(hash(agent_id + "_lineage"))

    triggers = [
        "Prompt optimization",
        "Added new tool integration",
        "LLM backbone upgrade",
        "Safety guardrail update",
        "Knowledge base refresh",
        "Removed deprecated tool",
        "Regulatory compliance update",
        "User feedback-driven revision",
    ]

    try:
        parts = agent["version"].lstrip("v").split(".")
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        major, minor, patch = 1, 0, 0

    versions = []
    today = datetime.now()
    for i in range(min(5, major * 3 + minor + 1)):
        if i == 0:
            ver = agent["version"]
            status = "Production"
            deploy_date = today - timedelta(days=random.randint(5, 30))
        else:
            ver = f"v{major}.{max(0, minor - i)}.{random.randint(0, patch)}"
            status = "Retired"
            deploy_date = today - timedelta(days=30 * i + random.randint(5, 25))

        comp = agent["task_completion_rate"] - (i * random.uniform(0.01, 0.04))
        comp = max(0.6, round(comp, 3))

        versions.append({
            "version": ver,
            "status": status,
            "deployed_date": deploy_date.strftime("%Y-%m-%d"),
            "retired_date": (deploy_date + timedelta(days=random.randint(20, 60))).strftime("%Y-%m-%d") if status == "Retired" else None,
            "trigger": triggers[i % len(triggers)],
            "performance_at_deploy": comp,
            "performance_at_retire": round(comp - random.uniform(0.02, 0.08), 3) if status == "Retired" else None,
            "training_records": None,
            "training_duration_min": None,
            "champion_challenger": "Champion" if i == 0 else "Retired",
            "notes": random.choice([
                "Improved groundedness with RAG context window expansion",
                "Added medication interaction tool",
                "Switched from GPT-4 to GPT-4o for cost reduction",
                "Updated system prompt for regulatory compliance",
                "Integrated new EHR data source",
                "Reduced hallucination rate by 15% with prompt tuning",
                "Added safety guardrail for PHI in responses",
                "Removed deprecated FHIR v3 tool",
            ]),
        })

    return {
        "model": agent,
        "current_version": agent["version"],
        "total_versions": len(versions),
        "versions": versions,
        "total_retrains": len(versions) - 1,
        "avg_version_lifespan_days": random.randint(15, 60),
    }


def get_all_entities():
    """Return combined list of models and agents."""
    return MODELS + AGENTS


def get_entity(entity_id):
    """Look up any entity by ID (model or agent)."""
    return get_model(entity_id) or get_agent(entity_id)


def get_summary_stats_combined():
    """Stats for combined cockpit view."""
    models = MODELS
    agents = AGENTS
    return {
        "total_models": len(models),
        "healthy_models": len([m for m in models if m["status"] == "Healthy"]),
        "warning_models": len([m for m in models if m["status"] == "Warning"]),
        "critical_models": len([m for m in models if m["status"] in ("Critical", "Degraded")]),
        "total_agents": len(agents),
        "operational_agents": len([a for a in agents if a["status"] == "Operational"]),
        "warning_agents": len([a for a in agents if a["status"] == "Warning"]),
        "degraded_agents": len([a for a in agents if a["status"] in ("Degraded",)]),
    }

def get_model_metrics(model_id):
    model = next((m for m in MODELS if m["id"] == model_id), None)
    if not model:
        return None
    random.seed(hash(model_id))
    if model["model_type"] == "classification":
        return _get_classification_metrics(model)
    return _get_regression_metrics(model)


def get_model(model_id):
    return next((m for m in MODELS if m["id"] == model_id), None)


def get_projects():
    projects = []
    for p in PROJECTS:
        p_copy = dict(p)
        p_copy["model_count"] = len([m for m in MODELS if m["project_id"] == p["id"]])
        p_copy["models"] = [m for m in MODELS if m["project_id"] == p["id"]]
        p_copy["agent_count"] = len([a for a in AGENTS if a["project_id"] == p["id"]])
        p_copy["agents"] = [a for a in AGENTS if a["project_id"] == p["id"]]
        projects.append(p_copy)
    return projects


def get_summary_stats():
    total = len(MODELS)
    healthy = len([m for m in MODELS if m["status"] == "Healthy"])
    warning = len([m for m in MODELS if m["status"] == "Warning"])
    critical = len([m for m in MODELS if m["status"] in ("Critical", "Degraded")])
    return {"total": total, "healthy": healthy, "warning": warning, "critical": critical}


def get_fairness_metrics(model_id):
    """Generate fairness/equity metrics across demographic groups."""
    model = next((m for m in MODELS if m["id"] == model_id), None)
    if not model:
        return None
    random.seed(hash(model_id + "_fairness"))
    base_perf = model["performance_score"]

    demographics = {
        "age_group": {
            "label": "Age Group",
            "groups": [
                {"name": "18-30", "size": random.randint(800, 3000)},
                {"name": "31-45", "size": random.randint(2000, 5000)},
                {"name": "46-60", "size": random.randint(2500, 6000)},
                {"name": "61-75", "size": random.randint(1500, 4000)},
                {"name": "75+", "size": random.randint(500, 2000)},
            ],
        },
        "sex": {
            "label": "Sex",
            "groups": [
                {"name": "Female", "size": random.randint(4000, 8000)},
                {"name": "Male", "size": random.randint(4000, 8000)},
                {"name": "Other/Unknown", "size": random.randint(100, 500)},
            ],
        },
        "race_ethnicity": {
            "label": "Race/Ethnicity",
            "groups": [
                {"name": "White", "size": random.randint(3000, 7000)},
                {"name": "Black", "size": random.randint(1500, 4000)},
                {"name": "Hispanic", "size": random.randint(1500, 4000)},
                {"name": "Asian", "size": random.randint(800, 2500)},
                {"name": "Other/Multi", "size": random.randint(400, 1200)},
            ],
        },
        "insurance": {
            "label": "Insurance Type",
            "groups": [
                {"name": "Medicare", "size": random.randint(2000, 5000)},
                {"name": "Medicaid", "size": random.randint(1500, 4000)},
                {"name": "Commercial", "size": random.randint(3000, 7000)},
                {"name": "Self-Pay", "size": random.randint(300, 1200)},
            ],
        },
    }

    for dim_key, dim in demographics.items():
        for group in dim["groups"]:
            variation = random.uniform(-0.10, 0.04)
            perf = max(0.55, min(1.0, base_perf + variation))
            group["accuracy"] = round(perf, 3)
            group["precision"] = round(max(0.55, perf - random.uniform(0, 0.04)), 3)
            group["recall"] = round(max(0.55, perf - random.uniform(0, 0.07)), 3)
            group["fpr"] = round(random.uniform(0.02, 0.15), 3)
            group["fnr"] = round(1 - group["recall"], 3)
            # Disparate impact ratio relative to best-performing group
            group["selection_rate"] = round(random.uniform(0.3, 0.7), 3)

    # Compute disparate impact for each dimension
    for dim_key, dim in demographics.items():
        rates = [g["selection_rate"] for g in dim["groups"]]
        max_rate = max(rates) if rates else 1
        for group in dim["groups"]:
            group["disparate_impact"] = round(group["selection_rate"] / max_rate, 3) if max_rate > 0 else 1.0

    # Overall fairness score (average of disparate impact ratios)
    all_di = []
    for dim in demographics.values():
        all_di.extend(g["disparate_impact"] for g in dim["groups"])
    overall = round(sum(all_di) / len(all_di), 3) if all_di else 1.0

    return {"demographics": demographics, "overall_fairness": overall}


def get_model_lineage(model_id):
    """Generate version history and retrain timeline for a model."""
    model = next((m for m in MODELS if m["id"] == model_id), None)
    if not model:
        return None
    random.seed(hash(model_id + "_lineage"))

    current_ver = model["version"]
    # Parse version to generate history
    try:
        parts = current_ver.lstrip("v").split(".")
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        major, minor, patch = 1, 0, 0

    triggers = [
        "Scheduled retrain (quarterly)",
        "Performance degradation detected",
        "Drift threshold exceeded",
        "New training data available",
        "Feature engineering update",
        "Hyperparameter optimization",
        "Bug fix in preprocessing",
        "Regulatory compliance update",
        "Data pipeline change",
        "Manual retrain request",
    ]

    statuses = ["Production", "Retired", "Retired", "Retired", "Retired"]

    versions = []
    today = datetime.now()
    for i in range(min(5, major * 3 + minor + 1)):
        if i == 0:
            ver = current_ver
            status = "Production"
            deploy_date = today - timedelta(days=random.randint(5, 30))
        else:
            p = max(0, patch - i)
            m_ = minor if p >= 0 else max(0, minor - 1)
            ver = f"v{major}.{m_}.{max(0, patch - i)}"
            status = statuses[min(i, len(statuses) - 1)]
            deploy_date = today - timedelta(days=30 * i + random.randint(5, 25))

        perf = model["performance_score"] - (i * random.uniform(0.01, 0.04))
        perf = max(0.6, round(perf, 3))

        versions.append({
            "version": ver,
            "status": status,
            "deployed_date": deploy_date.strftime("%Y-%m-%d"),
            "retired_date": (deploy_date + timedelta(days=random.randint(20, 60))).strftime("%Y-%m-%d") if status == "Retired" else None,
            "trigger": triggers[i % len(triggers)],
            "performance_at_deploy": perf,
            "performance_at_retire": round(perf - random.uniform(0.02, 0.08), 3) if status == "Retired" else None,
            "training_records": random.randint(10000, 500000),
            "training_duration_min": random.randint(15, 480),
            "champion_challenger": "Champion" if i == 0 else "Retired",
            "notes": random.choice([
                "Improved recall on minority cohorts",
                "Added new lab result features",
                "Retrained on updated ICD-10 codes",
                "Addressed class imbalance with SMOTE",
                "Switched to cross-validated hyperparameters",
                "Updated preprocessing for missing values",
                "Added temporal features for seasonality",
                "Regulatory-driven retrain after audit",
            ]),
        })

    return {
        "model": model,
        "current_version": current_ver,
        "total_versions": len(versions),
        "versions": versions,
        "total_retrains": len(versions) - 1,
        "avg_version_lifespan_days": random.randint(25, 90),
    }


def get_alerts():
    """Generate realistic alert history for models and agents."""
    random.seed(99)
    model_alert_types = [
        {"type": "drift", "icon": "exchange-alt", "severity": "warning",
         "template": "Drift threshold exceeded (PSI={psi:.3f}) for {model}"},
        {"type": "drift", "icon": "exchange-alt", "severity": "critical",
         "template": "Critical drift detected (PSI={psi:.3f}) on {model}"},
        {"type": "performance", "icon": "chart-line", "severity": "warning",
         "template": "Performance degradation detected on {model}: {metric} dropped to {value:.3f}"},
        {"type": "performance", "icon": "chart-line", "severity": "critical",
         "template": "Critical performance drop on {model}: {metric} at {value:.3f}"},
        {"type": "data_quality", "icon": "database", "severity": "warning",
         "template": "Data quality issue on {model}: {feature} missing rate at {rate:.1f}%"},
        {"type": "data_quality", "icon": "database", "severity": "info",
         "template": "Schema validation passed for {model} after fix"},
        {"type": "latency", "icon": "bolt", "severity": "warning",
         "template": "High latency detected on {model}: {latency}ms (threshold: {threshold}ms)"},
        {"type": "volume", "icon": "chart-bar", "severity": "info",
         "template": "Prediction volume spike on {model}: {volume:,} requests (3x normal)"},
        {"type": "retrain", "icon": "sync-alt", "severity": "info",
         "template": "Automated retrain triggered for {model} due to drift"},
        {"type": "threshold", "icon": "exclamation-triangle", "severity": "critical",
         "template": "Model {model} dropped below minimum performance threshold"},
    ]
    agent_alert_types = [
        {"type": "safety", "icon": "shield-alt", "severity": "critical",
         "template": "Safety guardrail triggered on {model}: PHI detected in agent response"},
        {"type": "safety", "icon": "shield-alt", "severity": "warning",
         "template": "Content filter activated on {model}: potentially harmful output blocked"},
        {"type": "groundedness", "icon": "bullseye", "severity": "warning",
         "template": "Groundedness score dropped to {value:.2f} on {model}"},
        {"type": "cost", "icon": "dollar-sign", "severity": "warning",
         "template": "Cost spike on {model}: ${cost:.2f}/hr (threshold: $20/hr)"},
        {"type": "completion", "icon": "tasks", "severity": "warning",
         "template": "Task completion rate dropped to {value:.0%} on {model}"},
        {"type": "tool_failure", "icon": "wrench", "severity": "critical",
         "template": "{model}: {tool} returning errors ({rate:.0%} failure rate)"},
    ]
    alerts = []
    today = datetime.now()
    # Model alerts
    for i in range(50):
        alert_def = random.choice(model_alert_types)
        model = random.choice(MODELS)
        hours_ago = random.randint(0, 168)
        timestamp = today - timedelta(hours=hours_ago)
        message = alert_def["template"].format(
            model=model["name"], psi=random.uniform(0.1, 0.5),
            metric=random.choice(["accuracy", "precision", "recall", "F1"]),
            value=random.uniform(0.6, 0.88),
            feature=random.choice(model["features"]),
            rate=random.uniform(2, 15),
            latency=random.randint(100, 500),
            threshold=random.randint(50, 100),
            volume=random.randint(50000, 500000),
        )
        alerts.append({
            "id": f"alert-{i+1}",
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M"),
            "timestamp_relative": f"{hours_ago}h ago" if hours_ago < 24 else f"{hours_ago // 24}d ago",
            "model_id": model["id"],
            "model_name": model["name"],
            "entity_type": "model",
            "project_name": model["project_name"],
            "type": alert_def["type"],
            "icon": alert_def["icon"],
            "severity": alert_def["severity"],
            "message": message,
            "acknowledged": random.random() > 0.4,
        })
    # Agent alerts
    for i in range(20):
        alert_def = random.choice(agent_alert_types)
        agent = random.choice(AGENTS)
        hours_ago = random.randint(0, 168)
        timestamp = today - timedelta(hours=hours_ago)
        message = alert_def["template"].format(
            model=agent["name"], value=random.uniform(0.6, 0.85),
            cost=random.uniform(15, 50),
            tool=random.choice(agent["tools"]),
            rate=random.uniform(0.05, 0.25),
        )
        alerts.append({
            "id": f"alert-agent-{i+1}",
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M"),
            "timestamp_relative": f"{hours_ago}h ago" if hours_ago < 24 else f"{hours_ago // 24}d ago",
            "model_id": agent["id"],
            "model_name": agent["name"],
            "entity_type": "agent",
            "project_name": agent["project_name"],
            "type": alert_def["type"],
            "icon": alert_def["icon"],
            "severity": alert_def["severity"],
            "message": message,
            "acknowledged": random.random() > 0.4,
        })
    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    return alerts
