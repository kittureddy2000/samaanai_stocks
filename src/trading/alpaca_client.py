"""Alpaca trading client for executing orders."""

from typing import Optional, Dict, Any, List
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus, QueryOrderStatus
from loguru import logger

import sys
sys.path.append(str(__file__).rsplit("/", 3)[0])
from config import config


class AlpacaTradingClient:
    """Client for executing trades on Alpaca."""
    
    def __init__(self):
        """Initialize the Alpaca trading client."""
        self.client = TradingClient(
            api_key=config.alpaca.api_key,
            secret_key=config.alpaca.secret_key,
            paper=True  # Always use paper trading
        )
    
    def get_account(self) -> Optional[Dict[str, Any]]:
        """Get account information.
        
        Returns:
            Account info dictionary or None
        """
        try:
            account = self.client.get_account()
            return {
                'id': str(account.id),
                'status': str(account.status),
                'cash': float(account.cash),
                'buying_power': float(account.buying_power),
                'portfolio_value': float(account.portfolio_value),
                'equity': float(account.equity),
                'last_equity': float(account.last_equity),
                'long_market_value': float(account.long_market_value),
                'short_market_value': float(account.short_market_value),
                'initial_margin': float(account.initial_margin),
                'maintenance_margin': float(account.maintenance_margin),
                'daytrade_count': account.daytrade_count,
                'pattern_day_trader': account.pattern_day_trader
            }
        except Exception as e:
            logger.error(f"Error getting account: {e}")
            return None
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all current positions.
        
        Returns:
            List of position dictionaries
        """
        try:
            positions = self.client.get_all_positions()
            return [
                {
                    'symbol': pos.symbol,
                    'qty': float(pos.qty),
                    'side': str(pos.side),
                    'avg_entry_price': float(pos.avg_entry_price),
                    'current_price': float(pos.current_price),
                    'market_value': float(pos.market_value),
                    'cost_basis': float(pos.cost_basis),
                    'unrealized_pl': float(pos.unrealized_pl),
                    'unrealized_plpc': float(pos.unrealized_plpc),
                    'unrealized_intraday_pl': float(pos.unrealized_intraday_pl),
                    'unrealized_intraday_plpc': float(pos.unrealized_intraday_plpc),
                    'change_today': float(pos.change_today)
                }
                for pos in positions
            ]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for a specific symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Position dictionary or None
        """
        try:
            pos = self.client.get_open_position(symbol)
            return {
                'symbol': pos.symbol,
                'qty': float(pos.qty),
                'side': str(pos.side),
                'avg_entry_price': float(pos.avg_entry_price),
                'current_price': float(pos.current_price),
                'market_value': float(pos.market_value),
                'unrealized_pl': float(pos.unrealized_pl),
                'unrealized_plpc': float(pos.unrealized_plpc)
            }
        except Exception as e:
            logger.debug(f"No position for {symbol}: {e}")
            return None
    
    def place_market_order(
        self,
        symbol: str,
        qty: int,
        side: str  # 'buy' or 'sell'
    ) -> Optional[Dict[str, Any]]:
        """Place a market order.
        
        Args:
            symbol: Stock ticker symbol
            qty: Number of shares
            side: 'buy' or 'sell'
            
        Returns:
            Order info dictionary or None
        """
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
    
    def place_limit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float
    ) -> Optional[Dict[str, Any]]:
        """Place a limit order.
        
        Args:
            symbol: Stock ticker symbol
            qty: Number of shares
            side: 'buy' or 'sell'
            limit_price: Limit price
            
        Returns:
            Order info dictionary or None
        """
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
    
    def _format_order(self, order) -> Dict[str, Any]:
        """Format order response into dictionary.
        
        Args:
            order: Alpaca order object
            
        Returns:
            Formatted dictionary
        """
        return {
            'id': str(order.id),
            'client_order_id': str(order.client_order_id),
            'symbol': order.symbol,
            'qty': float(order.qty) if order.qty else 0,
            'filled_qty': float(order.filled_qty) if order.filled_qty else 0,
            'side': str(order.side),
            'type': str(order.type),
            'status': str(order.status),
            'limit_price': float(order.limit_price) if order.limit_price else None,
            'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
            'created_at': str(order.created_at) if order.created_at else None,
            'submitted_at': str(order.submitted_at) if order.submitted_at else None
        }
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order info dictionary or None
        """
        try:
            order = self.client.get_order_by_id(order_id)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open orders.
        
        Returns:
            List of open order dictionaries
        """
        try:
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self.client.get_orders(request)
            return [self._format_order(order) for order in orders]
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders.
        
        Returns:
            True if all cancelled successfully
        """
        try:
            self.client.cancel_orders()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return False
    
    def close_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Close a position (sell all shares).
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Order info dictionary or None
        """
        try:
            order = self.client.close_position(symbol)
            logger.info(f"Position closed: {symbol}")
            return self._format_order(order)
        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")
            return None
    
    def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all positions.
        
        Returns:
            List of order dictionaries
        """
        try:
            orders = self.client.close_all_positions()
            logger.info("All positions closed")
            return [self._format_order(order) for order in orders]
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return []
    
    def is_market_open(self) -> bool:
        """Check if the market is currently open.
        
        Returns:
            True if market is open
        """
        try:
            clock = self.client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False
    
    def get_market_hours(self) -> Optional[Dict[str, Any]]:
        """Get today's market hours.
        
        Returns:
            Dictionary with market timing info
        """
        try:
            clock = self.client.get_clock()
            return {
                'is_open': clock.is_open,
                'next_open': str(clock.next_open),
                'next_close': str(clock.next_close)
            }
        except Exception as e:
            logger.error(f"Error getting market hours: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test the trading API connection.
        
        Returns:
            True if connection successful
        """
        try:
            account = self.get_account()
            if account:
                logger.info(f"✅ Alpaca trading connection OK")
                logger.info(f"   Account: {account['id']}")
                logger.info(f"   Cash: ${account['cash']:,.2f}")
                logger.info(f"   Portfolio Value: ${account['portfolio_value']:,.2f}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Alpaca trading connection failed: {e}")
            return False
