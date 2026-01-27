# Production Deployment Guide

## Overview

This guide covers deploying the LLM Trading Agent to Google Cloud Platform production environment (`samaanai-prod-1009-124126`).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Google Cloud Platform                          │
│                      (samaanai-prod-1009-124126)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐   │
│  │   Frontend   │────▶│   Backend    │────▶│   Cloud SQL          │   │
│  │  Cloud Run   │     │  Cloud Run   │     │   (PostgreSQL)       │   │
│  │  (React)     │     │  (Django)    │     │                      │   │
│  │  256Mi/1CPU  │     │  1Gi/2CPU    │     │  db-custom-1-3840    │   │
│  │  0-3 inst    │     │  1-5 inst    │     │                      │   │
│  └──────────────┘     └──────┬───────┘     └──────────────────────┘   │
│                              │                                         │
│                              │ VPC Connector                           │
│                              │ (10.8.0.0/28)                           │
│                              ▼                                         │
│                       ┌──────────────┐                                 │
│                       │  IBKR Gateway │                                │
│                       │  (GCE VM)     │                                │
│                       │  e2-small     │                                │
│                       │  10.138.0.X   │                                │
│                       └──────────────┘                                 │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                     Secret Manager                              │   │
│  │  • DJANGO_SECRET_KEY    • DB_PASSWORD      • GEMINI_API_KEY    │   │
│  │  • GOOGLE_CLIENT_ID     • GOOGLE_SECRET    • SENDGRID_API_KEY  │   │
│  │  • SLACK_WEBHOOK_URL    • NEWS_API_KEY                         │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                     Cloud Scheduler                             │   │
│  │  • trading-agent-trigger: */30 9-16 * * 1-5 → /api/analyze     │   │
│  │  • trading-daily-summary: 0 16 * * 1-5 → /api/daily-summary    │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. Google Cloud SDK installed and authenticated
2. Access to production GCP project (`samaanai-prod-1009-124126`)
3. GitHub repository access for CI/CD
4. Interactive Brokers account (paper or live)

## Step 1: Set Up Secret Manager

All sensitive configuration is stored in Secret Manager, not in environment variables.

```bash
# Set project
export PROJECT_ID=samaanai-prod-1009-124126
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable secretmanager.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable compute.googleapis.com
gcloud services enable vpcaccess.googleapis.com
gcloud services enable cloudscheduler.googleapis.com

# Create secrets (replace with actual values)
echo -n "$(openssl rand -base64 50)" | gcloud secrets create django-secret-key --data-file=-
echo -n "your-db-password" | gcloud secrets create db-password --data-file=-
echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-
echo -n "your-google-client-id" | gcloud secrets create google-client-id --data-file=-
echo -n "your-google-client-secret" | gcloud secrets create google-client-secret --data-file=-
echo -n "your-sendgrid-api-key" | gcloud secrets create sendgrid-api-key --data-file=-
echo -n "your-slack-webhook-url" | gcloud secrets create slack-webhook-url --data-file=-
echo -n "your-news-api-key" | gcloud secrets create news-api-key --data-file=-
```

## Step 2: Create Cloud SQL Instance

```bash
# Create PostgreSQL instance (production tier)
gcloud sql instances create samaanai-backend-db \
  --database-version=POSTGRES_14 \
  --tier=db-custom-1-3840 \
  --region=us-west1 \
  --storage-type=SSD \
  --storage-size=20GB \
  --storage-auto-increase \
  --backup-start-time=04:00 \
  --availability-type=zonal \
  --maintenance-window-day=SUN \
  --maintenance-window-hour=03

# Create database
gcloud sql databases create stock_trading --instance=samaanai-backend-db

# Create user (get password from Secret Manager)
DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)
gcloud sql users create samaanai_backend \
  --instance=samaanai-backend-db \
  --password="$DB_PASSWORD"
```

## Step 3: Set Up VPC Connector

```bash
# Create VPC connector for IBKR Gateway access
gcloud compute networks vpc-access connectors create ibkr-connector \
  --region=us-west1 \
  --network=default \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=3
```

## Step 4: Set Up IBKR Gateway VM

```bash
# Create VM for IBKR Gateway
gcloud compute instances create ibkr-gateway-prod \
  --zone=us-west1-b \
  --machine-type=e2-small \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --image-family=cos-stable \
  --image-project=cos-cloud \
  --tags=ibkr-gateway \
  --metadata-from-file=startup-script=scripts/ibkr-startup.sh

# Create firewall rule for IBKR
gcloud compute firewall-rules create allow-ibkr-gateway \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:4001,tcp:4002,tcp:4004 \
  --source-ranges=10.8.0.0/28 \
  --target-tags=ibkr-gateway

# Get VM internal IP (save this for Cloud Run config)
gcloud compute instances describe ibkr-gateway-prod \
  --zone=us-west1-b \
  --format='get(networkInterfaces[0].networkIP)'
```

## Step 5: Grant Service Account Permissions

```bash
# Get Cloud Run service account
export SA_EMAIL=$(gcloud iam service-accounts list \
  --filter="displayName:Compute Engine default service account" \
  --format="value(email)")

# Grant Secret Manager access
gcloud secrets add-iam-policy-binding django-secret-key \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding db-password \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding google-client-id \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding google-client-secret \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding sendgrid-api-key \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding slack-webhook-url \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding news-api-key \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"

# Grant Cloud SQL access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/cloudsql.client"
```

## Step 6: Configure GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

| Secret Name | Description |
|-------------|-------------|
| `GCP_SA_KEY_PROD` | Service account JSON key for deployments |

**Note:** Application secrets are now stored in GCP Secret Manager, not GitHub Secrets.

## Step 7: Deploy via GitHub Actions

Push to `main` branch to trigger production deployment:

```bash
git checkout main
git merge staging
git push origin main
```

## Step 8: Set Up Cloud Scheduler

```bash
# Get backend URL
BACKEND_URL=$(gcloud run services describe trading-api \
  --region=us-west1 --format='value(status.url)')

# Trading analysis (every 30 min during market hours)
gcloud scheduler jobs create http trading-agent-trigger-prod \
  --location=us-central1 \
  --schedule="*/30 9-16 * * 1-5" \
  --time-zone="America/New_York" \
  --uri="${BACKEND_URL}/api/analyze" \
  --http-method=POST \
  --attempt-deadline=180s \
  --description="Trigger trading analysis every 30 minutes during market hours"

# Daily summary email (at market close)
gcloud scheduler jobs create http trading-daily-summary-prod \
  --location=us-central1 \
  --schedule="0 16 * * 1-5" \
  --time-zone="America/New_York" \
  --uri="${BACKEND_URL}/api/daily-summary" \
  --http-method=POST \
  --attempt-deadline=60s \
  --description="Send daily trading summary at market close"
```

## Step 9: Post-Deployment Verification

```bash
# Check service health
curl ${BACKEND_URL}/health

# Check broker connection
curl -H "Authorization: Bearer $TOKEN" ${BACKEND_URL}/api/broker-status

# Verify Cloud Scheduler jobs
gcloud scheduler jobs list --location=us-central1
```

## Step 10: Set Up Monitoring & Alerts

```bash
# Create uptime check
gcloud monitoring uptime-check-configs create trading-api-health \
  --display-name="Trading API Health" \
  --monitored-resource-type="uptime_url" \
  --uri="${BACKEND_URL}/health" \
  --check-interval=300s

# Create alert policy for errors
gcloud alpha monitoring policies create \
  --display-name="Trading API Error Rate" \
  --condition-filter='metric.type="run.googleapis.com/request_count" resource.type="cloud_run_revision" metric.label.response_code_class!="2xx"' \
  --condition-threshold-value=10 \
  --condition-threshold-comparison="COMPARISON_GT" \
  --notification-channels="projects/${PROJECT_ID}/notificationChannels/YOUR_CHANNEL_ID"
```

## Environment Configuration

### Production vs Staging Differences

| Setting | Staging | Production |
|---------|---------|------------|
| Min instances | 0 | 1 |
| Max instances | 2 | 5 |
| Memory | 512Mi | 1Gi |
| CPU | 1 | 2 |
| Cloud SQL tier | db-f1-micro | db-custom-1-3840 |
| IBKR mode | Paper | Paper/Live |

### Required Environment Variables (from Secret Manager)

| Variable | Secret Name | Description |
|----------|-------------|-------------|
| `DJANGO_SECRET_KEY` | django-secret-key | Django secret key |
| `DB_PASSWORD` | db-password | Cloud SQL password |
| `GEMINI_API_KEY` | gemini-api-key | Google Gemini API |
| `GOOGLE_CLIENT_ID` | google-client-id | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | google-client-secret | OAuth client secret |
| `SENDGRID_API_KEY` | sendgrid-api-key | Email notifications |
| `SLACK_WEBHOOK_URL` | slack-webhook-url | Slack notifications |
| `NEWS_API_KEY` | news-api-key | Market news API |

### Non-Secret Environment Variables

Set directly in Cloud Run deployment:

```
DJANGO_SETTINGS_MODULE=backend.settings.production
BROKER_TYPE=ibkr
IBKR_GATEWAY_HOST=10.138.0.X  # VM internal IP
IBKR_GATEWAY_PORT=4004
DB_USER=samaanai_backend
DB_NAME=stock_trading
INSTANCE_CONNECTION_NAME=samaanai-prod-1009-124126:us-west1:samaanai-backend-db
ALLOWED_HOSTS=trading.samaanai.com,trading-api-XXX.us-west1.run.app
FRONTEND_URL=https://trading-dashboard-XXX.us-west1.run.app
AUTHORIZED_EMAILS=your@email.com
```

## Cost Estimation

| Resource | Monthly Cost |
|----------|--------------|
| Cloud Run (backend, 1-5 instances) | $10-30 |
| Cloud Run (frontend, 0-3 instances) | $0-10 |
| Cloud SQL (db-custom-1-3840) | $35-50 |
| GCE VM (e2-small spot) | $6-8 |
| VPC Connector | $7-10 |
| Cloud Scheduler | <$1 |
| Secret Manager | <$1 |
| **Total** | **$60-100/month** |

## Troubleshooting

### Common Issues

1. **Secret Manager access denied**
   ```bash
   gcloud secrets add-iam-policy-binding SECRET_NAME \
     --member="serviceAccount:SA_EMAIL" \
     --role="roles/secretmanager.secretAccessor"
   ```

2. **IBKR Gateway connection failed**
   - Check VM is running: `gcloud compute instances list`
   - Check firewall rules: `gcloud compute firewall-rules list`
   - Check VPC connector: `gcloud compute networks vpc-access connectors list`

3. **Cloud SQL connection failed**
   - Verify Cloud SQL Admin API is enabled
   - Check instance connection name matches
   - Verify service account has `cloudsql.client` role

4. **OAuth redirect issues**
   - Verify `FRONTEND_URL` is set correctly
   - Check Google Console authorized redirect URIs

## Security Checklist

- [ ] All secrets stored in Secret Manager (not env vars or code)
- [ ] Cloud Run uses IAM for Secret Manager access
- [ ] HTTPS enforced (`SECURE_SSL_REDIRECT=True`)
- [ ] CORS configured for production domains only
- [ ] VPC connector isolates IBKR traffic
- [ ] Cloud SQL not publicly accessible
- [ ] Minimum required IAM permissions
- [ ] Audit logging enabled
- [ ] Regular secret rotation policy
