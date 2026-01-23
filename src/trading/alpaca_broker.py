"""Alpaca broker implementation.

Implements the BaseBroker interface for Alpaca trading.
"""

from typing import Optional, List
from datetime import datetime
from loguru import logger

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

import sys
import os

# Add the project root and src to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SRC_DIR = os.path.join(_PROJECT_ROOT, 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from config import config
from src.trading.broker_base import BaseBroker, AccountInfo, Position, Order


class AlpacaBroker(BaseBroker):
    """Alpaca implementation of BaseBroker interface."""
    
    def __init__(self):
        """Initialize the Alpaca broker."""
        api_key = config.alpaca.api_key
        secret_key = config.alpaca.secret_key
        
        logger.info(f"AlpacaBroker: API Key present: {bool(api_key)}")
        
        self.client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=True  # Always use paper trading
        )
        self._connected = True
    
    @property
    def name(self) -> str:
        """Return the broker name."""
        return "Alpaca"
    
    def connect(self) -> bool:
        """Alpaca doesn't require explicit connection."""
        self._connected = True
        return True
    
    def disconnect(self) -> None:
        """Alpaca doesn't require explicit disconnection."""
        self._connected = False
    
    def test_connection(self) -> bool:
        """Test the broker connection."""
        try:
            account = self.get_account()
            if account:
                logger.info(f"✅ {self.name} connection OK")
                logger.info(f"   Cash: ${account.cash:,.2f}")
                logger.info(f"   Portfolio Value: ${account.portfolio_value:,.2f}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ {self.name} connection failed: {e}")
            return False
    
    def get_account(self) -> Optional[AccountInfo]:
        """Get account information."""
        try:
            account = self.client.get_account()
            return AccountInfo(
                id=str(account.id),
                cash=float(account.cash),
                buying_power=float(account.buying_power),
                portfolio_value=float(account.portfolio_value),
                equity=float(account.equity),
                last_equity=float(account.last_equity)
            )
        except Exception as e:
            logger.error(f"Error getting account: {e}")
            return None
    
    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        try:
            positions = self.client.get_all_positions()
            return [
                Position(
                    symbol=pos.symbol,
                    qty=float(pos.qty),
                    avg_entry_price=float(pos.avg_entry_price),
                    current_price=float(pos.current_price),
                    market_value=float(pos.market_value),
                    unrealized_pl=float(pos.unrealized_pl),
                    unrealized_plpc=float(pos.unrealized_plpc)
                )
                for pos in positions
            ]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        try:
            pos = self.client.get_open_position(symbol)
            return Position(
                symbol=pos.symbol,
                qty=float(pos.qty),
                avg_entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                market_value=float(pos.market_value),
                unrealized_pl=float(pos.unrealized_pl),
                unrealized_plpc=float(pos.unrealized_plpc)
            )
        except Exception as e:
            logger.debug(f"No position for {symbol}: {e}")
            return None
    
    def place_market_order(self, symbol: str, qty: int, side: str) -> Optional[Order]:
        """Place a market order."""
        try:
            order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
            
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY
            )
            
            order = self.client.submit_order(request)
            logger.info(f"Market order placed: {side.upper()} {qty} {symbol}")
            
            return self._format_order(order)
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return None
    
    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Optional[Order]:
        """Place a limit order."""
        try:
            order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
            
            request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price
            )
            
            order = self.client.submit_order(request)
            logger.info(f"Limit order placed: {side.upper()} {qty} {symbol} @ ${limit_price}")
            
            return self._format_order(order)
            
        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return None
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order status by ID."""
        try:
            order = self.client.get_order_by_id(order_id)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None
    
    def get_orders_history(self, limit: int = 50) -> List[Order]:
        """Get recent order history."""
        try:
            request = GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                limit=limit
            )
            orders = self.client.get_orders(request)
            return [self._format_order(order) for order in orders]
        except Exception as e:
            logger.error(f"Error getting order history: {e}")
            return []
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def is_market_open(self) -> bool:
        """Check if market is open."""
        try:
            clock = self.client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False
    
    def get_market_hours(self) -> dict:
        """Get market hours information."""
        try:
            clock = self.client.get_clock()
            return {
                'is_open': clock.is_open,
                'next_open': str(clock.next_open),
                'next_close': str(clock.next_close)
            }
        except Exception as e:
            logger.error(f"Error getting market hours: {e}")
            return {'is_open': False, 'next_open': 'Unknown', 'next_close': 'Unknown'}
    
    def _format_order(self, order) -> Order:
        """Format Alpaca order to standardized Order object."""
        created_at = None
        if order.created_at:
            created_at = order.created_at if isinstance(order.created_at, datetime) else datetime.fromisoformat(str(order.created_at).replace('Z', '+00:00'))
        
        return Order(
            id=str(order.id),
            symbol=order.symbol,
            side=str(order.side).lower().replace('ordersid.', ''),
            qty=float(order.qty) if order.qty else 0,
            order_type=str(order.type).lower().replace('ordertype.', ''),
            status=str(order.status).lower().replace('orderstatus.', ''),
            limit_price=float(order.limit_price) if order.limit_price else None,
            filled_qty=float(order.filled_qty) if order.filled_qty else 0,
            filled_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            created_at=created_at
        )
    
    # Additional Alpaca-specific methods (not part of BaseBroker interface)
    
    def close_position(self, symbol: str) -> Optional[Order]:
        """Close a position (sell all shares)."""
        try:
            order = self.client.close_position(symbol)
            logger.info(f"Position closed: {symbol}")
            return self._format_order(order)
        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")
            return None
    
    def close_all_positions(self) -> List[Order]:
        """Close all positions."""
        try:
            orders = self.client.close_all_positions()
            logger.info("All positions closed")
            return [self._format_order(order) for order in orders]
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return []
    
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self.client.cancel_orders()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return False
