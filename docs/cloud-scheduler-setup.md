# Cloud Scheduler Setup for Market Hours Trading

## Overview
This guide sets up Cloud Scheduler to run the trading agent only during market hours.

## Market Hours (Eastern Time)
- **Open**: 9:30 AM ET (14:30 UTC)
- **Close**: 4:00 PM ET (21:00 UTC)
- **Days**: Monday - Friday (excluding holidays)

## Cloud Scheduler Configuration

### Option 1: Cloud Scheduler + Cloud Run Jobs (Recommended)

Create a Cloud Run Job that runs on a schedule:

```bash
# Create Cloud Run Job
gcloud run jobs create trading-agent \
    --image=gcr.io/samaanai-stg-1009-124126/trading-api-staging:latest \
    --region=us-central1 \
    --cpu=1 \
    --memory=512Mi \
    --max-retries=1 \
    --task-timeout=10m \
    --set-env-vars="RUN_MODE=single" \
    --set-secrets="ALPACA_API_KEY=alpaca-api-key:latest,ALPACA_SECRET_KEY=alpaca-secret-key:latest,GEMINI_API_KEY=gemini-api-key:latest"

# Create Cloud Scheduler to trigger every 5 minutes during market hours
gcloud scheduler jobs create http trading-agent-trigger \
    --location=us-central1 \
    --schedule="*/5 9-16 * * 1-5" \
    --time-zone="America/New_York" \
    --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/samaanai-stg-1009-124126/jobs/trading-agent:run" \
    --http-method=POST \
    --oauth-service-account-email=YOUR_SERVICE_ACCOUNT@samaanai-stg-1009-124126.iam.gserviceaccount.com
```

### Option 2: Built-in Background Thread (Simpler)

The current implementation uses a background thread that checks market hours automatically.
Just deploy to Cloud Run and keep it running.

### Cron Expression Breakdown
```
*/5 9-16 * * 1-5
│   │    │ │ │
│   │    │ │ └── Monday through Friday
│   │    │ └──── Every month
│   │    └────── Every day
│   └─────────── Hours 9 AM to 4 PM (Eastern)
└─────────────── Every 5 minutes
```

## IAM Permissions Needed

```bash
# Grant Cloud Scheduler permission to invoke Cloud Run
gcloud run jobs add-iam-policy-binding trading-agent \
    --region=us-central1 \
    --member=serviceAccount:YOUR_SERVICE_ACCOUNT@samaanai-stg-1009-124126.iam.gserviceaccount.com \
    --role=roles/run.invoker
```

## Verify Schedule

```bash
# List scheduled jobs
gcloud scheduler jobs list --location=us-central1

# Test manual trigger
gcloud scheduler jobs run trading-agent-trigger --location=us-central1
```
