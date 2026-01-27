"""Trading API views.

Migrated from Flask to Django REST Framework.
"""

import logging
import concurrent.futures
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

logger = logging.getLogger(__name__)


# Lazy import functions to avoid import errors during collectstatic
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


class BrokerStatusView(APIView):
    """Get detailed broker connection status and diagnostics."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        import os
        import socket
        from datetime import datetime

        broker_name = get_broker_info()
        host = os.environ.get('IBKR_GATEWAY_HOST', '127.0.0.1')
        port = int(os.environ.get('IBKR_GATEWAY_PORT', '4004'))

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
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                status['checks']['tcp_connection'] = {
                    'status': 'ok',
                    'message': f'TCP connection to {host}:{port} successful'
                }
            else:
                status['checks']['tcp_connection'] = {
                    'status': 'error',
                    'message': f'TCP connection failed (code={result})'
                }
                status['errors'].append(f'Cannot reach IBKR Gateway at {host}:{port}')
        except Exception as e:
            status['checks']['tcp_connection'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'TCP connection error: {str(e)}')

        # Check 2: Broker API connection
        try:
            from trading_api.services import get_broker
            broker = get_broker()

            if broker.test_connection():
                status['checks']['api_connection'] = {
                    'status': 'ok',
                    'message': 'IBKR API connection verified'
                }
            else:
                status['checks']['api_connection'] = {
                    'status': 'error',
                    'message': 'IBKR API connection test failed'
                }
                status['errors'].append('Broker API connection test failed')
        except Exception as e:
            status['checks']['api_connection'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'Broker API error: {str(e)}')

        # Check 3: Account data retrieval
        try:
            trading_client = get_trading_client()
            account = trading_client.get_account()

            if account:
                status['checks']['account_data'] = {
                    'status': 'ok',
                    'message': f'Account {account.get("id", "unknown")} accessible',
                    'account_id': account.get('id'),
                    'cash': account.get('cash'),
                    'portfolio_value': account.get('portfolio_value'),
                    'buying_power': account.get('buying_power'),
                }
                status['trading_ready'] = True
            else:
                status['checks']['account_data'] = {
                    'status': 'error',
                    'message': 'Failed to retrieve account data'
                }
                status['errors'].append('Cannot retrieve account data from broker')
                status['trading_ready'] = False
        except Exception as e:
            status['checks']['account_data'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'Account data error: {str(e)}')
            status['trading_ready'] = False

        # Overall status
        all_checks_ok = all(
            check.get('status') == 'ok'
            for check in status['checks'].values()
        )
        status['overall_status'] = 'connected' if all_checks_ok else 'error'
        status['can_trade'] = all_checks_ok and status.get('trading_ready', False)

        return Response(status)


class PortfolioView(APIView):
    """Get current portfolio data."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            logger.info(f"PortfolioView: Fetching portfolio for user {request.user.email}")
            trading_client = get_trading_client()
            
            logger.info("PortfolioView: Getting account...")
            account = trading_client.get_account()
            logger.info(f"PortfolioView: Account result: {account}")
            
            logger.info("PortfolioView: Getting positions...")
            positions = trading_client.get_positions()
            logger.info(f"PortfolioView: Positions count: {len(positions) if positions else 0}")
            
            if not account:
                logger.error("PortfolioView: Failed to get account - returned None")
                return Response({'error': 'Failed to get account'}, status=500)
            
            # Calculate daily change
            daily_change = account['equity'] - account['last_equity']
            daily_change_pct = (
                (daily_change / account['last_equity'] * 100) 
                if account['last_equity'] > 0 else 0
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
            })
        except Exception as e:
            logger.error(f"Portfolio error: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)


class RiskView(APIView):
    """Get current risk status."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            trading_client = get_trading_client()
            risk_manager = get_risk_manager()
            
            account = trading_client.get_account()
            if not account:
                return Response({'error': 'Failed to get account'}, status=500)
            
            risk_status = risk_manager.get_risk_status(account)
            return Response(risk_status)
        except Exception as e:
            logger.error(f"Risk error: {e}")
            return Response({'error': str(e)}, status=500)


class MarketView(APIView):
    """Get market status."""
    
    permission_classes = [AllowAny]  # Public endpoint
    
    def get(self, request):
        try:
            trading_client = get_trading_client()
            is_open = trading_client.is_market_open()
            hours = trading_client.get_market_hours()
            
            return Response({
                'is_open': is_open,
                'next_open': hours.get('next_open') if hours else None,
                'next_close': hours.get('next_close') if hours else None,
            })
        except Exception as e:
            logger.error(f"Market error: {e}")
            return Response({'error': str(e)}, status=500)


class WatchlistView(APIView):
    """Get current prices for watchlist."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
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
            
            return Response({'watchlist': watchlist})
        except Exception as e:
            logger.error(f"Watchlist error: {e}")
            return Response({'error': str(e)}, status=500)


class TradesView(APIView):
    """Get recent trade history from Alpaca."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            trading_client = get_trading_client()
            orders = trading_client.get_orders_history(limit=30)
            
            trades = []
            for order in orders:
                trades.append({
                    'id': order.get('id'),
                    'symbol': order.get('symbol'),
                    'action': order.get('side', '').upper(),
                    'quantity': int(order.get('qty', 0)),
                    'filled_quantity': int(order.get('filled_qty', 0)),
                    'order_type': order.get('type', '').replace('OrderType.', ''),
                    'status': order.get('status', '').replace('OrderStatus.', ''),
                    'limit_price': order.get('limit_price'),
                    'filled_price': order.get('filled_avg_price'),
                    'created_at': order.get('created_at'),
                    'filled_at': order.get('filled_at'),
                })
            
            return Response({'trades': trades})
        except Exception as e:
            logger.error(f"Trades error: {e}")
            return Response({'error': str(e)}, status=500)


class ConfigView(APIView):
    """Get trading configuration."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
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
            
            return Response({'indicators': results})
            
        except Exception as e:
            logger.error(f"Indicators error: {e}")
            return Response({'error': str(e), 'indicators': []}, status=500)


class TestTradeView(APIView):
    """Execute a test trade to verify trading functionality."""

    permission_classes = [AllowAny]  # Temporarily public for testing

    def post(self, request):
        """Place a small test trade.

        Body: {"symbol": "AAPL", "action": "BUY", "quantity": 1}
        """
        try:
            symbol = request.data.get('symbol', 'AAPL')
            action = request.data.get('action', 'BUY').upper()
            quantity = int(request.data.get('quantity', 1))

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

            if order:
                logger.info(f"TEST TRADE SUCCESS: Order ID {order.id}, Status: {order.status}")
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
                return Response({
                    'status': 'failed',
                    'message': 'Order placement returned None'
                }, status=500)

        except Exception as e:
            logger.error(f"Test trade error: {e}", exc_info=True)
            return Response({'status': 'error', 'message': str(e)}, status=500)


class AnalyzeView(APIView):
    """Run trading analysis cycle - triggered by Cloud Scheduler."""

    permission_classes = [AllowAny]  # Called by Cloud Scheduler

    def post(self, request):
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
                return Response({'status': 'no_response', 'message': 'No LLM response'})
            
            # Filter and execute trades
            valid_trades = analyst.filter_by_confidence(response.trades)
            
            if not valid_trades:
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
            logger.error(f"Analysis error: {e}")
            return Response({'status': 'error', 'message': str(e)}, status=500)
