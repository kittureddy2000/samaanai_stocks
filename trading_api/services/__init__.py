"""Trading services package.

This package provides lazy imports for the existing trading logic
from the src/ directory, adapted for use with Django.

Imports are done lazily to avoid issues during collectstatic at build time.
"""

import sys
import os

# Add the project root to path to access src modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Also add src directory directly for imports that expect 'config' at root
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


# Cached broker instance
# Force rebuild 2
_broker_instance = None


def get_broker():
    """Get the configured broker instance (Alpaca or IBKR).
    
    Uses the BROKER_TYPE environment variable to determine which broker to use.
    Returns a cached instance to avoid reconnection overhead.
    """
    global _broker_instance
    if _broker_instance is None:
        print("DEBUG: _broker_instance is None, creating new broker")
        from src.trading.broker_factory import get_broker as _get_broker
        _broker_instance = _get_broker()
    return _broker_instance


def get_broker_name():
    """Get the name of the broker (always 'ibkr').

    Returns:
        Broker name string
    """
    return 'ibkr'


def get_risk_manager():
    """Lazily import RiskManager."""
    from src.trading.risk_controls import RiskManager
    return RiskManager


def get_order_manager():
    """Lazily import OrderManager."""
    from src.trading.order_manager import OrderManager
    return OrderManager


def get_portfolio_tracker():
    """Lazily import PortfolioTracker."""
    from src.trading.portfolio import PortfolioTracker
    return PortfolioTracker


def get_data_aggregator():
    """Lazily import DataAggregator."""
    from src.data.data_aggregator import DataAggregator
    return DataAggregator


def get_market_data_client():
    """Lazily import MarketDataClient."""
    from src.data.market_data import MarketDataClient
    return MarketDataClient


def get_technical_indicators():
    """Lazily import TechnicalIndicators."""
    from src.data.technical_indicators import TechnicalIndicators
    return TechnicalIndicators


def get_trading_analyst():
    """Lazily import TradingAnalyst."""
    from src.llm.analyst import TradingAnalyst
    return TradingAnalyst


def get_llm_client():
    """Lazily import LLMClient."""
    from src.llm.llm_client import LLMClient
    return LLMClient


def get_slack():
    """Lazily import slack utilities."""
    from src.utils.slack import slack, notify_trade
    return slack, notify_trade


__all__ = [
    'get_broker',
    'get_broker_name',
    'get_risk_manager',
    'get_order_manager',
    'get_portfolio_tracker',
    'get_data_aggregator',
    'get_market_data_client',
    'get_technical_indicators',
    'get_trading_analyst',
    'get_llm_client',
    'get_slack',
]

