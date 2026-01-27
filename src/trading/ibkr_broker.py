"""Interactive Brokers broker implementation.

Implements the BaseBroker interface for Interactive Brokers (IBKR) trading
using the ib_insync library.
"""

from typing import Optional, List
from datetime import datetime, timezone
from loguru import logger
import os
import asyncio

# Imports moved to __init__ to handle asyncio loop creation in threads


import asyncio
import sys

# specific fix for cloud run/django env
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

try:
    from ib_insync import IB, Stock, MarketOrder, LimitOrder
    IB_INSYNC_AVAILABLE = True
except ImportError:
    IB_INSYNC_AVAILABLE = False
    logger.warning("ib_insync not installed. IBKR trading will not be available.")

from src.trading.broker_base import BaseBroker, AccountInfo, Position, Order


class IBKRBroker(BaseBroker):
    """Interactive Brokers implementation of BaseBroker interface.

    Requires IB Gateway or TWS to be running and accessible.
    """

    def _ensure_event_loop(self):
        """Ensure an event loop exists in the current thread."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

    def __init__(self):
        """Initialize the IBKR broker."""
        # Late import to ensure event loop exists in this thread
        try:
            self._ensure_event_loop()

            import ib_insync
            self.ib_module = ib_insync
            self.IB = ib_insync.IB
            self.Stock = ib_insync.Stock
            self.MarketOrder = ib_insync.MarketOrder
            self.LimitOrder = ib_insync.LimitOrder
        except ImportError:
            logger.warning("ib_insync not installed. IBKR trading will not be available.")
            raise ImportError("ib_insync is required for IBKR trading")

        self.ib = self.IB()
        self.host = os.environ.get('IBKR_GATEWAY_HOST', '127.0.0.1')
        self.port = int(os.environ.get('IBKR_GATEWAY_PORT', '4002'))  # 4001=live, 4002=paper
        # Use random client ID to avoid conflicts between multiple Cloud Run instances
        # Each instance gets a unique client ID in range 100-999 to prevent
        # "Error 326: client id is already in use" errors
        import random
        base_client_id = int(os.environ.get('IBKR_CLIENT_ID', '1'))
        if base_client_id == 1:
            # Generate random client ID if using default
            self.client_id = random.randint(100, 999)
        else:
            self.client_id = base_client_id
        self._connected = False

        logger.info(f"IBKRBroker initialized: host={self.host}, port={self.port}, client_id={self.client_id}")
    
    @property
    def name(self) -> str:
        """Return the broker name."""
        return "Interactive Brokers"
    
    def connect(self) -> bool:
        """Connect to IB Gateway."""
        try:
            self._ensure_event_loop()
            if self._connected and self.ib.isConnected():
                return True

            logger.info(f"Attempting to connect to IBKR Gateway at {self.host}:{self.port} (Client ID: {self.client_id})...")
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=10)
            self._connected = True
            logger.info(f"✅ Connected to IBKR Gateway at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to IBKR: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from IB Gateway."""
        if self._connected:
            try:
                self.ib.disconnect()
            except:
                pass
            self._connected = False
            logger.info("Disconnected from IBKR Gateway")
    
    def test_connection(self) -> bool:
        """Test the broker connection."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                if not self.connect():
                    return False
            
            account = self.get_account()
            if account:
                logger.info(f"✅ {self.name} connection OK")
                logger.info(f"   Account: {account.id}")
                logger.info(f"   Cash: ${account.cash:,.2f}")
                logger.info(f"   Portfolio Value: ${account.portfolio_value:,.2f}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ {self.name} connection test failed: {e}")
            return False
    
    def get_account(self) -> Optional[AccountInfo]:
        """Get account information from IBKR."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                self.connect()
            
            account_values = self.ib.accountSummary()
            
            # Parse account values into a dictionary
            values = {}
            account_id = ""
            for av in account_values:
                if av.currency == 'USD':
                    try:
                        values[av.tag] = float(av.value)
                    except ValueError:
                        values[av.tag] = av.value
                if not account_id and av.account:
                    account_id = av.account
            
            return AccountInfo(
                id=account_id,
                cash=values.get('TotalCashValue', 0),
                buying_power=values.get('BuyingPower', 0),
                portfolio_value=values.get('NetLiquidation', 0),
                equity=values.get('EquityWithLoanValue', 0),
                last_equity=values.get('NetLiquidation', 0)
            )
        except Exception as e:
            logger.error(f"Error getting IBKR account: {e}")
            return None
    
    def get_positions(self) -> List[Position]:
        """Get all open positions from IBKR."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                self.connect()
            
            positions = self.ib.positions()
            result = []
            
            for pos in positions:
                current_price = self._get_current_price(pos.contract.symbol)
                market_value = pos.position * current_price
                cost_basis = pos.position * pos.avgCost
                unrealized_pl = market_value - cost_basis
                unrealized_plpc = (unrealized_pl / cost_basis) if cost_basis != 0 else 0
                
                result.append(Position(
                    symbol=pos.contract.symbol,
                    qty=pos.position,
                    avg_entry_price=pos.avgCost,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pl=unrealized_pl,
                    unrealized_plpc=unrealized_plpc
                ))
            
            return result
        except Exception as e:
            logger.error(f"Error getting IBKR positions: {e}")
            return []
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        positions = self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None
    
    def place_market_order(self, symbol: str, qty: int, side: str) -> Optional[Order]:
        """Place a market order on IBKR."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                self.connect()
            
            contract = self.Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            action = 'BUY' if side.lower() == 'buy' else 'SELL'
            order = self.MarketOrder(action, qty)
            
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)  # Wait for order to be processed
            
            logger.info(f"Market order placed: {action} {qty} {symbol}")
            
            return Order(
                id=str(trade.order.orderId),
                symbol=symbol,
                side=side.lower(),
                qty=qty,
                order_type='market',
                status=trade.orderStatus.status.lower(),
                filled_qty=trade.orderStatus.filled,
                filled_price=trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice else None,
                created_at=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Error placing IBKR market order: {e}")
            return None
    
    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Optional[Order]:
        """Place a limit order on IBKR."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                self.connect()
            
            contract = self.Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            action = 'BUY' if side.lower() == 'buy' else 'SELL'
            order = self.LimitOrder(action, qty, limit_price)
            
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)
            
            logger.info(f"Limit order placed: {action} {qty} {symbol} @ ${limit_price}")
            
            return Order(
                id=str(trade.order.orderId),
                symbol=symbol,
                side=side.lower(),
                qty=qty,
                order_type='limit',
                limit_price=limit_price,
                status=trade.orderStatus.status.lower(),
                created_at=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Error placing IBKR limit order: {e}")
            return None
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order status by ID."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                self.connect()
            
            # Find the trade by order ID
            for trade in self.ib.trades():
                if str(trade.order.orderId) == order_id:
                    return Order(
                        id=str(trade.order.orderId),
                        symbol=trade.contract.symbol,
                        side=trade.order.action.lower(),
                        qty=trade.order.totalQuantity,
                        order_type=trade.order.orderType.lower(),
                        status=trade.orderStatus.status.lower(),
                        limit_price=trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else None,
                        filled_qty=trade.orderStatus.filled,
                        filled_price=trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice else None
                    )
            return None
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None
    
    def get_orders_history(self, limit: int = 50) -> List[Order]:
        """Get recent order history from IBKR."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                self.connect()
            
            trades = self.ib.trades()
            orders = []
            
            for trade in trades[:limit]:
                orders.append(Order(
                    id=str(trade.order.orderId),
                    symbol=trade.contract.symbol,
                    side=trade.order.action.lower(),
                    qty=trade.order.totalQuantity,
                    order_type=trade.order.orderType.lower(),
                    status=trade.orderStatus.status.lower(),
                    limit_price=trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else None,
                    filled_qty=trade.orderStatus.filled,
                    filled_price=trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice else None
                ))
            
            return orders
        except Exception as e:
            logger.error(f"Error getting IBKR order history: {e}")
            return []
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            self._ensure_event_loop()
            if not self._connected:
                self.connect()
            
            for trade in self.ib.trades():
                if str(trade.order.orderId) == order_id:
                    self.ib.cancelOrder(trade.order)
                    logger.info(f"Order {order_id} cancelled")
                    return True
            
            logger.warning(f"Order {order_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def is_market_open(self) -> bool:
        """Check if US stock market is open."""
        try:
            now = datetime.now(timezone.utc)
            # Simple check: M-F, 14:30 - 21:00 UTC (9:30 AM - 4:00 PM ET)
            # For production, use IBKR's contract details for accurate trading hours
            if now.weekday() >= 5:  # Saturday or Sunday
                return False
            
            hour = now.hour
            minute = now.minute
            
            # Market opens at 14:30 UTC and closes at 21:00 UTC
            market_open = (hour == 14 and minute >= 30) or (15 <= hour < 21)
            return market_open
        except:
            return False
    
    def get_market_hours(self) -> dict:
        """Get market hours information."""
        is_open = self.is_market_open()
        now = datetime.now(timezone.utc)
        
        # Calculate next open/close (simplified)
        if is_open:
            next_close = now.replace(hour=21, minute=0, second=0, microsecond=0)
            next_open = "Market is open"
        else:
            # Find next trading day
            days_until_open = 0
            if now.weekday() >= 4:  # Friday after close, Saturday, or Sunday
                days_until_open = 7 - now.weekday()
            elif now.hour >= 21:
                days_until_open = 1
            
            from datetime import timedelta
            next_open_date = now + timedelta(days=days_until_open)
            next_open = next_open_date.replace(hour=14, minute=30, second=0, microsecond=0)
            next_close = "Market is closed"
        
        return {
            'is_open': is_open,
            'next_open': str(next_open) if isinstance(next_open, datetime) else next_open,
            'next_close': str(next_close) if isinstance(next_close, datetime) else next_close
        }
    
    def _get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol using IBKR market data."""
        try:
            contract = self.Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(2)  # Wait for data
            
            price = ticker.last or ticker.close or 0
            self.ib.cancelMktData(contract)  # Clean up
            return price
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return 0
