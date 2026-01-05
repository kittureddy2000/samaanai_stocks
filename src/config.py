"""Configuration module for the trading agent."""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)


class AlpacaConfig(BaseModel):
    """Alpaca API configuration."""
    api_key: str = os.getenv("ALPACA_API_KEY", "")
    secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    # Paper trading endpoint
    base_url: str = "https://paper-api.alpaca.markets"
    # Data endpoint
    data_url: str = "https://data.alpaca.markets"


class GeminiConfig(BaseModel):
    """Google Gemini API configuration."""
    api_key: str = os.getenv("GEMINI_API_KEY", "")
    model: str = "models/gemini-2.5-flash"
    temperature: float = 0.3  # Lower = more deterministic


class TradingConfig(BaseModel):
    """Trading parameters."""
    # Stocks to watch - 2026 Top Picks from Analyst Research
    watchlist: List[str] = [
        # === Tech Giants ===
        "AAPL",   # Apple - AI integration across devices
        "MSFT",   # Microsoft - Azure AI & Copilot
        "GOOGL",  # Alphabet - Gemini AI leader
        "AMZN",   # Amazon - AWS cloud dominance
        "META",   # Meta - AI & VR innovation
        
        # === AI & Semiconductors (2026 HOT PICKS) ===
        "NVDA",   # NVIDIA - #1 AI chip leader
        "AMD",    # AMD - GPU competitor
        "AVGO",   # Broadcom - AI networking & custom silicon
        "TSM",    # Taiwan Semi - Backbone of AI chips
        "MU",     # Micron - HBM memory for AI (Morgan Stanley top pick)
        
        # === Growth & Innovation ===
        "TSLA",   # Tesla - AI self-driving & robotics
        "NFLX",   # Netflix - Streaming leader
        "CRM",    # Salesforce - Enterprise AI
        "COIN",   # Coinbase - Crypto recovery play
        "PLTR",   # Palantir - Enterprise AI adoption
        "CRWD",   # CrowdStrike - AI cybersecurity
        
        # === Small Caps (High Growth Potential) ===
        "IONQ",   # IonQ - Quantum computing
        "SOFI",   # SoFi - Fintech disruption
        "RKLB",   # Rocket Lab - Space economy
        "AFRM",   # Affirm - Buy-now-pay-later
        "UPST",   # Upstart - AI lending
        
        # === Emerging Sector ETFs ===
        "ARKK",   # ARK Innovation ETF
        "ICLN",   # Clean Energy ETF
        "XBI",    # Biotech ETF
        "BOTZ",   # Robotics & AI ETF
        
        # === Index ETFs ===
        "SPY",    # S&P 500 ETF
        "QQQ",    # Nasdaq 100 ETF
    ]
    
    # Trading strategy: 'momentum', 'mean_reversion', 'contrarian', 'balanced'
    strategy: str = os.getenv("TRADING_STRATEGY", "balanced")
    
    # Analysis frequency in minutes (configurable via env var)
    analysis_interval_minutes: int = int(os.getenv("ANALYSIS_INTERVAL", "15"))
    
    # Risk parameters (configurable via env vars)
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "0.10"))  # Max 10% of portfolio per position
    max_daily_loss_pct: float = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.03"))  # Max 3% daily loss
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "0.70"))  # Min confidence to execute trade
    
    # Stop loss / take profit (as percentage) - configurable via env vars
    default_stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.05"))  # 5% stop loss
    default_take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.10"))  # 10% take profit
    
    # Market hours (Eastern Time)
    market_open_hour: int = 9
    market_open_minute: int = 30
    market_close_hour: int = 16
    market_close_minute: int = 0


class Config(BaseModel):
    """Main configuration."""
    alpaca: AlpacaConfig = AlpacaConfig()
    gemini: GeminiConfig = GeminiConfig()
    trading: TradingConfig = TradingConfig()
    
    # Logging
    log_level: str = "INFO"
    log_file: Path = LOGS_DIR / "trading.log"
    
    # Database
    db_path: Path = BASE_DIR / "trading_history.db"


# Global config instance
config = Config()


def validate_config() -> bool:
    """Validate that required API keys are set."""
    errors = []
    
    if not config.alpaca.api_key or config.alpaca.api_key == "your_alpaca_api_key_here":
        errors.append("ALPACA_API_KEY not set in .env")
    
    if not config.alpaca.secret_key or config.alpaca.secret_key == "your_alpaca_secret_key_here":
        errors.append("ALPACA_SECRET_KEY not set in .env")
    
    if not config.gemini.api_key or config.gemini.api_key == "your_gemini_api_key_here":
        errors.append("GEMINI_API_KEY not set in .env")
    
    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"   - {error}")
        return False
    
    return True
