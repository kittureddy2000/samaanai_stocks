# LLM Trading Agent

An AI-powered stock trading agent that uses **Google Gemini** to analyze market data and make automated trading decisions. Supports **Alpaca** (paper trading) and **Interactive Brokers** (live/paper).

## Live Demo

| Environment | Dashboard | API |
|-------------|-----------|-----|
| **Staging** | https://stg.trading.samaanai.com | https://trading-api-staging-hdp6ioqupa-uw.a.run.app |
| **Production** | https://trading.samaanai.com | https://trading-api-hdp6ioqupa-uw.a.run.app |

---

## Technology Stack

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.x | UI Framework |
| React Router | 6.x | Client-side Routing |
| Axios | 1.x | HTTP Client |
| Create React App | 5.x | Build Tool |
| Jest | 29.x | Unit Testing |
| Cypress | 13.x | E2E Testing |

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Django | 4.x | Web Framework |
| Django REST Framework | 3.x | REST API |
| PostgreSQL | 14.x | Database (Cloud SQL) |
| JWT (Simple JWT) | 5.x | Authentication |
| Django Allauth | 65.x | Google OAuth 2.0 |
| Gunicorn | 21.x | WSGI Server |

### Infrastructure
| Technology | Purpose |
|------------|---------|
| Docker | Containerization |
| Docker Compose | Local Development |
| Google Cloud Run | Production Runtime |
| Google Cloud SQL | Managed PostgreSQL |
| Google Compute Engine | IB Gateway VM |
| Google VPC Connector | Private network access to IB Gateway |
| Google Cloud Scheduler | Automated trading triggers |
| GitHub Actions | CI/CD Pipelines |
| Nginx | Frontend Static Server |

### External APIs & Brokers
| Service | Purpose |
|---------|---------|
| **Interactive Brokers** | Live/Paper Trading (Primary) |
| **Alpaca** | Paper Trading & Market Data (Fallback) |
| Google Gemini | LLM Analysis |
| NewsAPI | Sentiment Analysis (Optional) |
| Slack | Trade Notifications (Optional) |

---

## System Architecture

```
                                   CLOUD SCHEDULER
                              (Every 30 min, market hours)
                                        |
                                        v
+------------------+              POST /api/analyze
|   USER BROWSER   |                    |
|  (Dashboard UI)  |                    v
+--------+---------+        +------------------------+
         |                  |      CLOUD RUN         |
         | HTTPS            |   (Django Backend)     |
         v                  |                        |
+------------------+        |  +------------------+  |
| CLOUD RUN        |<------>|  | Trading Logic    |  |
| (React Frontend) |  API   |  | - LLM Analyst    |  |
+------------------+        |  | - Risk Manager   |  |
                            |  | - Order Manager  |  |
                            |  +--------+---------+  |
                            |           |            |
                            +-----------|------------+
                                        |
                    +-------------------+-------------------+
                    |                   |                   |
                    v                   v                   v
          +------------------+  +---------------+  +------------------+
          |   CLOUD SQL      |  | GOOGLE GEMINI |  |   IB GATEWAY     |
          |   (PostgreSQL)   |  |  (LLM API)    |  |   (GCE VM)       |
          | - Trade history  |  | - Analysis    |  | - Order execution|
          | - User accounts  |  | - Decisions   |  | - Market data    |
          +------------------+  +---------------+  +------------------+
                                                           |
                                                   VPC CONNECTOR
                                                   (10.8.0.0/28)
```

### Data Flow

1. **Cloud Scheduler** triggers analysis every 30 minutes during market hours (9:30 AM - 4:00 PM ET)
2. **Django Backend** receives the trigger and initiates analysis
3. **Market Data** is fetched from IBKR (or Alpaca as fallback)
4. **Technical Indicators** calculate RSI, MACD, Bollinger Bands, etc.
5. **Gemini LLM** analyzes data and recommends trades with confidence scores
6. **Risk Controls** validate trades against position limits and daily loss caps
7. **Order Manager** executes approved trades via IBKR API
8. **Dashboard** displays real-time portfolio, positions, and trade history

---

## Project Structure

```
Stock Trading/
├── manage.py                    # Django management script
├── backend/                     # Django project settings
│   ├── settings/
│   │   ├── base.py             # Shared settings
│   │   ├── development.py      # Local dev (SQLite)
│   │   └── production.py       # Cloud Run (PostgreSQL)
│   ├── urls.py                 # Root URL configuration
│   ├── wsgi.py                 # WSGI entry point
│   └── asgi.py                 # ASGI entry point
│
├── trading_api/                 # Main Django app
│   ├── models/
│   │   ├── user.py             # Custom User model
│   │   └── trade.py            # Trade & PortfolioSnapshot
│   ├── views/
│   │   ├── auth.py             # JWT + OAuth endpoints
│   │   └── api.py              # Trading API endpoints
│   ├── urls/
│   │   ├── auth.py             # /auth/* routes
│   │   └── api.py              # /api/* routes
│   ├── services/               # Business logic wrapper
│   └── admin.py                # Django admin config
│
├── frontend/                    # React Dashboard (CRA)
│   ├── src/
│   │   ├── App.js              # Main component
│   │   └── services/api.js     # API client with JWT
│   ├── package.json
│   └── Dockerfile
│
├── src/                         # Trading Logic (Python)
│   ├── llm/                    # Gemini LLM integration
│   │   ├── analyst.py          # Trading analysis
│   │   └── llm_client.py       # Gemini API client
│   ├── trading/                # Trade execution
│   │   ├── ibkr_broker.py      # IBKR API wrapper
│   │   ├── alpaca_client.py    # Alpaca API wrapper
│   │   ├── broker_factory.py   # Broker selection
│   │   ├── order_manager.py    # Order execution
│   │   ├── portfolio.py        # Portfolio tracking
│   │   └── risk_controls.py    # Risk management
│   └── data/                   # Market data
│       ├── market_data.py      # Price data
│       └── technical_indicators.py
│
├── scripts/                     # Utility scripts
│   └── migrate_data.py         # SQLite -> PostgreSQL migration
│
├── .github/workflows/           # CI/CD
│   ├── deploy-staging.yml      # Auto-deploy on push to staging
│   └── deploy-production.yml   # Auto-deploy on push to main
│
├── docker-compose.yml           # Local development
├── docker-compose.debug.yml     # Local IBKR testing
├── Dockerfile                   # Backend container
├── requirements.txt             # Python dependencies
└── README.md
```

---

## Configuration

### Environment Variables

#### Required for All Environments

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key for sessions | `your-secret-key` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIzaSy...` |

#### Broker Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BROKER_TYPE` | Broker to use (`ibkr` or `alpaca`) | `alpaca` |
| `IBKR_GATEWAY_HOST` | IB Gateway IP address | `127.0.0.1` |
| `IBKR_GATEWAY_PORT` | IB Gateway port (use **4004** for socat proxy) | `4004` |
| `IBKR_CLIENT_ID` | IBKR client ID | `1` |
| `ALPACA_API_KEY` | Alpaca API key (if using Alpaca) | - |
| `ALPACA_SECRET_KEY` | Alpaca secret key | - |

#### OAuth & Authentication

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `AUTHORIZED_EMAILS` | Comma-separated allowed emails |
| `FRONTEND_URL` | Frontend URL for OAuth redirects |

#### Database (Production)

| Variable | Description |
|----------|-------------|
| `DB_USER` | Cloud SQL username |
| `DB_PASSWORD` | Cloud SQL password |
| `DB_NAME` | Database name |
| `INSTANCE_CONNECTION_NAME` | Cloud SQL instance connection name |

#### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `NEWS_API_KEY` | - | NewsAPI key for sentiment |
| `SLACK_WEBHOOK_URL` | - | Slack notifications |
| `TRADING_STRATEGY` | `balanced` | aggressive, balanced, conservative |
| `ANALYSIS_INTERVAL` | `15` | Minutes between analyses |
| `MAX_POSITION_PCT` | `0.10` | Max 10% per position |
| `MAX_DAILY_LOSS_PCT` | `0.03` | Max 3% daily loss |
| `MIN_CONFIDENCE` | `0.70` | Min 70% LLM confidence |
| `STOP_LOSS_PCT` | `0.05` | 5% stop loss |
| `TAKE_PROFIT_PCT` | `0.10` | 10% take profit |

---

## Interactive Brokers Integration

### Architecture

```
Cloud Run (Django) ──VPC Connector──> GCE VM (10.138.0.3:4004)
                                              │
                                        socat proxy (4004 → localhost:4002)
                                              │
                                    Docker Container (ib-gateway)
                                              │
                                              v
                                       IBKR Servers

NOTE: Port 4004 uses a socat proxy inside the container that forwards to localhost:4002.
This bypasses the TrustedIPs restriction since the gateway sees connections from localhost.
```

### IB Gateway VM Details

| Component | Value |
|-----------|-------|
| **VM Name** | `ibkr-gateway` |
| **Zone** | `us-west1-b` |
| **Machine Type** | e2-small (Spot) |
| **Internal IP** | `10.138.0.3` |
| **Container** | `ghcr.io/gnzsnz/ib-gateway:stable` |
| **Trading Mode** | Paper (account DUO726424) |
| **VPC Connector** | `ibkr-connector` (10.8.0.0/28) |

### Docker Container Configuration

The IB Gateway runs in a Docker container with automatic login via IBC (IB Controller):

```bash
docker run -d --name ibgateway --restart=always \
  -p 4001:4001 -p 4002:4002 \
  -e TWS_USERID=YOUR_IBKR_USERNAME \
  -e TWS_PASSWORD=YOUR_IBKR_PASSWORD \
  -e TRADING_MODE=paper \
  -e READ_ONLY_API=no \
  -e IBC_TrustedTwsApiClientIPs=0.0.0.0/0 \
  -e ACCEPT_INCOMING_CONNECTION=accept \
  ghcr.io/gnzsnz/ib-gateway:stable
```

### Important: TrustedIPs Configuration

The IB Gateway must be configured to accept connections from the VPC connector IP range. Set the environment variable:

```
IBC_TrustedTwsApiClientIPs=0.0.0.0/0
```

If the jts.ini file has `TrustedIPs=127.0.0.1`, connections from Cloud Run will be rejected.

### VM Management Commands

```bash
# SSH into IB Gateway VM
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap

# View container logs
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker logs -f ibgateway'

# Check container status
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker ps'

# Restart container with correct config
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker stop ibgateway && docker rm ibgateway && \
    docker run -d --name ibgateway --restart=always \
    -p 4001:4001 -p 4002:4002 \
    -e TWS_USERID=YOUR_USERNAME \
    -e TWS_PASSWORD=YOUR_PASSWORD \
    -e TRADING_MODE=paper \
    -e READ_ONLY_API=no \
    -e IBC_TrustedTwsApiClientIPs=0.0.0.0/0 \
    -e ACCEPT_INCOMING_CONNECTION=accept \
    ghcr.io/gnzsnz/ib-gateway:stable'

# Start VM if stopped (spot preemption)
gcloud compute instances start ibkr-gateway --zone=us-west1-b
```

### Monthly Infrastructure Costs

| Resource | Cost |
|----------|------|
| GCE VM (e2-small spot) | ~$6 |
| VPC Connector | ~$7 |
| Cloud Run (backend) | ~$0-5 |
| Cloud Run (frontend) | ~$0-2 |
| Cloud SQL (db-f1-micro) | ~$8 |
| **Total** | **~$21-28/month** |

---

## Cloud Scheduler Configuration

The trading agent runs automatically during market hours via Cloud Scheduler:

```
Schedule: */30 9-16 * * 1-5 (America/New_York)
Target: POST https://trading-api-staging-hdp6ioqupa-uw.a.run.app/api/analyze
```

### Current Schedule

| Job Name | Schedule | Description |
|----------|----------|-------------|
| `trading-agent-trigger` | Every 30 min, 9am-4pm ET, Mon-Fri | Triggers LLM analysis |

### Managing the Scheduler

```bash
# List scheduled jobs
gcloud scheduler jobs list --location=us-central1

# Pause trading
gcloud scheduler jobs pause trading-agent-trigger --location=us-central1

# Resume trading
gcloud scheduler jobs resume trading-agent-trigger --location=us-central1

# Manual trigger
gcloud scheduler jobs run trading-agent-trigger --location=us-central1

# Update schedule (e.g., every 15 minutes)
gcloud scheduler jobs update http trading-agent-trigger \
  --location=us-central1 \
  --schedule="*/15 9-16 * * 1-5"
```

---

## Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose

### Backend Setup

```bash
# Clone and setup
cd "/path/to/Stock Trading"
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run migrations
python manage.py migrate --settings=backend.settings.development

# Start backend (port 8000)
python manage.py runserver 8000 --settings=backend.settings.development
```

### Frontend Setup

```bash
cd frontend
npm install
npm start
# Opens http://localhost:3000
```

### Docker Compose (Full Stack)

```bash
# Standard development
docker-compose up --build

# With local IBKR testing
docker-compose -f docker-compose.debug.yml up --build
```

### Testing IBKR Locally

For local IBKR testing, use the debug compose file which includes an IB Gateway container:

```bash
# Start IB Gateway + Backend
docker-compose -f docker-compose.debug.yml up --build

# VNC to IB Gateway for manual login (if needed)
# Connect to localhost:5900, password: 123456
```

---

## Cloud Deployment

### CI/CD Pipeline

| Branch | Action | Environment |
|--------|--------|-------------|
| `staging` | Auto-deploy on push | Staging |
| `main` | Auto-deploy on push | Production |

### GitHub Secrets Required

Add these to Repository Settings > Secrets and variables > Actions:

#### Secrets

| Secret | Description |
|--------|-------------|
| `GCP_SA_KEY` | GCP Service Account JSON (staging) |
| `GCP_SA_KEY_PROD` | GCP Service Account JSON (production) |
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_SECRET_KEY_PROD` | Django secret key (production) |
| `DB_PASSWORD` | Cloud SQL password (staging) |
| `DB_PASSWORD_PROD` | Cloud SQL password (production) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `NEWS_API_KEY` | NewsAPI key |
| `GOOGLE_CLIENT_ID` | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |

#### Variables

| Variable | Description |
|----------|-------------|
| `AUTHORIZED_EMAILS` | Comma-separated allowed emails |

### Deploy to Staging

```bash
git checkout staging
git add .
git commit -m "Your changes"
git push origin staging
# GitHub Actions auto-deploys to Cloud Run
```

### Deploy to Production

```bash
git checkout main
git merge staging
git push origin main
# GitHub Actions auto-deploys to Cloud Run
```

---

## Production Deployment Checklist

### 1. Create GCP Resources

```bash
# Set project
gcloud config set project YOUR_PROD_PROJECT

# Create Cloud SQL instance
gcloud sql instances create trading-db \
  --database-version=POSTGRES_14 \
  --tier=db-f1-micro \
  --region=us-west1

# Create database and user
gcloud sql databases create stock_trading --instance=trading-db
gcloud sql users create samaanai_backend --instance=trading-db \
  --password=YOUR_PASSWORD

# Create VPC Connector (for IBKR)
gcloud compute networks vpc-access connectors create ibkr-connector \
  --region=us-west1 \
  --network=default \
  --range=10.8.0.0/28
```

### 2. Create IB Gateway VM

```bash
# Create VM
gcloud compute instances create ibkr-gateway \
  --zone=us-west1-b \
  --machine-type=e2-small \
  --provisioning-model=SPOT \
  --tags=ibkr-gateway \
  --image-family=cos-stable \
  --image-project=cos-cloud

# Create firewall rule for VPC connector
gcloud compute firewall-rules create allow-vpc-to-ibkr \
  --source-ranges=10.8.0.0/28 \
  --target-tags=ibkr-gateway \
  --allow=tcp:4001,tcp:4002

# SSH and start container
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap
# Then run docker command from IBKR section above
```

### 3. Configure Cloud Scheduler

```bash
# Create scheduler job
gcloud scheduler jobs create http trading-agent-trigger \
  --location=us-central1 \
  --schedule="*/30 9-16 * * 1-5" \
  --time-zone="America/New_York" \
  --uri="https://YOUR_BACKEND_URL/api/analyze" \
  --http-method=POST
```

### 4. Add GitHub Secrets

Add all required secrets to GitHub repository settings.

### 5. Update Cloud Run Environment

After first deployment, update IBKR settings:

```bash
gcloud run services update trading-api \
  --region=us-west1 \
  --update-env-vars="BROKER_TYPE=ibkr,IBKR_GATEWAY_HOST=VM_INTERNAL_IP,IBKR_GATEWAY_PORT=4002,FRONTEND_URL=https://your-domain.com"
```

### 6. Configure Domain Mapping (Optional)

```bash
# Map custom domain to frontend
gcloud run domain-mappings create \
  --service=trading-dashboard \
  --domain=trading.yourdomain.com \
  --region=us-west1
```

---

## API Endpoints

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register with email/password |
| `/auth/login` | POST | Login, returns JWT tokens |
| `/auth/logout` | POST | Blacklist refresh token |
| `/auth/me` | GET | Get current user info |
| `/auth/token/refresh` | POST | Refresh access token |

### Trading API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth) |
| `/api/broker-status` | GET | Broker connection diagnostics |
| `/api/portfolio` | GET | Portfolio & positions |
| `/api/risk` | GET | Risk status & limits |
| `/api/market` | GET | Market open/close status |
| `/api/watchlist` | GET | Watchlist with prices |
| `/api/trades` | GET | Trade history |
| `/api/config` | GET | Trading configuration |
| `/api/indicators` | GET | Technical indicators |
| `/api/analyze` | POST | Trigger trading analysis |

---

## Risk Management

| Control | Default | Description |
|---------|---------|-------------|
| **Max Position Size** | 10% | No single stock exceeds 10% of portfolio |
| **Max Daily Loss** | 3% | Trading halts if daily losses exceed 3% |
| **Min Confidence** | 70% | Only executes trades with >70% LLM confidence |
| **Stop Loss** | 5% | Default stop-loss per trade |
| **Take Profit** | 10% | Default take-profit target |
| **Kill Switch** | Manual | Emergency stop for all trading |

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Connection refused" to IBKR | TrustedIPs=127.0.0.1 | Set `IBC_TrustedTwsApiClientIPs=0.0.0.0/0` |
| IBKR port 4004 error | Wrong port configured | Use 4002 for paper, 4001 for live |
| "429 RESOURCE_EXHAUSTED" | Gemini quota exceeded | Wait for daily reset |
| OAuth redirect wrong URL | FRONTEND_URL misconfigured | Update Cloud Run env var |
| VM stopped | Spot preemption | Run `gcloud compute instances start` |

### View Cloud Run Logs

```bash
# Staging
gcloud logging read "resource.labels.service_name=trading-api-staging" \
  --project=samaanai-stg-1009-124126 --limit=50

# Search for specific errors
gcloud logging read "resource.labels.service_name=trading-api-staging AND textPayload:IBKR" \
  --project=samaanai-stg-1009-124126 --limit=20
```

### Check IB Gateway Status

```bash
# Container logs
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker logs ibgateway --tail 50'

# Port status
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='ss -tlnp | grep -E "4001|4002"'

# Environment variables
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker inspect ibgateway --format "{{range .Config.Env}}{{println .}}{{end}}" | grep -E "IBC_|TWS_|TRADING"'
```

---

## Important Notes

1. **Paper Trading Only**: Default configuration uses IBKR paper trading (no real money)
2. **Market Hours**: Agent only trades during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
3. **Pattern Day Trading**: If using live trading with <$25k, be aware of PDT rules
4. **No Guarantees**: AI trading is experimental. Past performance doesn't predict future results
5. **Your Responsibility**: Always monitor the agent and set appropriate risk limits

---

## License

MIT
