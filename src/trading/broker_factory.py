"""Broker factory for IBKR trading.

Provides a factory function to instantiate the IBKR broker.
"""

import os
from loguru import logger
from src.trading.broker_base import BaseBroker


class BrokerConnectionError(Exception):
    """Raised when broker connection fails."""
    pass


def get_broker() -> BaseBroker:
    """Factory function to get the IBKR broker.

    Returns:
        IBKRBroker instance

    Raises:
        BrokerConnectionError: If IBKR connection fails
    """
    broker_type = os.environ.get('BROKER_TYPE', 'ibkr').lower()

    logger.info(f"Initializing broker: {broker_type}")

    if broker_type != 'ibkr':
        logger.warning(f"BROKER_TYPE={broker_type} is not supported. Only 'ibkr' is available.")

    try:
        from src.trading.ibkr_broker import IBKRBroker
        broker = IBKRBroker()

        # IBKR requires explicit connection
        if not broker.connect():
            error_msg = (
                f"Failed to connect to IBKR Gateway at "
                f"{os.environ.get('IBKR_GATEWAY_HOST', '127.0.0.1')}:"
                f"{os.environ.get('IBKR_GATEWAY_PORT', '4004')}. "
                "Please ensure IB Gateway is running and accessible."
            )
            logger.error(error_msg)
            raise BrokerConnectionError(error_msg)

        logger.info("✅ IBKR broker connected successfully")
        return broker

    except ImportError as e:
        error_msg = f"Failed to import IBKRBroker: {e}. Ensure ib_insync is installed."
        logger.error(error_msg)
        raise BrokerConnectionError(error_msg)
    except BrokerConnectionError:
        raise
    except Exception as e:
        import traceback
        logger.error(f"IBKR initialization failed: {e}")
        logger.error(traceback.format_exc())
        raise BrokerConnectionError(f"IBKR initialization failed: {e}")


def get_broker_name() -> str:
    """Get the name of the broker.

    Returns:
        Broker name string (always 'ibkr')
    """
    return 'ibkr'
