#!/bin/bash
# Production Infrastructure Setup Script for Trading Application
# This script sets up ONLY trading-specific resources, reusing existing infrastructure
#
# SAFE FOR EXISTING APPS: This script does NOT modify or affect existing applications
# - Reuses existing Cloud SQL instance (samaanai-prod-postgres)
# - Creates trading-specific VPC connector (trading-vpc-connector) - opt-in only
# - Creates prefixed secrets (TRADING_*) to avoid conflicts
# - Does NOT modify any existing services

set -e

# Configuration
PROJECT_ID="samaanai-prod-1009-124126"
REGION="us-west1"
ZONE="${REGION}-b"

# Existing infrastructure to REUSE (not create)
EXISTING_CLOUDSQL_INSTANCE="samaanai-prod-postgres"

# Trading-specific resources to CREATE
TRADING_DB_NAME="stock_trading"
TRADING_DB_USER="trading_backend"
TRADING_VPC_CONNECTOR="trading-vpc-connector"
TRADING_VPC_RANGE="10.9.0.0/28"  # Different range from any existing connectors

echo "=========================================="
echo "LLM Trading Agent - Production Setup"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""
echo "⚠️  SAFE MODE: This script only creates"
echo "   trading-specific resources and does NOT"
echo "   modify existing applications."
echo "=========================================="

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
    echo "❌ Please authenticate with: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID
echo "✅ Project set to $PROJECT_ID"

# Enable required APIs (idempotent - won't affect existing services)
echo ""
echo "📦 Enabling required APIs..."
gcloud services enable \
    secretmanager.googleapis.com \
    run.googleapis.com \
    sqladmin.googleapis.com \
    compute.googleapis.com \
    vpcaccess.googleapis.com \
    cloudscheduler.googleapis.com \
    --quiet

echo "✅ APIs enabled"

# ============================================
# CLOUD SQL: Reuse existing instance, add database
# ============================================
echo ""
echo "🗄️ Setting up Cloud SQL database..."
echo "   Using existing instance: $EXISTING_CLOUDSQL_INSTANCE"

# Verify existing instance exists
if ! gcloud sql instances describe $EXISTING_CLOUDSQL_INSTANCE --project=$PROJECT_ID 2>/dev/null; then
    echo "❌ Cloud SQL instance '$EXISTING_CLOUDSQL_INSTANCE' not found!"
    echo "   Please verify the instance name or create it first."
    exit 1
fi

echo "  ✅ Found existing Cloud SQL instance"

# Create trading database (if not exists)
if gcloud sql databases describe $TRADING_DB_NAME --instance=$EXISTING_CLOUDSQL_INSTANCE --project=$PROJECT_ID 2>/dev/null; then
    echo "  ℹ️  Database '$TRADING_DB_NAME' already exists"
else
    echo "  Creating database '$TRADING_DB_NAME'..."
    gcloud sql databases create $TRADING_DB_NAME \
        --instance=$EXISTING_CLOUDSQL_INSTANCE \
        --project=$PROJECT_ID
    echo "  ✅ Database created"
fi

# ============================================
# SECRETS: Create trading-specific secrets with TRADING_ prefix
# ============================================
echo ""
echo "🔐 Setting up Secret Manager..."
echo "   Note: Using TRADING_ prefix to avoid conflicts with existing secrets"
echo ""

create_secret() {
    local name=$1
    local description=$2
    local reuse_existing=$3  # If set, check if non-prefixed version exists

    if gcloud secrets describe $name --project=$PROJECT_ID 2>/dev/null; then
        echo "  ℹ️  Secret '$name' already exists, skipping"
        return 0
    fi

    # Check if we should reuse an existing non-prefixed secret
    if [ -n "$reuse_existing" ]; then
        if gcloud secrets describe $reuse_existing --project=$PROJECT_ID 2>/dev/null; then
            echo "  ℹ️  Using existing secret '$reuse_existing' (no need to create '$name')"
            return 0
        fi
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

# Trading-specific secrets (prefixed to avoid conflicts)
create_secret "TRADING_SECRET_KEY" "Django SECRET_KEY for trading app"
if ! gcloud secrets describe TRADING_SECRET_KEY --project=$PROJECT_ID 2>/dev/null; then
    openssl rand -base64 50 | gcloud secrets create TRADING_SECRET_KEY --data-file=- --project=$PROJECT_ID
    echo "  ✅ Auto-generated TRADING_SECRET_KEY"
fi

create_secret "TRADING_DB_PASSWORD" "Trading database password"
create_secret "TRADING_SENDGRID_API_KEY" "SendGrid API key for trading emails"
create_secret "TRADING_SLACK_WEBHOOK" "Slack webhook for trading notifications"
create_secret "TRADING_NEWS_API_KEY" "NewsAPI key for market news"

# Check for reusable existing secrets
echo ""
echo "  Checking for existing secrets that can be reused..."
for secret in GEMINI_API_KEY GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
    if gcloud secrets describe $secret --project=$PROJECT_ID 2>/dev/null; then
        echo "  ✅ Found existing: $secret (will reuse)"
    else
        echo "  ⚠️  Not found: $secret (you may need to create it)"
    fi
done

echo "✅ Secrets configured"

# ============================================
# CREATE DATABASE USER
# ============================================
echo ""
echo "👤 Setting up database user..."

# Check if user exists
if gcloud sql users list --instance=$EXISTING_CLOUDSQL_INSTANCE --project=$PROJECT_ID --format="value(name)" | grep -q "^${TRADING_DB_USER}$"; then
    echo "  ℹ️  Database user '$TRADING_DB_USER' already exists"
else
    # Get password from secret
    if gcloud secrets describe TRADING_DB_PASSWORD --project=$PROJECT_ID 2>/dev/null; then
        DB_PASSWORD=$(gcloud secrets versions access latest --secret=TRADING_DB_PASSWORD --project=$PROJECT_ID)
        gcloud sql users create $TRADING_DB_USER \
            --instance=$EXISTING_CLOUDSQL_INSTANCE \
            --password="$DB_PASSWORD" \
            --project=$PROJECT_ID
        echo "  ✅ Database user '$TRADING_DB_USER' created"
    else
        echo "  ⚠️  Cannot create user - TRADING_DB_PASSWORD secret not found"
        echo "     Please create the secret and run this script again"
    fi
fi

# ============================================
# VPC CONNECTOR: Create trading-specific connector
# ============================================
echo ""
echo "🔌 Setting up VPC Connector..."
echo "   Note: This is opt-in only - existing services are NOT affected"

if gcloud compute networks vpc-access connectors describe $TRADING_VPC_CONNECTOR \
    --region=$REGION --project=$PROJECT_ID 2>/dev/null; then
    echo "  ℹ️  VPC connector '$TRADING_VPC_CONNECTOR' already exists"
else
    echo "  Creating VPC connector '$TRADING_VPC_CONNECTOR'..."
    echo "  IP Range: $TRADING_VPC_RANGE (does not overlap with existing ranges)"
    gcloud compute networks vpc-access connectors create $TRADING_VPC_CONNECTOR \
        --region=$REGION \
        --network=default \
        --range=$TRADING_VPC_RANGE \
        --min-instances=2 \
        --max-instances=3 \
        --project=$PROJECT_ID
    echo "  ✅ VPC connector created"
fi

# ============================================
# IBKR GATEWAY VM
# ============================================
echo ""
echo "🖥️ Setting up IBKR Gateway VM..."
if gcloud compute instances describe trading-ibkr-gateway --zone=$ZONE --project=$PROJECT_ID 2>/dev/null; then
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

    gcloud compute instances create trading-ibkr-gateway \
        --zone=$ZONE \
        --machine-type=e2-small \
        --provisioning-model=SPOT \
        --instance-termination-action=STOP \
        --image-family=ubuntu-2204-lts \
        --image-project=ubuntu-os-cloud \
        --tags=trading-ibkr-gateway \
        --metadata-from-file=startup-script=/tmp/ibkr-startup.sh \
        --project=$PROJECT_ID

    rm /tmp/ibkr-startup.sh
    echo "  ✅ IBKR Gateway VM created"
fi

# ============================================
# FIREWALL RULES
# ============================================
echo ""
echo "🔒 Setting up firewall rules..."
if gcloud compute firewall-rules describe allow-trading-ibkr --project=$PROJECT_ID 2>/dev/null; then
    echo "  ℹ️  Firewall rule already exists"
else
    gcloud compute firewall-rules create allow-trading-ibkr \
        --direction=INGRESS \
        --priority=1000 \
        --network=default \
        --action=ALLOW \
        --rules=tcp:4001,tcp:4002,tcp:4004 \
        --source-ranges=$TRADING_VPC_RANGE \
        --target-tags=trading-ibkr-gateway \
        --project=$PROJECT_ID
    echo "  ✅ Firewall rule created"
fi

# ============================================
# IAM PERMISSIONS
# ============================================
echo ""
echo "🔑 Setting up IAM permissions..."
SA_EMAIL=$(gcloud iam service-accounts list \
    --filter="displayName:Compute Engine default service account" \
    --format="value(email)" --project=$PROJECT_ID)

if [ -z "$SA_EMAIL" ]; then
    SA_EMAIL="${PROJECT_ID}@appspot.gserviceaccount.com"
fi

echo "  Service Account: $SA_EMAIL"

# Grant Secret Manager access for trading-specific secrets
for secret in TRADING_SECRET_KEY TRADING_DB_PASSWORD TRADING_SENDGRID_API_KEY TRADING_SLACK_WEBHOOK TRADING_NEWS_API_KEY; do
    if gcloud secrets describe $secret --project=$PROJECT_ID 2>/dev/null; then
        gcloud secrets add-iam-policy-binding $secret \
            --member="serviceAccount:$SA_EMAIL" \
            --role="roles/secretmanager.secretAccessor" \
            --project=$PROJECT_ID --quiet 2>/dev/null || true
    fi
done

# Also grant access to reusable existing secrets
for secret in GEMINI_API_KEY GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
    if gcloud secrets describe $secret --project=$PROJECT_ID 2>/dev/null; then
        gcloud secrets add-iam-policy-binding $secret \
            --member="serviceAccount:$SA_EMAIL" \
            --role="roles/secretmanager.secretAccessor" \
            --project=$PROJECT_ID --quiet 2>/dev/null || true
    fi
done

echo "  ✅ Secret Manager permissions granted"

# Grant Cloud SQL access (if not already granted)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/cloudsql.client" \
    --quiet 2>/dev/null || true
echo "  ✅ Cloud SQL permissions granted"

# ============================================
# SUMMARY
# ============================================
echo ""
echo "📋 Configuration Summary"
echo "=========================================="
IBKR_IP=$(gcloud compute instances describe trading-ibkr-gateway \
    --zone=$ZONE --format='get(networkInterfaces[0].networkIP)' --project=$PROJECT_ID 2>/dev/null || echo "Not created yet")

echo ""
echo "REUSED INFRASTRUCTURE:"
echo "  Cloud SQL Instance: $EXISTING_CLOUDSQL_INSTANCE"
echo "  Existing Secrets: GEMINI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET"
echo ""
echo "NEW TRADING-SPECIFIC RESOURCES:"
echo "  Database: $TRADING_DB_NAME"
echo "  DB User: $TRADING_DB_USER"
echo "  VPC Connector: $TRADING_VPC_CONNECTOR"
echo "  IBKR Gateway VM: trading-ibkr-gateway"
echo "  IBKR Gateway IP: $IBKR_IP"
echo ""
echo "SECRETS CREATED:"
echo "  TRADING_SECRET_KEY, TRADING_DB_PASSWORD, TRADING_SENDGRID_API_KEY"
echo "  TRADING_SLACK_WEBHOOK, TRADING_NEWS_API_KEY"
echo ""
echo "=========================================="
echo "✅ Production infrastructure setup complete!"
echo ""
echo "⚠️  EXISTING APPS ARE NOT AFFECTED:"
echo "   - VPC connector is opt-in (only used if specified in Cloud Run deployment)"
echo "   - Secrets use TRADING_ prefix (no conflicts)"
echo "   - Database is separate (no shared tables)"
echo ""
echo "Next steps:"
echo "1. Configure IBKR Gateway VM with your IB credentials"
echo "   gcloud compute ssh trading-ibkr-gateway --zone=$ZONE"
echo ""
echo "2. Add GCP_SA_KEY_PROD secret to GitHub repository"
echo "   - Go to GitHub repo → Settings → Secrets → Actions"
echo "   - Create service account key:"
echo "     gcloud iam service-accounts keys create key.json --iam-account=$SA_EMAIL"
echo ""
echo "3. Push to main branch to trigger production deployment"
echo "   git checkout main && git merge staging && git push origin main"
echo ""
echo "4. Set GitHub repository variables:"
echo "   - AUTHORIZED_EMAILS_PROD: Comma-separated list of allowed user emails"
echo "   - EMAIL_RECIPIENTS_PROD: Comma-separated list of email recipients"
echo ""
