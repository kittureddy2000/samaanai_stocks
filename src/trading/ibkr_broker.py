"""Interactive Brokers broker implementation.

Implements the BaseBroker interface for Interactive Brokers (IBKR) trading
using the ib_insync library.
"""

from typing import Optional, List
from datetime import datetime, timezone
from loguru import logger
import os
import time
import asyncio
import sys
import traceback

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
        start = time.time()
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

        elapsed = time.time() - start
        logger.info(
            f"IBKR broker initialized in {elapsed:.3f}s: "
            f"host={self.host}, port={self.port}, client_id={self.client_id}"
        )

    @property
    def name(self) -> str:
        """Return the broker name."""
        return "Interactive Brokers"

    def connect(self) -> bool:
        """Connect to IB Gateway (single attempt)."""
        try:
            self._ensure_event_loop()
            if self._connected and self.ib.isConnected():
                logger.debug("IBKR already connected, reusing existing connection")
                return True

            logger.info(
                f"IBKR connecting: host={self.host}, port={self.port}, "
                f"client_id={self.client_id}"
            )
            start = time.time()
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=10)
            elapsed = time.time() - start
            self._connected = True
            logger.info(f"IBKR connected successfully in {elapsed:.2f}s")
            return True
        except Exception as e:
            logger.error(
                f"IBKR connect failed to {self.host}:{self.port}: "
                f"{type(e).__name__}: {e}"
            )
            logger.debug(traceback.format_exc())
            self._connected = False
            return False

    def connect_with_retry(self, max_retries: int = 3) -> bool:
        """Connect to IB Gateway with exponential backoff retry.

        Args:
            max_retries: Maximum number of connection attempts.

        Returns:
            True if connection successful, False after all retries exhausted.
        """
        for attempt in range(max_retries):
            if attempt > 0:
                wait_time = 2 * (2 ** attempt)  # 4s, 8s, 16s
                logger.warning(
                    f"IBKR connection retry {attempt + 1}/{max_retries} "
                    f"after {wait_time}s backoff..."
                )
                time.sleep(wait_time)

            if self.connect():
                if attempt > 0:
                    logger.info(
                        f"IBKR connection succeeded on retry {attempt + 1}/{max_retries}"
                    )
                return True

            logger.warning(
                f"IBKR connection attempt {attempt + 1}/{max_retries} failed "
                f"(host={self.host}, port={self.port})"
            )

        logger.error(
            f"IBKR connection failed after {max_retries} attempts "
            f"to {self.host}:{self.port}"
        )
        return False

    def _ensure_connected(self) -> bool:
        """Ensure broker is connected, attempting reconnection if needed.

        Returns:
            True if connected, False if reconnection failed.
        """
        self._ensure_event_loop()
        if self._connected and self.ib.isConnected():
            return True

        logger.warning(
            f"IBKR connection lost (flag={self._connected}, "
            f"isConnected={self.ib.isConnected() if self._connected else 'N/A'}), "
            f"attempting reconnect..."
        )
        self._connected = False

        # Reconnect with fresh IB instance to avoid stale state
        try:
            self.ib.disconnect()
        except Exception:
            pass
        self.ib = self.IB()

        return self.connect_with_retry(max_retries=2)

    def disconnect(self) -> None:
        """Disconnect from IB Gateway."""
        was_connected = self._connected
        if self._connected:
            try:
                self.ib.disconnect()
            except Exception:
                pass
            self._connected = False
        if was_connected:
            logger.info("IBKR disconnected (was connected)")
        else:
            logger.debug("IBKR disconnect called (was already disconnected)")

    def test_connection(self) -> bool:
        """Test the broker connection."""
        start = time.time()
        logger.info("IBKR test_connection started")
        try:
            self._ensure_event_loop()
            if not self._connected:
                if not self.connect():
                    logger.error("IBKR test_connection: connect failed")
                    return False

            account = self.get_account()
            elapsed = time.time() - start
            if account:
                logger.info(
                    f"IBKR test_connection OK in {elapsed:.2f}s: "
                    f"account={account.id}, cash=${account.cash:,.2f}, "
                    f"portfolio=${account.portfolio_value:,.2f}"
                )
                return True
            logger.error(f"IBKR test_connection: account data unavailable ({elapsed:.2f}s)")
            return False
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"IBKR test_connection failed in {elapsed:.2f}s: {e}")
            return False

    def get_account(self) -> Optional[AccountInfo]:
        """Get account information from IBKR."""
        start = time.time()
        logger.debug("IBKR get_account called")
        try:
            if not self._ensure_connected():
                logger.error("IBKR get_account: not connected")
                return None

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

            result = AccountInfo(
                id=account_id,
                cash=values.get('TotalCashValue', 0),
                buying_power=values.get('BuyingPower', 0),
                portfolio_value=values.get('NetLiquidation', 0),
                equity=values.get('EquityWithLoanValue', 0),
                last_equity=values.get('NetLiquidation', 0)
            )
            elapsed = time.time() - start
            logger.info(
                f"IBKR get_account OK in {elapsed:.2f}s: "
                f"account={account_id}, cash=${result.cash:,.2f}, "
                f"portfolio=${result.portfolio_value:,.2f}"
            )
            return result
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"IBKR get_account failed in {elapsed:.2f}s: {e}")
            logger.debug(traceback.format_exc())
            return None

    def get_positions(self) -> List[Position]:
        """Get all open positions from IBKR."""
        start = time.time()
        logger.debug("IBKR get_positions called")
        try:
            if not self._ensure_connected():
                logger.error("IBKR get_positions: not connected")
                return []

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

            elapsed = time.time() - start
            logger.info(f"IBKR get_positions: {len(result)} positions in {elapsed:.2f}s")
            return result
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"IBKR get_positions failed in {elapsed:.2f}s: {e}")
            logger.debug(traceback.format_exc())
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
        start = time.time()
        logger.info(f"IBKR place_market_order: {side.upper()} {qty} {symbol}")
        try:
            if not self._ensure_connected():
                logger.error("IBKR place_market_order: not connected")
                return None

            contract = self.Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            action = 'BUY' if side.lower() == 'buy' else 'SELL'
            order = self.MarketOrder(action, qty)

            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)  # Wait for order to be processed

            elapsed = time.time() - start
            logger.info(
                f"IBKR ORDER placed in {elapsed:.2f}s: "
                f"{action} {qty} {symbol} (market), "
                f"orderId={trade.order.orderId}, "
                f"status={trade.orderStatus.status}"
            )

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
            elapsed = time.time() - start
            logger.error(
                f"IBKR place_market_order failed in {elapsed:.2f}s: "
                f"{side.upper()} {qty} {symbol}: {e}"
            )
            logger.debug(traceback.format_exc())
            return None

    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Optional[Order]:
        """Place a limit order on IBKR."""
        start = time.time()
        logger.info(f"IBKR place_limit_order: {side.upper()} {qty} {symbol} @ ${limit_price}")
        try:
            if not self._ensure_connected():
                logger.error("IBKR place_limit_order: not connected")
                return None

            contract = self.Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            action = 'BUY' if side.lower() == 'buy' else 'SELL'
            order = self.LimitOrder(action, qty, limit_price)

            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)

            elapsed = time.time() - start
            logger.info(
                f"IBKR ORDER placed in {elapsed:.2f}s: "
                f"{action} {qty} {symbol} @ ${limit_price} (limit), "
                f"orderId={trade.order.orderId}, "
                f"status={trade.orderStatus.status}"
            )

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
            elapsed = time.time() - start
            logger.error(
                f"IBKR place_limit_order failed in {elapsed:.2f}s: "
                f"{side.upper()} {qty} {symbol} @ ${limit_price}: {e}"
            )
            logger.debug(traceback.format_exc())
            return None

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order status by ID."""
        start = time.time()
        logger.debug(f"IBKR get_order called: order_id={order_id}")
        try:
            if not self._ensure_connected():
                logger.error("IBKR get_order: not connected")
                return None

            # Find the trade by order ID
            for trade in self.ib.trades():
                if str(trade.order.orderId) == order_id:
                    elapsed = time.time() - start
                    logger.debug(
                        f"IBKR get_order found in {elapsed:.2f}s: "
                        f"order_id={order_id}, status={trade.orderStatus.status}"
                    )
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
            elapsed = time.time() - start
            logger.warning(f"IBKR get_order: order_id={order_id} not found ({elapsed:.2f}s)")
            return None
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"IBKR get_order failed in {elapsed:.2f}s: order_id={order_id}: {e}")
            logger.debug(traceback.format_exc())
            return None

    def get_orders_history(self, limit: int = 50) -> List[Order]:
        """Get recent order history from IBKR."""
        start = time.time()
        logger.debug(f"IBKR get_orders_history called: limit={limit}")
        try:
            if not self._ensure_connected():
                logger.error("IBKR get_orders_history: not connected")
                return []

            trades = self.ib.trades()
            orders = []

            for trade in trades[:limit]:
                # Get the order creation time from the log if available
                created_time = None
                if trade.log and len(trade.log) > 0:
                    # The first log entry typically contains the submission time
                    created_time = trade.log[0].time if hasattr(trade.log[0], 'time') else None

                # If no log time, use current time as fallback
                if created_time is None:
                    created_time = datetime.now(timezone.utc)

                orders.append(Order(
                    id=str(trade.order.orderId),
                    symbol=trade.contract.symbol,
                    side=trade.order.action.lower(),
                    qty=trade.order.totalQuantity,
                    order_type=trade.order.orderType.lower(),
                    status=trade.orderStatus.status.lower(),
                    limit_price=trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else None,
                    filled_qty=trade.orderStatus.filled,
                    filled_price=trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice else None,
                    created_at=created_time
                ))

            elapsed = time.time() - start
            logger.info(
                f"IBKR get_orders_history: {len(orders)} orders "
                f"(from {len(trades)} total) in {elapsed:.2f}s"
            )
            return orders
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"IBKR get_orders_history failed in {elapsed:.2f}s: {e}")
            logger.debug(traceback.format_exc())
            return []

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        start = time.time()
        logger.info(f"IBKR cancel_order called: order_id={order_id}")
        try:
            if not self._ensure_connected():
                logger.error("IBKR cancel_order: not connected")
                return False

            for trade in self.ib.trades():
                if str(trade.order.orderId) == order_id:
                    self.ib.cancelOrder(trade.order)
                    elapsed = time.time() - start
                    logger.info(f"IBKR ORDER cancelled in {elapsed:.2f}s: order_id={order_id}")
                    return True

            elapsed = time.time() - start
            logger.warning(f"IBKR cancel_order: order_id={order_id} not found ({elapsed:.2f}s)")
            return False
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"IBKR cancel_order failed in {elapsed:.2f}s: order_id={order_id}: {e}")
            logger.debug(traceback.format_exc())
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
        except Exception:
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
        start = time.time()
        try:
            contract = self.Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(2)  # Wait for data

            price = ticker.last or ticker.close or 0
            self.ib.cancelMktData(contract)  # Clean up
            elapsed = time.time() - start
            logger.debug(f"IBKR price for {symbol}: ${price} ({elapsed:.2f}s)")
            return price
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"IBKR price fetch failed for {symbol} in {elapsed:.2f}s: {e}")
            return 0
