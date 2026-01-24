# LLM Trading Agent

An AI-powered stock trading agent that uses **Google Gemini** to analyze market data and make automated trading decisions. Supports **Alpaca** (paper trading) and **Interactive Brokers** (live/paper).

## 🚀 Live Demo

| Environment | Dashboard | API |
|-------------|-----------|-----|
| **Staging** | https://stg.trading.samaanai.com | https://trading-api-staging-*.run.app |
| **Production** | https://trading.samaanai.com | https://trading-api-*.run.app |

---

## 📐 Technology Stack

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
| Google Compute Engine | IB Gateway VM (~$3/month) |
| GitHub Actions | CI/CD Pipelines |
| Nginx | Frontend Static Server |

### External APIs & Brokers
| Service | Purpose |
|---------|---------|
| **Alpaca** | Paper Trading & Market Data (Default) |
| **Interactive Brokers** | Live/Paper Trading (Optional) |
| Google Gemini | LLM Analysis |
| NewsAPI | Sentiment Analysis (Optional) |
| Slack | Trade Notifications (Optional) |

---

## 📁 Project Structure

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
│   │   ├── alpaca_client.py    # Alpaca API wrapper
│   │   ├── order_manager.py    # Order execution
│   │   ├── portfolio.py        # Portfolio tracking
│   │   └── risk_controls.py    # Risk management
│   └── data/                   # Market data
│       ├── market_data.py      # Price data
│       └── technical_indicators.py
│
├── scripts/                     # Utility scripts
│   └── migrate_data.py         # SQLite → PostgreSQL migration
│
├── .github/workflows/           # CI/CD
│   ├── deploy-staging.yml      # Auto-deploy on push to staging
│   └── deploy-production.yml   # Auto-deploy on push to main
│
├── docker-compose.yml           # Local development
├── Dockerfile                   # Backend container
├── requirements.txt             # Python dependencies
└── README.md
```

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM TRADING AGENT                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CLOUD SCHEDULER (Every 15 min)                    │   │
│  │                   POST /api/analyze during market hours              │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│         ┌───────────────────────┼───────────────────────┐                  │
│         ▼                       ▼                       ▼                  │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐            │
│  │   DATA      │        │   GEMINI    │        │   EXECUTION │            │
│  │   LAYER     │───────▶│   BRAIN     │───────▶│   ENGINE    │            │
│  └─────────────┘        └─────────────┘        └─────────────┘            │
│         │                      │                      │                    │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐            │
│  │ • Alpaca IEX│        │ • Analysis  │        │ • Order     │            │
│  │ • yfinance  │        │ • Strategy  │        │   Manager   │            │
│  │   (fallback)│        │ • Retry     │        │ • Risk Ctrl │            │
│  │ • Technical │        │   Logic     │        │ • Portfolio │            │
│  │   Indicators│        │ • Decisions │        │             │            │
│  └─────────────┘        └─────────────┘        └─────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   ALPACA API     │    │   GOOGLE GEMINI  │    │   REACT DASH     │
│ Trading & Data   │    │   LLM Analysis   │    │   Port 80 (Nginx)│
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

### Data Flow

1. **Cloud Scheduler** triggers analysis every 15 minutes during market hours
2. **Data Layer** fetches market data from Alpaca (with yfinance fallback)
3. **Technical Indicators** calculate RSI, MACD, Bollinger Bands, etc.
4. **Gemini LLM** analyzes data and recommends trades with confidence scores
5. **Risk Controls** validate trades against position limits and daily loss caps
6. **Order Manager** executes approved trades via Alpaca API
7. **Dashboard** displays real-time portfolio, positions, and trade history

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ALPACA_API_KEY` | Alpaca paper trading API key | ✅ |
| `ALPACA_SECRET_KEY` | Alpaca API secret | ✅ |
| `GEMINI_API_KEY` | Google Gemini API key | ✅ |
| `DJANGO_SECRET_KEY` | Django secret key for sessions | ✅ |
| `GOOGLE_CLIENT_ID` | OAuth client ID | For auth |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | For auth |
| `DB_PASSWORD` | Cloud SQL password | For prod |
| `NEWS_API_KEY` | NewsAPI key for sentiment | Optional |
| `SLACK_WEBHOOK_URL` | Slack notifications | Optional |

### Trading Configuration

Set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_STRATEGY` | balanced | aggressive, balanced, conservative |
| `ANALYSIS_INTERVAL` | 15 | Minutes between analyses |
| `MAX_POSITION_PCT` | 0.10 | Max 10% per position |
| `MAX_DAILY_LOSS_PCT` | 0.03 | Max 3% daily loss |
| `MIN_CONFIDENCE` | 0.70 | Min 70% LLM confidence |
| `STOP_LOSS_PCT` | 0.05 | 5% stop loss |
| `TAKE_PROFIT_PCT` | 0.10 | 10% take profit |

---

## 🚀 Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose (optional)

### Backend Setup

```bash
# Clone and setup
cd "/Users/krishnayadamakanti/Documents/Stock Trading"
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
docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

---

## ☁️ Cloud Deployment

### CI/CD Pipeline

| Branch | Action | Environment |
|--------|--------|-------------|
| `staging` | Auto-deploy on push | Staging |
| `main` | Auto-deploy on push | Production |

### GitHub Secrets Required

Add these to your repository Settings → Secrets:

**Shared:**
- `GCP_SA_KEY` - GCP Service Account JSON (staging)
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `DJANGO_SECRET_KEY`
- `DB_PASSWORD`

**Production-specific:**
- `GCP_SA_KEY_PROD` - GCP Service Account JSON (production)
- `ALPACA_API_KEY_PROD`, `ALPACA_SECRET_KEY_PROD` (if different)
- `DJANGO_SECRET_KEY_PROD`
- `DB_PASSWORD_PROD`

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

## 🔄 Production Migration Checklist

When ready to go to production:

1. **Create Production Cloud SQL Instance** (if not exists)
   ```bash
   gcloud sql instances create samaanai-backend-db \
     --database-version=POSTGRES_14 \
     --tier=db-f1-micro \
     --region=us-west1
   ```

2. **Create Database and User**
   ```bash
   gcloud sql databases create stock_trading --instance=samaanai-backend-db
   gcloud sql users create samaanai_backend --instance=samaanai-backend-db \
     --password=YOUR_PASSWORD
   ```

3. **Add Production Secrets to GitHub**
   - `GCP_SA_KEY_PROD`
   - `DJANGO_SECRET_KEY_PROD`
   - `DB_PASSWORD_PROD`
   - `ALPACA_API_KEY_PROD` (live trading keys if different)

4. **Run Migrations on Production**
   ```bash
   # Connect to Cloud Run and run migrations
   # Or include in Dockerfile startup
   ```

5. **Migrate Data (if needed)**
   ```bash
   # Use Cloud SQL Proxy
   cloud_sql_proxy -instances=samaanai-prod:us-west1:samaanai-backend-db=tcp:5432
   
   export DB_HOST=127.0.0.1
   export DB_PASSWORD=your_prod_password
   python scripts/migrate_data.py
   ```

6. **Push to main branch**
   ```bash
   git checkout main
   git merge staging
   git push origin main
   ```

---

## 📊 API Endpoints

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
| `/api/portfolio` | GET | Portfolio & positions |
| `/api/risk` | GET | Risk status & limits |
| `/api/market` | GET | Market open/close status |
| `/api/watchlist` | GET | Watchlist with prices |
| `/api/trades` | GET | Trade history |
| `/api/config` | GET | Trading configuration |
| `/api/indicators` | GET | Technical indicators |
| `/api/analyze` | POST | Trigger trading analysis |

---

## 🛡️ Risk Management

| Control | Default | Description |
|---------|---------|-------------|
| **Max Position Size** | 10% | No single stock exceeds 10% of portfolio |
| **Max Daily Loss** | 3% | Trading halts if daily losses exceed 3% |
| **Min Confidence** | 70% | Only executes trades with >70% LLM confidence |
| **Stop Loss** | 5% | Default stop-loss per trade |
| **Take Profit** | 10% | Default take-profit target |
| **Kill Switch** | Manual | Emergency stop for all trading |

---

## 📈 Technical Indicators

| Indicator | Purpose |
|-----------|---------|
| **RSI (14)** | Overbought (>70) / Oversold (<30) detection |
| **MACD** | Trend direction & momentum |
| **SMA (20, 50)** | Medium-term trend |
| **EMA (12, 26)** | Short-term trend |
| **Bollinger Bands** | Volatility & price extremes |
| **Stochastic** | Momentum oscillator |
| **OBV** | Volume-based trend confirmation |
| **ATR** | Volatility measurement |

---

## 📋 Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "429 RESOURCE_EXHAUSTED" | Gemini quota exceeded | Wait for daily reset or enable billing |
| "503 UNAVAILABLE" | Gemini overloaded | Retry logic handles automatically |
| "No historical data" | Alpaca IEX gap | yfinance fallback handles this |
| No trades executing | LLM confidence < 70% | Normal - wait for better signals |
| JWT token expired | Access token lifetime | Frontend auto-refreshes tokens |

### View Cloud Run Logs

```bash
# Staging
gcloud logging read "resource.labels.service_name=trading-api-staging" \
  --project=samaanai-stg-1009-124126 --limit=50

# Production
gcloud logging read "resource.labels.service_name=trading-api" \
  --project=samaanai-prod-1009-124126 --limit=50
```

---

## 🏦 Interactive Brokers Integration

The system supports switching between Alpaca and Interactive Brokers via environment variable. IB Gateway runs as a Docker container on a GCE VM with **automatic login**.

### Architecture

```
Cloud Run ──VPC Connector──► GCE VM (10.138.0.3:4002)
     │                              │
     │ HTTP/REST                    │ Docker Container
     ▼                              ▼
  Django API                  IB Gateway → IBKR Servers
```

### Broker Selection

```bash
# Use Alpaca (default)
export BROKER_TYPE=alpaca

# Use Interactive Brokers (already configured on Cloud Run)
export BROKER_TYPE=ibkr
export IBKR_GATEWAY_HOST=10.138.0.3    # VM internal IP
export IBKR_GATEWAY_PORT=4002          # 4002=paper, 4001=live
export IBKR_CLIENT_ID=1
```

### IB Gateway VM

| Component | Details |
|-----------|---------|
| **VM Name** | `ibkr-gateway` |
| **Zone** | `us-west1-b` |
| **Machine Type** | e2-small (Spot) |
| **Internal IP** | `10.138.0.3` |
| **Container** | `ghcr.io/gnzsnz/ib-gateway:stable` |
| **Trading Mode** | Paper (account DUO726424) |
| **VPC Connector** | `ibkr-connector` |

### Monthly Costs

| Resource | Cost |
|----------|------|
| VM (e2-small spot) | ~$6 |
| VPC Connector | ~$7 |
| **Total** | **~$13/month** |

### The Docker container handles login automatically!

The IB Gateway Docker image (`ghcr.io/gnzsnz/ib-gateway`) includes IBC (IB Controller) which:
- Automatically logs in using credentials passed via environment variables
- Dismisses popups and warnings
- Restarts the gateway if it crashes
- No manual login required!

### VM Management Commands

```bash
# SSH into IB Gateway VM (uses IAP tunnel)
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap

# View container logs (live)
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker logs -f ibgateway'

# View recent logs
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker logs ibgateway --tail 50'

# Check container status
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker ps'

# Restart container
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker restart ibgateway'

# Check if port 4002 is listening
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='ss -tlnp | grep 4002'
```

### Updating IBKR Credentials

```bash
# Stop and remove old container
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker stop ibgateway && docker rm ibgateway'

# Start new container with updated credentials
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker run -d --name ibgateway --restart=always \
    -p 4001:4001 -p 4002:4002 \
    -e TWS_USERID=YOUR_USERNAME \
    -e TWS_PASSWORD=YOUR_PASSWORD \
    -e TRADING_MODE=paper \
    -e READ_ONLY_API=no \
    ghcr.io/gnzsnz/ib-gateway:stable'
```

### Switching to Live Trading

```bash
# Update Cloud Run environment
gcloud run services update samaanai-backend-staging \
  --region=us-west1 \
  --update-env-vars=IBKR_GATEWAY_PORT=4001

# Restart container with live mode
gcloud compute ssh ibkr-gateway --zone=us-west1-b --tunnel-through-iap \
  --command='docker stop ibgateway && docker rm ibgateway && \
    docker run -d --name ibgateway --restart=always \
    -p 4001:4001 -p 4002:4002 \
    -e TWS_USERID=YOUR_USERNAME \
    -e TWS_PASSWORD=YOUR_PASSWORD \
    -e TRADING_MODE=live \
    -e READ_ONLY_API=no \
    ghcr.io/gnzsnz/ib-gateway:stable'
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Container not running | `docker restart ibgateway` |
| Login failed | Check credentials in `docker logs ibgateway` |
| Port not listening | Wait 30-60 seconds for gateway startup |
| Connection timeout | Verify VPC connector: `gcloud compute networks vpc-access connectors list --region=us-west1` |
| VM stopped (spot preemption) | `gcloud compute instances start ibkr-gateway --zone=us-west1-b` |

---

## ⚠️ Important Notes

1. **Paper Trading Only**: Default configuration uses Alpaca paper trading (no real money)
2. **Market Hours**: Agent only trades during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
3. **Pattern Day Trading**: If using live trading with <$25k, be aware of PDT rules
4. **No Guarantees**: AI trading is experimental. Past performance doesn't predict future results
5. **Your Responsibility**: Always monitor the agent and set appropriate risk limits

---

## 📄 License

MIT