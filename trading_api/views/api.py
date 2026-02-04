"""Trading API views.

Migrated from Flask to Django REST Framework.
Includes trade/position persistence, DB fallback, and diagnostic logging.
"""

import logging
import time
import concurrent.futures
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------

def get_trading_client():
    """Get trading client using broker factory (supports Alpaca and IBKR)."""
    from trading_api.services import get_broker
    return BrokerClientWrapper(get_broker())


def get_broker_info():
    """Get info about the current broker."""
    from trading_api.services import get_broker_name
    return get_broker_name()


class BrokerClientWrapper:
    """Wrapper to provide backward-compatible dict interface from broker dataclasses."""

    def __init__(self, broker):
        self.broker = broker

    def get_account(self):
        """Get account as dictionary."""
        account = self.broker.get_account()
        if not account:
            return None
        return {
            'id': account.id,
            'cash': account.cash,
            'buying_power': account.buying_power,
            'portfolio_value': account.portfolio_value,
            'equity': account.equity,
            'last_equity': account.last_equity,
        }

    def get_positions(self):
        """Get positions as list of dictionaries."""
        positions = self.broker.get_positions()
        return [
            {
                'symbol': pos.symbol,
                'qty': pos.qty,
                'avg_entry_price': pos.avg_entry_price,
                'current_price': pos.current_price,
                'market_value': pos.market_value,
                'unrealized_pl': pos.unrealized_pl,
                'unrealized_plpc': pos.unrealized_plpc,
            }
            for pos in positions
        ]

    def get_orders_history(self, limit=50):
        """Get order history as list of dictionaries."""
        orders = self.broker.get_orders_history(limit)
        return [
            {
                'id': order.id,
                'symbol': order.symbol,
                'side': order.side,
                'qty': order.qty,
                'type': order.order_type,
                'status': order.status,
                'limit_price': order.limit_price,
                'filled_qty': order.filled_qty,
                'filled_avg_price': order.filled_price,
                'created_at': str(order.created_at) if order.created_at else None,
            }
            for order in orders
        ]

    def is_market_open(self):
        """Check if market is open."""
        return self.broker.is_market_open()

    def get_market_hours(self):
        """Get market hours."""
        return self.broker.get_market_hours()


def get_risk_manager():
    """Get risk manager."""
    from trading_api.services import get_risk_manager as _get_rm
    RiskManager = _get_rm()
    return RiskManager()


def get_data_aggregator():
    """Get data aggregator."""
    from trading_api.services import get_data_aggregator as _get_da
    DataAggregator = _get_da()
    return DataAggregator()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def sync_trades_to_db(orders, user=None):
    """Sync IBKR trade data to Django Trade model.

    Uses order_id for deduplication via update_or_create.
    Only syncs orders that have an order_id.

    Args:
        orders: List of order dicts from BrokerClientWrapper.get_orders_history()
        user: Optional Django User instance

    Returns:
        Tuple of (created_count, updated_count)
    """
    from trading_api.models import Trade

    created = 0
    updated = 0

    for order in orders:
        order_id = order.get('id')
        if not order_id:
            continue

        side = order.get('side', '').upper()
        if side not in ('BUY', 'SELL'):
            continue

        qty = int(order.get('qty', 0)) if order.get('qty') else 0
        filled_price = order.get('filled_avg_price')
        price = filled_price or 0

        try:
            obj, was_created = Trade.objects.update_or_create(
                order_id=order_id,
                defaults={
                    'user': user,
                    'symbol': order.get('symbol', ''),
                    'action': side,
                    'quantity': qty,
                    'price': price,
                    'total_value': qty * float(price) if price else 0,
                    'order_type': order.get('type', 'market'),
                    'status': order.get('status', 'pending'),
                    'filled_qty': int(order.get('filled_qty', 0)) if order.get('filled_qty') else None,
                    'filled_avg_price': filled_price,
                    'limit_price': order.get('limit_price'),
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            logger.error(f"Failed to sync trade order_id={order_id}: {e}")

    if created or updated:
        logger.info(f"Trade sync complete: {created} created, {updated} updated")

    return created, updated


def save_portfolio_snapshot(account, positions, user=None):
    """Save portfolio and position snapshots to database.

    Args:
        account: Account dict from BrokerClientWrapper
        positions: List of position dicts
        user: Optional Django User instance

    Returns:
        The created PortfolioSnapshot, or None on error
    """
    from trading_api.models import PortfolioSnapshot, PositionSnapshot

    try:
        daily_change = account['equity'] - account['last_equity']
        daily_change_pct = (
            (daily_change / account['last_equity'] * 100)
            if account['last_equity'] > 0 else 0
        )

        snapshot = PortfolioSnapshot.objects.create(
            user=user,
            portfolio_value=account['portfolio_value'],
            cash=account['cash'],
            equity=account['equity'],
            daily_change=daily_change,
            daily_change_pct=daily_change_pct,
        )

        # Save individual positions linked to this snapshot
        for pos in positions:
            PositionSnapshot.objects.create(
                user=user,
                portfolio_snapshot=snapshot,
                symbol=pos['symbol'],
                qty=pos['qty'],
                avg_entry_price=pos['avg_entry_price'],
                current_price=pos['current_price'],
                market_value=pos['market_value'],
                unrealized_pl=pos['unrealized_pl'],
                unrealized_plpc=pos['unrealized_plpc'],
            )

        logger.info(
            f"Portfolio snapshot saved: ${account['portfolio_value']}, "
            f"{len(positions)} positions"
        )
        return snapshot

    except Exception as e:
        logger.error(f"Failed to save portfolio snapshot: {e}")
        return None


def should_save_snapshot(user):
    """Check if enough time has passed since last snapshot (5 min minimum)."""
    from trading_api.models import PortfolioSnapshot
    last = PortfolioSnapshot.objects.filter(user=user).order_by('-timestamp').first()
    if not last:
        return True
    return timezone.now() - last.timestamp > timedelta(minutes=5)


# ---------------------------------------------------------------------------
# API Views
# ---------------------------------------------------------------------------

class BrokerStatusView(APIView):
    """Get detailed broker connection status and diagnostics."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        import os
        import socket
        from datetime import datetime

        start_time = time.time()
        logger.info("BrokerStatusView.get called")

        broker_name = get_broker_info()
        host = os.environ.get('IBKR_GATEWAY_HOST', '127.0.0.1')
        port = int(os.environ.get('IBKR_GATEWAY_PORT', '4002'))

        status = {
            'broker': broker_name,
            'timestamp': datetime.now().isoformat(),
            'gateway': {
                'host': host,
                'port': port,
            },
            'checks': {},
            'errors': [],
        }

        # Check 1: TCP connectivity to IBKR Gateway
        try:
            tcp_start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            tcp_elapsed = time.time() - tcp_start

            if result == 0:
                status['checks']['tcp_connection'] = {
                    'status': 'ok',
                    'message': f'TCP connection to {host}:{port} successful ({tcp_elapsed:.2f}s)'
                }
                logger.info(f"BrokerStatus TCP check OK: {host}:{port} in {tcp_elapsed:.2f}s")
            else:
                status['checks']['tcp_connection'] = {
                    'status': 'error',
                    'message': f'TCP connection failed (code={result}, {tcp_elapsed:.2f}s)'
                }
                status['errors'].append(f'Cannot reach IBKR Gateway at {host}:{port}')
                logger.warning(f"BrokerStatus TCP check FAILED: code={result}, {tcp_elapsed:.2f}s")
        except Exception as e:
            status['checks']['tcp_connection'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'TCP connection error: {str(e)}')
            logger.error(f"BrokerStatus TCP exception: {e}")

        # Check 2: Broker API connection
        try:
            api_start = time.time()
            from trading_api.services import get_broker
            broker = get_broker()

            if broker.test_connection():
                api_elapsed = time.time() - api_start
                status['checks']['api_connection'] = {
                    'status': 'ok',
                    'message': f'IBKR API connection verified ({api_elapsed:.2f}s)'
                }
                logger.info(f"BrokerStatus API check OK in {api_elapsed:.2f}s")
            else:
                api_elapsed = time.time() - api_start
                status['checks']['api_connection'] = {
                    'status': 'error',
                    'message': f'IBKR API connection test failed ({api_elapsed:.2f}s)'
                }
                status['errors'].append('Broker API connection test failed')
                logger.warning(f"BrokerStatus API check FAILED in {api_elapsed:.2f}s")
        except Exception as e:
            status['checks']['api_connection'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'Broker API error: {str(e)}')
            logger.error(f"BrokerStatus API exception: {e}")

        # Check 3: Account data retrieval
        try:
            acct_start = time.time()
            trading_client = get_trading_client()
            account = trading_client.get_account()
            acct_elapsed = time.time() - acct_start

            if account:
                status['checks']['account_data'] = {
                    'status': 'ok',
                    'message': f'Account {account.get("id", "unknown")} accessible ({acct_elapsed:.2f}s)',
                    'account_id': account.get('id'),
                    'cash': account.get('cash'),
                    'portfolio_value': account.get('portfolio_value'),
                    'buying_power': account.get('buying_power'),
                }
                status['trading_ready'] = True
                logger.info(
                    f"BrokerStatus account check OK in {acct_elapsed:.2f}s: "
                    f"account={account.get('id')}"
                )
            else:
                status['checks']['account_data'] = {
                    'status': 'error',
                    'message': f'Failed to retrieve account data ({acct_elapsed:.2f}s)'
                }
                status['errors'].append('Cannot retrieve account data from broker')
                status['trading_ready'] = False
                logger.warning(f"BrokerStatus account check FAILED in {acct_elapsed:.2f}s")
        except Exception as e:
            status['checks']['account_data'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'Account data error: {str(e)}')
            status['trading_ready'] = False
            logger.error(f"BrokerStatus account exception: {e}")

        # Overall status
        all_checks_ok = all(
            check.get('status') == 'ok'
            for check in status['checks'].values()
        )
        status['overall_status'] = 'connected' if all_checks_ok else 'error'
        status['can_trade'] = all_checks_ok and status.get('trading_ready', False)

        elapsed = time.time() - start_time
        check_summary = ', '.join(
            f'{k}:{v.get("status")}' for k, v in status['checks'].items()
        )
        logger.info(
            f"BrokerStatusView.get completed in {elapsed:.2f}s: "
            f"overall={status['overall_status']}, can_trade={status['can_trade']}, "
            f"checks=[{check_summary}]"
        )

        return Response(status)


class PortfolioView(APIView):
    """Get current portfolio data with persistence and fallback."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("PortfolioView.get called")

        try:
            trading_client = get_trading_client()
            account = trading_client.get_account()
            positions = trading_client.get_positions()

            if not account:
                logger.warning("PortfolioView: account data unavailable, falling back to DB")
                return self._fallback_from_db(request)

            daily_change = account['equity'] - account['last_equity']
            daily_change_pct = (
                (daily_change / account['last_equity'] * 100)
                if account['last_equity'] > 0 else 0
            )

            # Persist snapshot (rate limited)
            user = request.user if request.user.is_authenticated else None
            if should_save_snapshot(user):
                save_portfolio_snapshot(account, positions, user=user)

            elapsed = time.time() - start_time
            logger.info(
                f"PortfolioView.get completed in {elapsed:.2f}s: "
                f"portfolio=${account['portfolio_value']}, "
                f"{len(positions)} positions"
            )

            return Response({
                'account': {
                    'cash': account['cash'],
                    'portfolio_value': account['portfolio_value'],
                    'equity': account['equity'],
                    'buying_power': account['buying_power'],
                },
                'performance': {
                    'daily_change': daily_change,
                    'daily_change_pct': daily_change_pct,
                },
                'positions': positions,
                'positions_count': len(positions),
                'broker_connected': True,
                'source': 'ibkr_live',
            })
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(
                f"PortfolioView.get broker failed in {elapsed:.2f}s: {e}, "
                f"falling back to DB"
            )
            return self._fallback_from_db(request)

    def _fallback_from_db(self, request):
        """Serve portfolio from most recent DB snapshot."""
        from trading_api.models import PortfolioSnapshot

        snapshot = PortfolioSnapshot.objects.filter(
            user=request.user
        ).order_by('-timestamp').first()

        if not snapshot:
            logger.info("PortfolioView fallback: no snapshots in DB")
            return Response({
                'account': {'cash': 0, 'portfolio_value': 0, 'equity': 0, 'buying_power': 0},
                'performance': {'daily_change': 0, 'daily_change_pct': 0},
                'positions': [],
                'positions_count': 0,
                'broker_connected': False,
                'source': 'none',
                'error': 'No data available - broker disconnected and no snapshots saved',
            })

        positions = []
        for ps in snapshot.positions.all():
            positions.append({
                'symbol': ps.symbol,
                'qty': float(ps.qty),
                'avg_entry_price': float(ps.avg_entry_price),
                'current_price': float(ps.current_price),
                'market_value': float(ps.market_value),
                'unrealized_pl': float(ps.unrealized_pl),
                'unrealized_plpc': float(ps.unrealized_plpc),
            })

        logger.info(
            f"PortfolioView fallback from DB: "
            f"snapshot={snapshot.timestamp.isoformat()}, {len(positions)} positions"
        )

        return Response({
            'account': {
                'cash': float(snapshot.cash),
                'portfolio_value': float(snapshot.portfolio_value),
                'equity': float(snapshot.equity),
                'buying_power': 0,
            },
            'performance': {
                'daily_change': float(snapshot.daily_change or 0),
                'daily_change_pct': float(snapshot.daily_change_pct or 0),
            },
            'positions': positions,
            'positions_count': len(positions),
            'broker_connected': False,
            'source': 'database',
            'snapshot_time': snapshot.timestamp.isoformat(),
        })


class RiskView(APIView):
    """Get current risk status."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("RiskView.get called")
        try:
            trading_client = get_trading_client()
            risk_manager = get_risk_manager()

            account = trading_client.get_account()
            if not account:
                elapsed = time.time() - start_time
                logger.warning(f"RiskView.get: account unavailable ({elapsed:.2f}s)")
                return Response({
                    'risk_level': 'UNKNOWN',
                    'daily_trades': 0,
                    'daily_loss': 0,
                    'max_position_value': 0,
                    'kill_switch_active': False,
                    'broker_connected': False,
                    'error': 'Broker not connected',
                })

            risk_status = risk_manager.get_risk_status(account)
            risk_status['broker_connected'] = True

            elapsed = time.time() - start_time
            logger.info(
                f"RiskView.get completed in {elapsed:.2f}s: "
                f"risk_level={risk_status.get('risk_level', 'N/A')}"
            )
            return Response(risk_status)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"RiskView.get failed in {elapsed:.2f}s: {e}")
            return Response({
                'risk_level': 'UNKNOWN',
                'daily_trades': 0,
                'daily_loss': 0,
                'max_position_value': 0,
                'kill_switch_active': False,
                'broker_connected': False,
                'error': str(e),
            })


class MarketView(APIView):
    """Get market status."""

    permission_classes = [AllowAny]  # Public endpoint

    def get(self, request):
        start_time = time.time()
        logger.debug("MarketView.get called")
        try:
            trading_client = get_trading_client()
            is_open = trading_client.is_market_open()
            hours = trading_client.get_market_hours()

            elapsed = time.time() - start_time
            logger.debug(f"MarketView.get completed in {elapsed:.2f}s: is_open={is_open}")

            return Response({
                'is_open': is_open,
                'next_open': hours.get('next_open') if hours else None,
                'next_close': hours.get('next_close') if hours else None,
                'broker_connected': True,
            })
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"MarketView.get failed in {elapsed:.2f}s: {e}")
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo('America/New_York'))
            weekday = now.weekday()
            hour = now.hour
            is_market_hours = weekday < 5 and 9 <= hour < 16
            return Response({
                'is_open': is_market_hours,
                'next_open': None,
                'next_close': None,
                'broker_connected': False,
                'error': str(e),
            })


class WatchlistView(APIView):
    """Get current prices for watchlist."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("WatchlistView.get called")
        try:
            data_aggregator = get_data_aggregator()
            trading_config = settings.TRADING_CONFIG
            watchlist_symbols = trading_config['WATCHLIST']

            prices = data_aggregator.market_client.get_current_prices(watchlist_symbols)
            watchlist = []
            for symbol in watchlist_symbols:
                watchlist.append({
                    'symbol': symbol,
                    'price': prices.get(symbol, 0)
                })

            elapsed = time.time() - start_time
            logger.info(
                f"WatchlistView.get completed in {elapsed:.2f}s: "
                f"{len(watchlist)} symbols"
            )
            return Response({'watchlist': watchlist})
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"WatchlistView.get failed in {elapsed:.2f}s: {e}")
            trading_config = settings.TRADING_CONFIG
            watchlist_symbols = trading_config.get('WATCHLIST', [])
            return Response({
                'watchlist': [{'symbol': s, 'price': 0} for s in watchlist_symbols],
                'error': str(e),
            })


class TradesView(APIView):
    """Get recent trade history, with DB persistence and fallback."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("TradesView.get called")

        user = request.user if request.user.is_authenticated else None
        broker_connected = False
        broker_trades = []

        # Try to get live trades from broker
        try:
            trading_client = get_trading_client()
            orders = trading_client.get_orders_history(limit=30)
            broker_connected = True

            # Sync live trades to DB for persistence
            if orders:
                sync_trades_to_db(orders, user=user)

            for order in orders:
                qty = order.get('qty', 0)
                filled_qty = order.get('filled_qty', 0)

                broker_trades.append({
                    'id': order.get('id'),
                    'symbol': order.get('symbol'),
                    'action': order.get('side', '').upper(),
                    'quantity': int(qty) if qty else 0,
                    'filled_quantity': int(filled_qty) if filled_qty else 0,
                    'order_type': order.get('type', '').replace('OrderType.', '').replace('order_type.', ''),
                    'status': order.get('status', '').replace('OrderStatus.', '').replace('order_status.', ''),
                    'limit_price': order.get('limit_price'),
                    'filled_price': order.get('filled_avg_price'),
                    'created_at': order.get('created_at'),
                })
        except Exception as e:
            logger.warning(f"TradesView.get broker error: {e}")

        # Always supplement with DB trades (covers gateway restarts)
        db_trades = self._get_db_trades(user)

        # Merge: broker trades first, then DB trades not already in broker set
        broker_ids = {t['id'] for t in broker_trades if t.get('id')}
        merged_trades = list(broker_trades)
        for t in db_trades:
            if t['id'] not in broker_ids:
                merged_trades.append(t)

        # Sort by created_at descending, limit to 50
        merged_trades.sort(
            key=lambda t: t.get('created_at') or '', reverse=True
        )
        merged_trades = merged_trades[:50]

        source = 'ibkr_live' if broker_trades else ('database' if db_trades else 'none')

        elapsed = time.time() - start_time
        logger.info(
            f"TradesView.get completed in {elapsed:.2f}s: "
            f"{len(broker_trades)} from broker + {len(db_trades)} from DB "
            f"= {len(merged_trades)} merged"
        )

        return Response({
            'trades': merged_trades,
            'broker_connected': broker_connected,
            'source': source,
        })

    def _get_db_trades(self, user):
        """Get trade history from the Django database.

        Fetches trades for the current user AND trades with no user (synced
        before authentication or from background tasks). This ensures trades
        are never lost due to user mismatch.
        """
        from trading_api.models import Trade
        from django.db.models import Q

        # Get trades for this user OR trades with no user assigned
        if user:
            trade_filter = Q(user=user) | Q(user__isnull=True)
        else:
            trade_filter = Q(user__isnull=True)

        db_trades = Trade.objects.filter(
            trade_filter
        ).order_by('-created_at')[:50]

        logger.debug(f"_get_db_trades: found {len(db_trades)} trades in DB (user={user})")

        trades = []
        for t in db_trades:
            trades.append({
                'id': t.order_id or str(t.id),
                'symbol': t.symbol,
                'action': t.action,
                'quantity': t.quantity,
                'filled_quantity': t.filled_qty or 0,
                'order_type': t.order_type,
                'status': t.status,
                'limit_price': float(t.limit_price) if t.limit_price else None,
                'filled_price': float(t.filled_avg_price) if t.filled_avg_price else None,
                'created_at': t.created_at.isoformat() if t.created_at else None,
            })

        return trades


class ConfigView(APIView):
    """Get trading configuration."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("ConfigView.get called")

        trading_config = settings.TRADING_CONFIG

        # Test TCP connection to IBKR
        import socket
        import os
        host = os.environ.get('IBKR_GATEWAY_HOST', '10.138.0.3')
        port = int(os.environ.get('IBKR_GATEWAY_PORT', '4002'))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            result = sock.connect_ex((host, port))
            api_conn = "success" if result == 0 else f"failed (code={result})"
        except Exception as e:
            api_conn = f"error: {str(e)}"
        finally:
            sock.close()

        # Debug info for broker selection
        broker_type_env = os.environ.get('BROKER_TYPE', 'unknown')
        broker_name = get_broker_info()

        elapsed = time.time() - start_time
        logger.info(
            f"ConfigView.get completed in {elapsed:.2f}s: "
            f"broker={broker_name}, tcp={api_conn}"
        )

        return Response({
            'broker': broker_name,
            'debug_broker_type_env': broker_type_env,
            'debug_broker_name_computed': broker_name,
            'ibkr_connection_test': api_conn,
            'ibkr_host': host,
            'ibkr_port': port,
            'watchlist': trading_config['WATCHLIST'],
            'analysis_interval': trading_config['ANALYSIS_INTERVAL_MINUTES'],
            'max_position_pct': trading_config['MAX_POSITION_PCT'] * 100,
            'max_daily_loss_pct': trading_config['MAX_DAILY_LOSS_PCT'] * 100,
            'min_confidence': trading_config['MIN_CONFIDENCE'] * 100,
            'stop_loss_pct': trading_config['STOP_LOSS_PCT'] * 100,
            'take_profit_pct': trading_config['TAKE_PROFIT_PCT'] * 100,
        })


class IndicatorsView(APIView):
    """Get technical indicators for watchlist symbols."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("IndicatorsView.get called")
        try:
            import yfinance as yf
            from trading_api.services import get_technical_indicators
            TechnicalIndicators = get_technical_indicators()

            trading_config = settings.TRADING_CONFIG
            top_symbols = trading_config['WATCHLIST'][:10]

            def get_indicator_for_symbol(symbol):
                """Get indicator data for a single symbol."""
                try:
                    ticker = yf.Ticker(symbol)
                    df = ticker.history(period="3mo")

                    if df.empty or len(df) < 30:
                        return {
                            'symbol': symbol,
                            'price': 0,
                            'rsi': None,
                            'rsi_signal': 'NO DATA',
                            'macd': None,
                            'macd_trend': 'NO DATA',
                            'overall_signal': 'NO DATA'
                        }

                    tech = TechnicalIndicators(df)
                    tech_data = tech.calculate_all()

                    current_price = float(df['Close'].iloc[-1]) if len(df) > 0 else 0

                    # Extract RSI
                    rsi = tech_data.get('rsi')
                    if rsi is not None and hasattr(rsi, 'iloc'):
                        rsi = float(rsi.iloc[-1]) if len(rsi) > 0 and not rsi.empty else None

                    rsi_signal = 'NEUTRAL'
                    if rsi is not None:
                        if rsi > 70:
                            rsi_signal = 'OVERBOUGHT'
                        elif rsi < 30:
                            rsi_signal = 'OVERSOLD'

                    # Extract MACD
                    macd = tech_data.get('macd')
                    macd_sig = tech_data.get('macd_signal')
                    if macd is not None and hasattr(macd, 'iloc'):
                        macd = float(macd.iloc[-1]) if len(macd) > 0 and not macd.empty else None
                    if macd_sig is not None and hasattr(macd_sig, 'iloc'):
                        macd_sig = float(macd_sig.iloc[-1]) if len(macd_sig) > 0 else None

                    macd_trend = 'NEUTRAL'
                    if macd is not None and macd_sig is not None:
                        if macd > macd_sig:
                            macd_trend = 'BULLISH'
                        else:
                            macd_trend = 'BEARISH'

                    # Overall signal
                    overall = 'NEUTRAL'
                    if rsi_signal == 'OVERSOLD' or macd_trend == 'BULLISH':
                        overall = 'BULLISH'
                    elif rsi_signal == 'OVERBOUGHT' or macd_trend == 'BEARISH':
                        overall = 'BEARISH'

                    return {
                        'symbol': symbol,
                        'price': round(current_price, 2),
                        'rsi': round(rsi, 2) if rsi else None,
                        'rsi_signal': rsi_signal,
                        'macd': round(macd, 4) if macd else None,
                        'macd_trend': macd_trend,
                        'overall_signal': overall
                    }

                except Exception as e:
                    logger.error(f"Indicator error for {symbol}: {e}")
                    return {
                        'symbol': symbol,
                        'price': 0,
                        'rsi': None,
                        'rsi_signal': 'ERROR',
                        'macd': None,
                        'macd_trend': 'ERROR',
                        'overall_signal': 'ERROR'
                    }

            # Use thread pool for parallel fetching
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(get_indicator_for_symbol, top_symbols))

            elapsed = time.time() - start_time
            logger.info(
                f"IndicatorsView.get completed in {elapsed:.2f}s: "
                f"{len(results)} indicators"
            )
            return Response({'indicators': results})

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"IndicatorsView.get failed in {elapsed:.2f}s: {e}")
            return Response({'error': str(e), 'indicators': []}, status=500)


class OptionChainView(APIView):
    """Get option chain data for a symbol at a specific strike across all expirations."""

    permission_classes = [AllowAny]  # Public endpoint using free yfinance data

    def get(self, request):
        start_time = time.time()

        symbol = request.GET.get('symbol', '').upper()
        strike_str = request.GET.get('strike')
        option_type = request.GET.get('type', 'call').lower()

        if not symbol:
            return Response({'error': 'symbol parameter is required'}, status=400)
        if not strike_str:
            return Response({'error': 'strike parameter is required'}, status=400)
        if option_type not in ('call', 'put'):
            return Response({'error': 'type must be "call" or "put"'}, status=400)

        try:
            strike = float(strike_str)
        except ValueError:
            return Response({'error': 'strike must be a valid number'}, status=400)

        logger.info(f"OptionChainView.get: {symbol} ${strike} {option_type}")

        try:
            import yfinance as yf
            from datetime import datetime as dt
            from src.utils.greeks import black_scholes_greeks

            ticker = yf.Ticker(symbol)

            # Current stock price
            current_price = None
            try:
                info = ticker.info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice')
                if not current_price:
                    hist = ticker.history(period='1d')
                    current_price = float(hist['Close'].iloc[-1]) if len(hist) > 0 else None
            except Exception as e:
                logger.warning(f"OptionChainView: could not get price for {symbol}: {e}")

            # All expiration dates
            try:
                expirations = ticker.options
            except Exception:
                return Response(
                    {'error': f'No options data available for {symbol}'},
                    status=404,
                )

            if not expirations:
                return Response(
                    {'error': f'No option expirations found for {symbol}'},
                    status=404,
                )

            logger.info(f"OptionChainView: {len(expirations)} expirations for {symbol}")

            risk_free_rate = 0.045  # ~4.5 % US Treasury approximation
            options_data = []

            for exp_date in expirations:
                try:
                    chain = ticker.option_chain(exp_date)
                    df = chain.calls if option_type == 'call' else chain.puts

                    # Find exact or closest strike
                    strike_match = df[df['strike'] == strike]
                    if strike_match.empty:
                        if df.empty:
                            continue
                        closest_idx = (df['strike'] - strike).abs().idxmin()
                        strike_match = df.loc[[closest_idx]]
                    actual_strike = float(strike_match['strike'].iloc[0])

                    row = strike_match.iloc[0]
                    last_price = float(row.get('lastPrice', 0) or 0)
                    bid = float(row.get('bid', 0) or 0)
                    ask = float(row.get('ask', 0) or 0)
                    volume = int(row.get('volume', 0) or 0)
                    open_interest = int(row.get('openInterest', 0) or 0)
                    implied_vol = float(row.get('impliedVolatility', 0) or 0)

                    exp_datetime = dt.strptime(exp_date, '%Y-%m-%d')
                    days_to_expiry = (exp_datetime - dt.now()).days
                    time_to_expiry = max(days_to_expiry, 0) / 365.0

                    # Greeks via Black-Scholes
                    greeks = {'delta': None, 'gamma': None, 'theta': None, 'vega': None}
                    if current_price and implied_vol > 0 and time_to_expiry > 0:
                        greeks = black_scholes_greeks(
                            option_type=option_type,
                            stock_price=current_price,
                            strike_price=actual_strike,
                            time_to_expiry=time_to_expiry,
                            risk_free_rate=risk_free_rate,
                            implied_volatility=implied_vol,
                        )

                    options_data.append({
                        'expiration': exp_date,
                        'days_to_expiry': days_to_expiry,
                        'strike': actual_strike,
                        'last_price': last_price,
                        'bid': bid,
                        'ask': ask,
                        'volume': volume,
                        'open_interest': open_interest,
                        'implied_volatility': round(implied_vol * 100, 2),
                        'delta': greeks.get('delta'),
                        'gamma': greeks.get('gamma'),
                        'theta': greeks.get('theta'),
                        'vega': greeks.get('vega'),
                    })
                except Exception as e:
                    logger.warning(f"OptionChainView: error for {exp_date}: {e}")
                    continue

            options_data.sort(key=lambda x: x['expiration'])

            elapsed = time.time() - start_time
            logger.info(
                f"OptionChainView.get completed in {elapsed:.2f}s: "
                f"{symbol} ${strike} {option_type}, {len(options_data)} expirations"
            )

            return Response({
                'symbol': symbol,
                'strike': strike,
                'type': option_type,
                'current_price': current_price,
                'options': options_data,
                'count': len(options_data),
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"OptionChainView.get failed in {elapsed:.2f}s: {e}", exc_info=True)
            return Response({'error': f'Failed to fetch option chain: {str(e)}'}, status=500)


class TestTradeView(APIView):
    """Execute a test trade to verify trading functionality."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Place a small test trade.

        Body: {"symbol": "AAPL", "action": "BUY", "quantity": 1}
        """
        start_time = time.time()
        try:
            symbol = request.data.get('symbol', 'AAPL')
            action = request.data.get('action', 'BUY').upper()
            quantity = int(request.data.get('quantity', 1))

            logger.info(f"TestTradeView.post called: {action} {quantity} {symbol}")

            if action not in ['BUY', 'SELL']:
                return Response({'error': 'Action must be BUY or SELL'}, status=400)

            if quantity < 1 or quantity > 10:
                return Response({'error': 'Quantity must be between 1 and 10 for test trades'}, status=400)

            from trading_api.services import get_broker
            broker = get_broker()

            logger.info(f"TEST TRADE: {action} {quantity} {symbol}")

            # Place market order
            order = broker.place_market_order(
                symbol=symbol,
                qty=quantity,
                side=action.lower()
            )

            elapsed = time.time() - start_time
            if order:
                logger.info(
                    f"TEST TRADE SUCCESS in {elapsed:.2f}s: "
                    f"Order ID {order.id}, Status: {order.status}"
                )
                return Response({
                    'status': 'success',
                    'message': f'Test trade executed: {action} {quantity} {symbol}',
                    'order': {
                        'id': order.id,
                        'symbol': order.symbol,
                        'side': order.side,
                        'qty': order.qty,
                        'status': order.status,
                        'filled_qty': order.filled_qty,
                        'filled_price': order.filled_price,
                    }
                })
            else:
                logger.error(f"TEST TRADE FAILED in {elapsed:.2f}s: order returned None")
                return Response({
                    'status': 'failed',
                    'message': 'Order placement returned None'
                }, status=500)

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"TestTradeView.post failed in {elapsed:.2f}s: {e}", exc_info=True)
            return Response({'status': 'error', 'message': str(e)}, status=500)


class AnalyzeView(APIView):
    """Run trading analysis cycle - triggered by Cloud Scheduler."""

    permission_classes = [AllowAny]  # Called by Cloud Scheduler

    def post(self, request):
        start_time = time.time()
        logger.info("AnalyzeView.post called")
        try:
            from trading_api.services import (
                get_trading_analyst,
                get_order_manager,
                get_slack
            )
            TradingAnalyst = get_trading_analyst()
            OrderManager = get_order_manager()
            _, notify_trade = get_slack()

            trading_client = get_trading_client()

            # Check if market is open
            if not trading_client.is_market_open():
                elapsed = time.time() - start_time
                logger.info(f"AnalyzeView: market closed, skipping ({elapsed:.2f}s)")
                return Response({
                    'status': 'skipped',
                    'message': 'Market is closed'
                })

            # Run analysis
            analyst = TradingAnalyst()
            order_manager = OrderManager()

            account = trading_client.get_account()
            positions = trading_client.get_positions()

            response = analyst.analyze_and_recommend(
                cash=account['cash'],
                portfolio_value=account['portfolio_value'],
                positions=positions
            )

            if not response:
                elapsed = time.time() - start_time
                logger.info(f"AnalyzeView: no LLM response ({elapsed:.2f}s)")
                return Response({'status': 'no_response', 'message': 'No LLM response'})

            # Filter and execute trades
            valid_trades = analyst.filter_by_confidence(response.trades)

            if not valid_trades:
                elapsed = time.time() - start_time
                logger.info(
                    f"AnalyzeView: no high-confidence trades ({elapsed:.2f}s)"
                )
                return Response({
                    'status': 'no_trades',
                    'message': 'No high-confidence trades',
                    'analysis': response.analysis_summary
                })

            # Execute trades
            executed = order_manager.execute_trades(valid_trades)

            # Send Slack notifications
            for trade in valid_trades:
                notify_trade({
                    'action': trade.action,
                    'symbol': trade.symbol,
                    'quantity': trade.quantity,
                    'confidence': trade.confidence,
                    'reasoning': trade.reasoning
                })

            elapsed = time.time() - start_time
            logger.info(
                f"AnalyzeView.post completed in {elapsed:.2f}s: "
                f"{len(executed)} trades executed"
            )

            return Response({
                'status': 'success',
                'trades_executed': len(executed),
                'trades': [
                    {'symbol': t.symbol, 'action': t.action, 'quantity': t.quantity}
                    for t in valid_trades
                ],
                'analysis': response.analysis_summary
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"AnalyzeView.post failed in {elapsed:.2f}s: {e}")
            return Response({'status': 'error', 'message': str(e)}, status=500)


class DailySummaryView(APIView):
    """Send daily trading summary email - triggered by Cloud Scheduler at market close."""

    permission_classes = [AllowAny]  # Called by Cloud Scheduler

    def post(self, request):
        start_time = time.time()
        logger.info("DailySummaryView.post called")
        try:
            from datetime import date
            from src.utils.email_notifier import send_daily_summary
            from trading_api.services import get_slack

            trading_client = get_trading_client()
            risk_manager = get_risk_manager()

            # Get portfolio data
            account = trading_client.get_account()
            positions = trading_client.get_positions()

            if not account:
                elapsed = time.time() - start_time
                logger.error(f"DailySummaryView: account unavailable ({elapsed:.2f}s)")
                return Response({'status': 'error', 'message': 'Failed to get account'}, status=500)

            # Calculate daily change
            daily_change = account['equity'] - account['last_equity']
            daily_change_pct = (daily_change / account['last_equity'] * 100) if account['last_equity'] > 0 else 0

            portfolio = {
                'portfolio_value': account['portfolio_value'],
                'cash': account['cash'],
                'equity': account['equity'],
                'daily_change': daily_change,
                'daily_change_pct': daily_change_pct,
                'positions': positions,
            }

            # Get today's trades
            orders = trading_client.get_orders_history(limit=50)
            today = date.today().isoformat()
            trades_today = []
            for order in orders:
                created = order.get('created_at', '')
                if created and today in str(created):
                    trades_today.append({
                        'action': order.get('side', '').upper(),
                        'symbol': order.get('symbol'),
                        'quantity': order.get('qty'),
                        'filled_price': order.get('filled_avg_price'),
                        'created_at': created,
                        'confidence': 0.8,
                    })

            # Get risk status
            risk_status = risk_manager.get_risk_status(account)

            # Estimate analysis runs
            analysis_runs = 14

            # Send email
            email_sent = send_daily_summary(portfolio, trades_today, analysis_runs, risk_status)

            # Also send to Slack
            _, notify_portfolio = get_slack()
            notify_portfolio({
                'portfolio_value': portfolio['portfolio_value'],
                'daily_change': daily_change,
                'daily_change_pct': daily_change_pct,
                'positions_count': len(positions),
            })

            elapsed = time.time() - start_time
            logger.info(
                f"DailySummaryView.post completed in {elapsed:.2f}s: "
                f"email_sent={email_sent}, trades_today={len(trades_today)}"
            )

            return Response({
                'status': 'success',
                'email_sent': email_sent,
                'portfolio_value': account['portfolio_value'],
                'trades_today': len(trades_today),
                'positions': len(positions),
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"DailySummaryView.post failed in {elapsed:.2f}s: {e}", exc_info=True)
            return Response({'status': 'error', 'message': str(e)}, status=500)
