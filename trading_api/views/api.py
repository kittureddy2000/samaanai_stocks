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


# Import trading services from src (keeping existing logic)
# These will be imported when needed to avoid circular imports
def get_trading_client():
    """Get Alpaca trading client."""
    from trading_api.services.alpaca_client import AlpacaTradingClient
    return AlpacaTradingClient()


def get_risk_manager():
    """Get risk manager."""
    from trading_api.services.risk_controls import RiskManager
    return RiskManager()


def get_data_aggregator():
    """Get data aggregator."""
    from trading_api.services.data_aggregator import DataAggregator
    return DataAggregator()


class PortfolioView(APIView):
    """Get current portfolio data."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            trading_client = get_trading_client()
            account = trading_client.get_account()
            positions = trading_client.get_positions()
            
            if not account:
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
            logger.error(f"Portfolio error: {e}")
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
        return Response({
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
            from trading_api.services.technical_indicators import TechnicalIndicators
            
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


class AnalyzeView(APIView):
    """Run trading analysis cycle - triggered by Cloud Scheduler."""
    
    permission_classes = [AllowAny]  # Called by Cloud Scheduler
    
    def post(self, request):
        try:
            from trading_api.services.analyst import TradingAnalyst
            from trading_api.services.order_manager import OrderManager
            from trading_api.services.slack import notify_trade
            
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
