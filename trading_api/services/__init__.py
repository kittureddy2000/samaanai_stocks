"""Trading services package.

This package provides wrapper imports for the existing trading logic
from the src/ directory, adapted for use with Django.
"""

# Import services from existing src directory
# These imports maintain backward compatibility while transitioning to Django

import sys
import os

# Add the project root to path to access src modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Re-export services
from src.trading.alpaca_client import AlpacaTradingClient
from src.trading.risk_controls import RiskManager
from src.trading.order_manager import OrderManager
from src.trading.portfolio import PortfolioTracker
from src.data.data_aggregator import DataAggregator
from src.data.market_data import MarketDataClient
from src.data.technical_indicators import TechnicalIndicators
from src.llm.analyst import TradingAnalyst
from src.llm.llm_client import LLMClient
from src.utils.slack import slack, notify_trade

__all__ = [
    'AlpacaTradingClient',
    'RiskManager',
    'OrderManager',
    'PortfolioTracker',
    'DataAggregator',
    'MarketDataClient',
    'TechnicalIndicators',
    'TradingAnalyst',
    'LLMClient',
    'slack',
    'notify_trade',
]
