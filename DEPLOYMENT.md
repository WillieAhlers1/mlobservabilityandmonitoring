---
title: "Azure Deployment Guide"
description: "Deployment process and details for Tredence ML Works on Azure App Service"
author: "Willie Ahlers"
ms.date: 2026-07-31
ms.topic: how-to
---

## Deployment Overview

Tredence ML Works is deployed to Azure App Service (Linux) as a Python Flask application. The app runs on the Free (F1) tier in Central US and is publicly accessible without authentication.

## Live URL

**https://tredence-mlworks.azurewebsites.net**

## Azure Resources

| Resource | Name | Details |
|----------|------|---------|
| Subscription | Azure subscription 1 | `4758145a-611a-4660-bca4-cf297fbf7e78` |
| Resource Group | `mlworks-rg` | East US 2 |
| App Service Plan | `mlworks-plan` | Free F1, Linux, Central US |
| Web App | `tredence-mlworks` | Python 3.11, Central US |

## Deployment Steps

### Prerequisites

- Azure CLI installed and logged in
- Access to the target Azure subscription
- Application source code in `c:\Sandbox\ML Monitoring`

### Step 1 - Authenticate and set subscription

```bash
az login
az account set --subscription "4758145a-611a-4660-bca4-cf297fbf7e78"
```

### Step 2 - Create resource group

```bash
az group create --name mlworks-rg --location eastus2
```

### Step 3 - Create App Service plan

```bash
az appservice plan create \
  --name mlworks-plan \
  --resource-group mlworks-rg \
  --sku F1 \
  --is-linux \
  --location centralus
```

The Free (F1) tier was used because East US 2 and East US had zero vCPU quota. Central US had available capacity. Upgrade to B1 or P0v3 for production workloads.

### Step 4 - Create the web app

```bash
az webapp create \
  --name tredence-mlworks \
  --resource-group mlworks-rg \
  --plan mlworks-plan \
  --runtime "PYTHON:3.11"
```

### Step 5 - Configure build settings

```bash
az webapp config appsettings set \
  --name tredence-mlworks \
  --resource-group mlworks-rg \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

This ensures `pip install -r requirements.txt` runs automatically during deployment.

### Step 6 - Package and deploy

```bash
# Create zip archive of the app
Compress-Archive -Path app.py, data_source.py, config_loader.py, mock_data.py, requirements.txt, config, static, templates, industries \
  -DestinationPath deploy.zip -Force

# Deploy to Azure
az webapp deploy \
  --name tredence-mlworks \
  --resource-group mlworks-rg \
  --src-path deploy.zip \
  --type zip \
  --track-status false
```

## Redeployment

To redeploy after code changes, repeat Step 6:

```bash
cd "c:\Sandbox\ML Monitoring"
Compress-Archive -Path app.py, data_source.py, config_loader.py, mock_data.py, requirements.txt, config, static, templates, industries -DestinationPath deploy.zip -Force
az webapp deploy --name tredence-mlworks --resource-group mlworks-rg --src-path deploy.zip --type zip --track-status false
Remove-Item deploy.zip
```

## Configuration

The application reads settings from `config/app.yaml`. On Azure, override via App Settings:

```bash
az webapp config appsettings set \
  --name tredence-mlworks \
  --resource-group mlworks-rg \
  --settings ML_WORKS_DATA_SOURCE=mock ML_WORKS_DB_PATH=/home/site/wwwroot/ml_monitor.db
```

## Configuration Notes

- **WSGI Server**: Azure App Service uses gunicorn automatically for Flask apps (added to `requirements.txt`)
- **Startup Command**: None required — Oryx auto-detects Flask via `app.py`
- **Database**: SQLite is ephemeral on App Service (resets on restart). This is acceptable for the prototype since all data is mock/generated
- **Industry Switcher**: Works as expected — state is in-memory per worker process

## Tier Limitations (Free F1)

- 60 CPU-minutes per day
- 1 GB memory
- No custom domain / SSL
- No deployment slots
- Shared infrastructure (cold starts possible)

## Teardown

To remove all Azure resources and stop billing:

```bash
az group delete --name mlworks-rg --yes --no-wait
```

## Troubleshooting

- **App shows default page after deploy**: Wait 2-3 minutes for warm-up
- **Application Error page**: Check logs with `az webapp log tail --name tredence-mlworks --resource-group mlworks-rg`
- **Quota exceeded on plan creation**: Try a different region or use the Free (F1) SKU
- **Import errors**: Verify all directories (industries/, static/, templates/) are included in the zip
