"""Trading services package.

This package provides lazy imports for the existing trading logic
from the src/ directory, adapted for use with Django.

Imports are done lazily to avoid issues during collectstatic at build time.
"""

import sys
import os
import time
import logging

logger = logging.getLogger(__name__)

# Add the project root to path to access src modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Also add src directory directly for imports that expect 'config' at root
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


# Cached broker instance with health checking
_broker_instance = None
_broker_last_check = 0
_HEALTH_CHECK_INTERVAL = 60  # seconds between health checks


def get_broker():
    """Get the configured broker instance with health checking.

    Returns a cached instance, but validates it is still connected.
    If connection is lost, invalidates cache and creates a new instance.

    Uses the BROKER_TYPE environment variable to determine which broker to use.
    """
    global _broker_instance, _broker_last_check

    now = time.time()

    # Return cached instance if recently validated
    if _broker_instance is not None:
        if (now - _broker_last_check) < _HEALTH_CHECK_INTERVAL:
            logger.debug("Returning cached broker instance (recently validated)")
            return _broker_instance

        # Periodic health check
        try:
            if _broker_instance.ib.isConnected():
                _broker_last_check = now
                logger.debug("Broker health check passed, reusing cached instance")
                return _broker_instance
            else:
                logger.warning(
                    "Broker health check failed: isConnected=False, "
                    "invalidating cached instance"
                )
                _broker_instance = None
        except Exception as e:
            logger.warning(f"Broker health check exception: {e}, invalidating cached instance")
            _broker_instance = None

    # Create new instance
    logger.info("Creating new broker instance via factory")
    from src.trading.broker_factory import get_broker as _get_broker
    _broker_instance = _get_broker()
    _broker_last_check = now
    logger.info("New broker instance created and cached")
    return _broker_instance


def invalidate_broker():
    """Explicitly invalidate the cached broker instance.

    Call this when the broker connection is known to be broken,
    e.g., after catching a connection error in a view.
    """
    global _broker_instance, _broker_last_check
    if _broker_instance is not None:
        try:
            _broker_instance.disconnect()
        except Exception:
            pass
        logger.info("Broker instance invalidated and disconnected")
    else:
        logger.debug("invalidate_broker called but no instance was cached")
    _broker_instance = None
    _broker_last_check = 0


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
    'invalidate_broker',
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
