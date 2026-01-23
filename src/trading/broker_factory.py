"""Broker factory for multi-broker support.

Provides a factory function to instantiate the appropriate broker
based on environment configuration.
"""

import os
from loguru import logger
from src.trading.broker_base import BaseBroker


def get_broker() -> BaseBroker:
    """Factory function to get the configured broker.
    
    Uses the BROKER_TYPE environment variable to determine which broker to use:
    - 'alpaca' (default): Use Alpaca paper trading
    - 'ibkr': Use Interactive Brokers
    
    Returns:
        BaseBroker implementation instance
    """
    broker_type = os.environ.get('BROKER_TYPE', 'alpaca').lower()
    
    logger.info(f"Initializing broker: {broker_type}")
    
    if broker_type == 'ibkr':
        from src.trading.ibkr_broker import IBKRBroker
        broker = IBKRBroker()
        # IBKR requires explicit connection
        if not broker.connect():
            logger.error("Failed to connect to IBKR Gateway. Falling back to Alpaca.")
            from src.trading.alpaca_broker import AlpacaBroker
            return AlpacaBroker()
        return broker
    else:
        # Default to Alpaca
        from src.trading.alpaca_broker import AlpacaBroker
        return AlpacaBroker()


def get_broker_name() -> str:
    """Get the name of the currently configured broker.
    
    Returns:
        Broker name string
    """
    broker_type = os.environ.get('BROKER_TYPE', 'alpaca').lower()
    if broker_type == 'ibkr':
        return 'Interactive Brokers'
    return 'Alpaca'
