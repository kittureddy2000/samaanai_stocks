#!/bin/bash
# Production Infrastructure Setup Script
# Run this once to set up all GCP resources for production

set -e

# Configuration
PROJECT_ID="samaanai-prod-1009-124126"
REGION="us-west1"
ZONE="${REGION}-b"

echo "=========================================="
echo "LLM Trading Agent - Production Setup"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "=========================================="

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
    echo "❌ Please authenticate with: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID
echo "✅ Project set to $PROJECT_ID"

# Enable required APIs
echo ""
echo "📦 Enabling required APIs..."
gcloud services enable \
    secretmanager.googleapis.com \
    run.googleapis.com \
    sqladmin.googleapis.com \
    compute.googleapis.com \
    vpcaccess.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    --quiet

echo "✅ APIs enabled"

# Create Artifact Registry repository
echo ""
echo "📦 Setting up Artifact Registry..."
gcloud artifacts repositories describe trading-images \
    --location=$REGION 2>/dev/null || \
gcloud artifacts repositories create trading-images \
    --repository-format=docker \
    --location=$REGION \
    --description="Trading application Docker images"
echo "✅ Artifact Registry ready"

# Create secrets (interactive prompts)
echo ""
echo "🔐 Setting up Secret Manager..."
echo "Note: You can skip secrets that already exist."
echo ""

create_secret() {
    local name=$1
    local description=$2

    if gcloud secrets describe $name --project=$PROJECT_ID 2>/dev/null; then
        echo "  ℹ️  Secret '$name' already exists, skipping"
        return 0
    fi

    echo -n "  Enter value for $name ($description): "
    read -s value
    echo ""

    if [ -z "$value" ]; then
        echo "  ⚠️  Skipping $name (empty value)"
        return 0
    fi

    echo -n "$value" | gcloud secrets create $name --data-file=- --project=$PROJECT_ID
    echo "  ✅ Created secret: $name"
}

# Create all required secrets
create_secret "django-secret-key" "Django SECRET_KEY (press Enter to auto-generate)"
if ! gcloud secrets describe django-secret-key --project=$PROJECT_ID 2>/dev/null; then
    openssl rand -base64 50 | gcloud secrets create django-secret-key --data-file=- --project=$PROJECT_ID
    echo "  ✅ Auto-generated django-secret-key"
fi

create_secret "db-password" "Cloud SQL database password"
create_secret "gemini-api-key" "Google Gemini API key"
create_secret "google-client-id" "Google OAuth client ID"
create_secret "google-client-secret" "Google OAuth client secret"
create_secret "sendgrid-api-key" "SendGrid API key (for emails)"
create_secret "slack-webhook-url" "Slack webhook URL (for notifications)"
create_secret "news-api-key" "NewsAPI key (optional)"

echo "✅ Secrets configured"

# Create Cloud SQL instance
echo ""
echo "🗄️ Setting up Cloud SQL..."
if gcloud sql instances describe samaanai-backend-db --project=$PROJECT_ID 2>/dev/null; then
    echo "  ℹ️  Cloud SQL instance already exists"
else
    echo "  Creating Cloud SQL instance (this takes ~5 minutes)..."
    gcloud sql instances create samaanai-backend-db \
        --database-version=POSTGRES_14 \
        --tier=db-custom-1-3840 \
        --region=$REGION \
        --storage-type=SSD \
        --storage-size=20GB \
        --storage-auto-increase \
        --backup-start-time=04:00 \
        --availability-type=zonal \
        --maintenance-window-day=SUN \
        --maintenance-window-hour=03 \
        --project=$PROJECT_ID

    # Create database
    gcloud sql databases create stock_trading \
        --instance=samaanai-backend-db \
        --project=$PROJECT_ID

    # Create user
    DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password --project=$PROJECT_ID)
    gcloud sql users create samaanai_backend \
        --instance=samaanai-backend-db \
        --password="$DB_PASSWORD" \
        --project=$PROJECT_ID

    echo "  ✅ Cloud SQL instance created"
fi

# Create VPC connector
echo ""
echo "🔌 Setting up VPC Connector..."
if gcloud compute networks vpc-access connectors describe ibkr-connector \
    --region=$REGION --project=$PROJECT_ID 2>/dev/null; then
    echo "  ℹ️  VPC connector already exists"
else
    gcloud compute networks vpc-access connectors create ibkr-connector \
        --region=$REGION \
        --network=default \
        --range=10.8.0.0/28 \
        --min-instances=2 \
        --max-instances=3 \
        --project=$PROJECT_ID
    echo "  ✅ VPC connector created"
fi

# Create IBKR Gateway VM
echo ""
echo "🖥️ Setting up IBKR Gateway VM..."
if gcloud compute instances describe ibkr-gateway-prod --zone=$ZONE --project=$PROJECT_ID 2>/dev/null; then
    echo "  ℹ️  IBKR Gateway VM already exists"
else
    # Create startup script
    cat > /tmp/ibkr-startup.sh << 'STARTUP_EOF'
#!/bin/bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Pull and run IB Gateway
docker pull ghcr.io/gnzsnz/ib-gateway:stable

# Create container (will need to be configured with credentials)
docker run -d \
    --name ib-gateway \
    --restart unless-stopped \
    -p 4001:4001 \
    -p 4002:4002 \
    -e TWS_USERID=your_ib_username \
    -e TWS_PASSWORD=your_ib_password \
    -e TRADING_MODE=paper \
    -e TWS_ACCEPT_INCOMING=accept \
    ghcr.io/gnzsnz/ib-gateway:stable

# Install and configure socat for proxy
apt-get update && apt-get install -y socat
socat TCP-LISTEN:4004,fork,reuseaddr TCP:localhost:4002 &
STARTUP_EOF

    gcloud compute instances create ibkr-gateway-prod \
        --zone=$ZONE \
        --machine-type=e2-small \
        --provisioning-model=SPOT \
        --instance-termination-action=STOP \
        --image-family=ubuntu-2204-lts \
        --image-project=ubuntu-os-cloud \
        --tags=ibkr-gateway \
        --metadata-from-file=startup-script=/tmp/ibkr-startup.sh \
        --project=$PROJECT_ID

    rm /tmp/ibkr-startup.sh
    echo "  ✅ IBKR Gateway VM created"
fi

# Create firewall rule
echo ""
echo "🔒 Setting up firewall rules..."
if gcloud compute firewall-rules describe allow-ibkr-gateway --project=$PROJECT_ID 2>/dev/null; then
    echo "  ℹ️  Firewall rule already exists"
else
    gcloud compute firewall-rules create allow-ibkr-gateway \
        --direction=INGRESS \
        --priority=1000 \
        --network=default \
        --action=ALLOW \
        --rules=tcp:4001,tcp:4002,tcp:4004 \
        --source-ranges=10.8.0.0/28 \
        --target-tags=ibkr-gateway \
        --project=$PROJECT_ID
    echo "  ✅ Firewall rule created"
fi

# Grant IAM permissions to Cloud Run service account
echo ""
echo "🔑 Setting up IAM permissions..."
SA_EMAIL=$(gcloud iam service-accounts list \
    --filter="displayName:Compute Engine default service account" \
    --format="value(email)" --project=$PROJECT_ID)

if [ -z "$SA_EMAIL" ]; then
    SA_EMAIL="${PROJECT_ID}@appspot.gserviceaccount.com"
fi

echo "  Service Account: $SA_EMAIL"

# Grant Secret Manager access
for secret in django-secret-key db-password gemini-api-key google-client-id google-client-secret sendgrid-api-key slack-webhook-url news-api-key; do
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:$SA_EMAIL" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID --quiet 2>/dev/null || true
done
echo "  ✅ Secret Manager permissions granted"

# Grant Cloud SQL access
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/cloudsql.client" \
    --quiet 2>/dev/null || true
echo "  ✅ Cloud SQL permissions granted"

# Get IBKR VM IP
echo ""
echo "📋 Configuration Summary"
echo "=========================================="
IBKR_IP=$(gcloud compute instances describe ibkr-gateway-prod \
    --zone=$ZONE --format='get(networkInterfaces[0].networkIP)' --project=$PROJECT_ID 2>/dev/null || echo "Not created yet")
echo "IBKR Gateway IP: $IBKR_IP"
echo "Cloud SQL Instance: samaanai-backend-db"
echo "VPC Connector: ibkr-connector"
echo "Region: $REGION"
echo ""
echo "=========================================="
echo "✅ Production infrastructure setup complete!"
echo ""
echo "Next steps:"
echo "1. Configure IBKR Gateway VM with your IB credentials"
echo "   gcloud compute ssh ibkr-gateway-prod --zone=$ZONE"
echo ""
echo "2. Add GCP_SA_KEY_PROD secret to GitHub repository"
echo "   - Go to GitHub repo → Settings → Secrets → Actions"
echo "   - Create service account key:"
echo "     gcloud iam service-accounts keys create key.json --iam-account=$SA_EMAIL"
echo ""
echo "3. Push to main branch to trigger production deployment"
echo "   git checkout main && git merge staging && git push origin main"
echo ""
echo "4. Set GitHub repository variables (optional):"
echo "   - AUTHORIZED_EMAILS_PROD: Comma-separated list of allowed user emails"
echo "   - EMAIL_RECIPIENTS_PROD: Comma-separated list of email recipients"
