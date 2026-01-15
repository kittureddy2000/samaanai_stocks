# LLM Trading Agent

An AI-powered stock trading agent that uses **Google Gemini** to analyze market data and make automated trading decisions on Alpaca's paper trading platform, with a React dashboard and Cloud Run deployment.

## 🚀 Live Demo

- **Staging Dashboard**: https://stg.trading.samaanai.com
- **Staging API**: https://trading-api-staging-362270100637.us-central1.run.app

---

## ✨ Features

### Core Trading
- 🤖 **LLM-Powered Analysis**: Google Gemini analyzes technical indicators and recommends trades
- 📊 **Technical Indicators**: RSI, MACD, Moving Averages, Bollinger Bands, Stochastic, OBV
- 🛡️ **Risk Management**: Position sizing, stop-loss, daily loss limits, kill switch
- 📈 **Paper Trading**: Safe testing with Alpaca's paper trading environment

### Dashboard
- � **Modern React UI**: Real-time portfolio view with dark theme
- 📋 **Live Positions**: Shows all current holdings with P&L
- � **Trade History**: See all executed trades from Alpaca
- 📊 **Technical Indicators**: Live RSI, MACD signals for watchlist

### Cloud Deployment
- ☁️ **Cloud Run**: Auto-scaling serverless deployment
- ⏰ **Cloud Scheduler**: Automated trading every 30 minutes during market hours
- 🔐 **Google OAuth**: Secure login with authorized emails
- 🔄 **CI/CD**: GitHub Actions auto-deploy on push to `staging` or `main`

---

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM TRADING AGENT                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CLOUD SCHEDULER (Every 30 min)                    │   │
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

---

## 📁 Project Structure

```
Stock Trading/
├── src/                          # Backend Python Application
│   ├── main.py                   # Entry point, CLI, scheduling
│   ├── config.py                 # Configuration from environment
│   ├── dashboard_app.py          # Flask API server
│   │
│   ├── data/                     # DATA LAYER
│   │   ├── market_data.py        # Alpaca + yfinance data client
│   │   ├── technical_indicators.py   # RSI, MACD, Bollinger, etc.
│   │   └── data_aggregator.py    # Combines data for LLM
│   │
│   ├── llm/                      # LLM BRAIN
│   │   ├── prompts.py            # System & user prompts
│   │   ├── llm_client.py         # Gemini API with retry logic
│   │   └── analyst.py            # Orchestrates analysis
│   │
│   ├── trading/                  # EXECUTION ENGINE
│   │   ├── alpaca_client.py      # Alpaca trading wrapper
│   │   ├── order_manager.py      # Order execution
│   │   ├── portfolio.py          # Portfolio tracking
│   │   └── risk_controls.py      # Position limits, kill switch
│   │
│   └── utils/                    # UTILITIES
│       ├── auth.py               # Google OAuth
│       ├── logger.py             # Logging configuration
│       └── slack.py              # Slack notifications
│
├── dashboard/                    # Frontend React Application
│   ├── src/
│   │   ├── App.jsx               # Main dashboard component
│   │   ├── api.js                # API client
│   │   └── index.css             # Styling
│   ├── Dockerfile                # Frontend container
│   └── nginx.conf                # Nginx configuration
│
├── .github/workflows/            # CI/CD Pipelines
│   ├── deploy-staging.yml        # Deploy to staging on push
│   └── deploy-production.yml     # Deploy to prod (manual)
│
├── Dockerfile                    # Backend container
├── .env.example                  # Environment template
└── README.md                     # This file
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ALPACA_API_KEY` | Alpaca paper trading API key | ✅ |
| `ALPACA_SECRET_KEY` | Alpaca API secret | ✅ |
| `GEMINI_API_KEY` | Google Gemini API key | ✅ |
| `NEWS_API_KEY` | NewsAPI key for sentiment | Optional |
| `GOOGLE_CLIENT_ID` | OAuth client ID | For auth |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | For auth |
| `FLASK_SECRET_KEY` | Session encryption key | For auth |
| `AUTHORIZED_EMAILS` | Comma-separated allowed emails | For auth |

### Trading Configuration

Configuration can be set via environment variables (used in Cloud Run):

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_STRATEGY` | balanced | aggressive, balanced, conservative |
| `ANALYSIS_INTERVAL` | 30 | Minutes between analyses |
| `MAX_POSITION_PCT` | 0.10 | Max 10% per position |
| `MAX_DAILY_LOSS_PCT` | 0.03 | Max 3% daily loss |
| `MIN_CONFIDENCE` | 0.70 | Min 70% confidence to trade |
| `STOP_LOSS_PCT` | 0.05 | 5% stop loss |
| `TAKE_PROFIT_PCT` | 0.10 | 10% take profit |

---

## 🚀 Local Development

### 1. Clone & Setup

```bash
cd "/Users/krishnayadamakanti/Documents/Stock Trading"
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Test Connections

```bash
python src/main.py --test-connection
```

### 4. Run Backend API

```bash
python src/dashboard_app.py
# API runs on http://localhost:5000
```

### 5. Run Frontend Dashboard

```bash
cd dashboard
npm install
npm run dev
# Dashboard runs on http://localhost:5173
```

---

## ☁️ Cloud Deployment

### Services

| Service | URL | Purpose |
|---------|-----|---------|
| Backend API | trading-api-staging | Flask API + Trading Agent |
| Frontend | trading-dashboard-staging | React Dashboard |
| Scheduler | trading-agent-trigger | Triggers analysis every 30 min |

### GitHub Secrets Required

Set these in your repository's Settings → Secrets:

- `GCP_SA_KEY` - Service account JSON key
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `GEMINI_API_KEY`
- `NEWS_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `FLASK_SECRET_KEY`

### GitHub Repository Variables

- `AUTHORIZED_EMAILS` - Comma-separated list of allowed Google emails

### Deploy

```bash
# Staging - auto deploys on push to staging branch
git push origin staging

# Production - auto deploys on push to main branch
git push origin main
```

---

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/portfolio` | GET | Current portfolio & positions |
| `/api/risk` | GET | Risk status & limits |
| `/api/market` | GET | Market status (open/closed) |
| `/api/watchlist` | GET | Watchlist with prices |
| `/api/trades` | GET | Recent trade history |
| `/api/indicators` | GET | Technical indicators |
| `/api/config` | GET | Trading configuration |
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

## 🔄 Retry Logic

The LLM client includes automatic retry for transient errors:

- **Max Retries**: 3 attempts
- **Backoff**: Exponential (5s, 15s, 45s)
- **Retryable Errors**: 503, 429, UNAVAILABLE, RESOURCE_EXHAUSTED

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
| **Fibonacci** | Support/resistance levels |

---

## 💰 API Costs & Limits

### Gemini API (Free Tier)

| Limit | Value |
|-------|-------|
| Requests/day | 20 (gemini-2.5-flash) |
| Tokens/min | 15 |

**Note**: Gemini Pro subscription ($20/mo) is for the consumer app only, NOT the API. For API access, enable billing at [aistudio.google.com](https://aistudio.google.com).

### Alpaca Data

| Plan | Price | Data |
|------|-------|------|
| Basic (Free) | $0/mo | IEX real-time + 15-min delayed SIP |
| Algo Trader Plus | $99/mo | Real-time SIP + Options + Crypto |

**Current Setup**: Uses IEX (free) with yfinance fallback for complete coverage.

---

## 📋 Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "429 RESOURCE_EXHAUSTED" | Gemini quota exceeded | Wait for daily reset or enable billing |
| "503 UNAVAILABLE" | Gemini overloaded | Retry logic handles automatically |
| "No historical data" | Alpaca IEX gap | yfinance fallback handles this |
| No trades executing | LLM confidence < 70% | Normal - wait for better signals |

### Check Logs

```bash
# Cloud Run logs
gcloud logging read "resource.labels.service_name=trading-api-staging" \
  --project=samaanai-stg-1009-124126 --limit=50

# Scheduler status
gcloud scheduler jobs describe trading-agent-trigger \
  --project=samaanai-stg-1009-124126 --location=us-central1
```

---

## ⚠️ Important Notes

1. **Paper Trading Only**: Default configuration uses Alpaca paper trading (no real money)

2. **Market Hours**: Agent only trades during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)

3. **Pattern Day Trading**: If using live trading with < $25k, be aware of PDT rules

4. **No Guarantees**: AI trading is experimental. Past performance doesn't predict future results

5. **Your Responsibility**: Always monitor the agent and set appropriate risk limits

---

## 📄 License

MIT
