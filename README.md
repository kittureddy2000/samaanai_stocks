# LLM Trading Agent

An AI-powered stock trading agent that uses **Google Gemini** to analyze market data and make automated trading decisions on Alpaca's paper trading platform.

## Features

- 🤖 **LLM-Powered Analysis**: Uses Google Gemini to analyze market conditions and make trading decisions
- 📊 **Technical Indicators**: RSI, MACD, Moving Averages, Bollinger Bands
- 🛡️ **Risk Management**: Position sizing, stop-loss, daily loss limits
- 📈 **Paper Trading**: Safe testing with Alpaca's paper trading environment
- 📝 **Full Logging**: Every decision is logged with reasoning
- 🗄️ **Trade History**: SQLite database stores all trades and portfolio snapshots

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM TRADING AGENT                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        ORCHESTRATOR (main.py)                        │   │
│  │                     Runs every 15 minutes                            │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│         ┌───────────────────────┼───────────────────────┐                  │
│         ▼                       ▼                       ▼                  │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐            │
│  │   DATA      │        │   GEMINI    │        │   EXECUTION │            │
│  │   LAYER     │───────▶│   BRAIN     │───────▶│   ENGINE    │            │
│  └─────────────┘        └─────────────┘        └─────────────┘            │
│         │                      │                      │                    │
│         ▼                      ▼                      ▼                    │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐            │
│  │ • Market    │        │ • Analysis  │        │ • Order     │            │
│  │   Data      │        │ • Strategy  │        │   Manager   │            │
│  │ • Technical │        │ • Risk Eval │        │ • Portfolio │            │
│  │   Indicators│        │ • Decisions │        │ • Risk Ctrl │            │
│  └─────────────┘        └─────────────┘        └─────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │        EXTERNAL APIs          │
                    ├───────────────────────────────┤
                    │ • Alpaca (Market Data/Trading)│
                    │ • Google Gemini (LLM)         │
                    └───────────────────────────────┘
```

---

## Project Structure

```
Stock Trading/
├── src/
│   ├── main.py              # Entry point, CLI, and scheduling
│   ├── config.py            # Configuration and environment variables
│   │
│   ├── data/                # DATA LAYER
│   │   ├── market_data.py       # Alpaca market data client
│   │   ├── technical_indicators.py  # RSI, MACD, MAs, Bollinger Bands
│   │   └── data_aggregator.py   # Combines data for LLM consumption
│   │
│   ├── llm/                 # LLM BRAIN
│   │   ├── prompts.py           # System & user prompts for trading
│   │   ├── llm_client.py        # Google Gemini API integration
│   │   └── analyst.py           # Orchestrates analysis & recommendations
│   │
│   ├── trading/             # EXECUTION ENGINE
│   │   ├── alpaca_client.py     # Alpaca trading API wrapper
│   │   ├── order_manager.py     # Order execution logic
│   │   ├── portfolio.py         # Portfolio tracking & P&L
│   │   └── risk_controls.py     # Position limits, loss limits, kill switch
│   │
│   └── utils/               # UTILITIES
│       ├── logger.py            # Logging configuration
│       └── database.py          # SQLite trade history
│
├── logs/                    # Log files (auto-created)
├── .env                     # API keys (create from .env.example)
├── .env.example             # API key template
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

## How It Works

### Trading Loop Flow

```
┌──────────┐
│  START   │  (Every 15 min during market hours)
└────┬─────┘
     │
     ▼
┌─────────────────────┐
│ 1. GATHER DATA      │  Fetch prices, calculate RSI, MACD, etc.
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. BUILD CONTEXT    │  Format data for LLM, include portfolio state
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. LLM ANALYSIS     │  Send to Gemini, get structured JSON response
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 4. VALIDATE TRADES  │  Check confidence, risk limits, position sizes
└──────────┬──────────┘
           │ Pass
           ▼
┌─────────────────────┐
│ 5. EXECUTE ORDERS   │  Place orders via Alpaca API
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 6. LOG & NOTIFY     │  Record to database, update logs
└──────────┬──────────┘
           │
           ▼
     ┌──────────┐
     │   END    │ ──▶ Wait for next cycle
     └──────────┘
```

---

## Quick Start

### 1. Set Up API Keys

You need two API keys:

| Service | Purpose | Where to Get |
|---------|---------|--------------|
| **Alpaca** | Market data & trading | [app.alpaca.markets](https://app.alpaca.markets) → API (left sidebar) |
| **Gemini** | LLM analysis | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

### 2. Configure Environment

```bash
cd "/Users/krishnayadamakanti/Documents/Stock Trading"
cp .env.example .env   # Already done!
```

Edit `.env` and add your keys:
```
ALPACA_API_KEY=PKXXXXXXXXXXXXXXXX
ALPACA_SECRET_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GEMINI_API_KEY=AIzaXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### 3. Activate Environment & Test

```bash
source venv/bin/activate
python src/main.py --test-connection
```

Expected output:
```
✅ Alpaca trading connection OK
✅ Alpaca data connection OK (AAPL: $XXX.XX)
✅ Gemini connection OK
```

### 4. Run the Agent

```bash
# Run single analysis (for testing)
python src/main.py --single-run

# Start continuous trading
python src/main.py
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `python src/main.py` | Start continuous trading (every 15 min) |
| `python src/main.py --test-connection` | Test API connections |
| `python src/main.py --single-run` | Run one analysis cycle |
| `python src/main.py --portfolio` | View current portfolio & risk status |
| `python src/main.py --history` | View recent trade history |

---

## Risk Management

The agent has multiple safety guardrails:

| Control | Default | Description |
|---------|---------|-------------|
| **Max Position Size** | 10% | No single stock can exceed 10% of portfolio |
| **Max Daily Loss** | 3% | Trading halts if daily losses exceed 3% |
| **Min Confidence** | 70% | Only executes trades with >70% LLM confidence |
| **Stop Loss** | 5% | Default stop-loss per trade |
| **Take Profit** | 10% | Default take-profit target |
| **Kill Switch** | Manual | Emergency stop for all trading |

---

## Configuration

Edit `src/config.py` to customize:

```python
class TradingConfig:
    watchlist = ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "SPY", "QQQ"]
    analysis_interval_minutes = 15
    max_position_pct = 0.10      # 10%
    max_daily_loss_pct = 0.03    # 3%
    min_confidence = 0.70        # 70%
    default_stop_loss_pct = 0.05 # 5%
    default_take_profit_pct = 0.10  # 10%
```

---

## Technical Indicators Used

| Indicator | Purpose |
|-----------|---------|
| **RSI (14)** | Overbought/oversold detection |
| **MACD** | Trend direction & momentum |
| **SMA (20, 50)** | Trend confirmation |
| **EMA (12, 26)** | Short-term trend |
| **Bollinger Bands** | Volatility & price extremes |
| **Volume Analysis** | Confirm price movements |

---

## Logs & Database

- **Trading logs**: `logs/trading.log` (all activity)
- **Trade-only logs**: `logs/trades.log` (executed trades)
- **Error logs**: `logs/errors.log` (errors only)
- **Trade database**: `trading_history.db` (SQLite)

---

## Important Notes

⚠️ **Paper Trading Only**: This agent is configured for paper trading by default. No real money is used.

⚠️ **Market Hours**: The agent only trades during market hours (9:30 AM - 4:00 PM ET, Mon-Fri).

⚠️ **Pattern Day Trading**: If you make 4+ day trades in 5 days with under $25k, PDT rules apply.

⚠️ **No Guarantees**: AI trading is experimental. Past performance doesn't predict future results.

---

## License

MIT
