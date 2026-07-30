---
title: "Tredence ML Works"
description: "ML model observability and monitoring prototype for Health & Life Sciences"
author: "Tredence"
ms.date: 2026-07-30
ms.topic: overview
---

## Overview

Tredence ML Works is a prototype web application that demonstrates monitoring and observability for ML models deployed in production. Built for Health & Life Sciences use cases, it provides a comprehensive view of model health, performance, drift, data quality, HIPAA compliance, fairness, and version lineage.

### Key Features

| Feature | Description |
|---------|-------------|
| **Cockpit** | At-a-glance view of all production models with status, HIPAA compliance, drift, performance, and data quality scores |
| **Model Dashboard** | Deep-dive into individual models across 7 tabs: Performance, Drift, Interpretability, Data Quality, Compliance, and Equity |
| **Alerts** | Filterable alert history with severity and type-based filtering across drift, performance, data quality, and latency events |
| **Compare** | Side-by-side model comparison with overlaid performance and drift trend charts |
| **Projects** | Project management with model grouping and persistent project creation |
| **Onboard** | 4-step model registration wizard with monitoring configuration and alert setup |
| **Lineage** | Version history timeline with retrain triggers, performance deltas, and champion/retired tracking |

### Health & Life Sciences Models

The prototype includes 8 realistic HLS models across 6 projects:

- **Patient Readmission Risk** (Population Health) — XGBoost classification
- **Adverse Drug Event Detector** (Patient Safety) — LightGBM classification
- **Disease Progression Forecaster** (Population Health) — Prophet + LSTM regression
- **Molecular Activity Predictor** (Drug Discovery) — Graph Neural Network
- **Clinical Trial Dropout Predictor** (Clinical Trials) — Gradient Boosting
- **Radiology Anomaly Detector** (Medical Imaging) — EfficientNet-B7
- **Clinical Notes NLP Classifier** (Patient Safety) — BioBERT
- **Claims Denial Predictor** (Revenue Cycle) — CatBoost

### Dashboard Tabs

- **Performance** — Accuracy, precision, recall, F1, AUC-ROC trends over 90 days; prediction cohort analysis; feature accuracy drop; confusion matrix
- **Drift** — PSI trend with warning/critical thresholds; feature-level drift breakdown
- **Interpretability** — Global feature importance (SHAP); top feature insights
- **Data Quality** — Missing rates, outlier rates, distribution shift, schema validation per feature
- **Compliance** — HIPAA technical and administrative safeguards; feature PHI sensitivity map; de-identification method tracking
- **Equity** — Fairness metrics across age, sex, race/ethnicity, and insurance type; disparate impact ratio with 4/5 rule indicators

## Quickstart

### Prerequisites

- Python 3.9 or later
- pip

### Install dependencies

```bash
pip install -r requirements.txt
```

The only dependency is Flask.

### Run the application

```bash
python app.py
```

The application starts on [http://127.0.0.1:5000](http://127.0.0.1:5000).

### Navigate the prototype

1. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser
2. The **Cockpit** page shows all 8 models with health indicators
3. Click any model name or the **Dashboard** button to see detailed metrics
4. Use the sidebar to navigate between Projects, Cockpit, Alerts, Compare, and Onboard
5. Click the **Lineage** button on any model dashboard to view version history

### Project structure

```text
ML Monitoring/
├── app.py                  # Flask routes and SQLite setup
├── mock_data.py            # HLS models, projects, metrics, alerts, fairness, lineage
├── requirements.txt        # Python dependencies
├── static/
│   ├── css/style.css       # Tredence-themed stylesheet
│   └── js/
│       ├── dashboard.js    # Chart.js for model dashboard tabs
│       └── compare.js      # Chart.js for model comparison
├── templates/
│   ├── base.html           # Sidebar layout with Tredence branding
│   ├── cockpit.html        # Production model overview table
│   ├── dashboard.html      # 7-tab model deep-dive
│   ├── alerts.html         # Alert history with filters
│   ├── compare.html        # Side-by-side model comparison
│   ├── projects.html       # Project cards with create modal
│   ├── onboard.html        # Model onboarding wizard
│   └── lineage.html        # Version timeline and comparison
└── styling/
    └── tredence-theme.css  # Brand token reference
```

## Technology

- **Backend**: Python / Flask
- **Frontend**: Bootstrap 5, Chart.js, Font Awesome
- **Database**: SQLite (for persisted projects and onboarded models)
- **Theme**: Tredence brand (Poppins font, orange/teal/green palette)
- **Data**: Deterministic mock data with realistic 90-day time series
