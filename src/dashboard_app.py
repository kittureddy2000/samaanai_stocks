"""Web dashboard for the LLM Trading Agent."""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from trading.alpaca_client import AlpacaTradingClient
from trading.portfolio import PortfolioTracker
from trading.risk_controls import RiskManager
from data.data_aggregator import DataAggregator
from utils.database import db
from utils.auth import init_auth

app = Flask(__name__, 
            template_folder='dashboard/templates',
            static_folder='dashboard/static')
CORS(app, supports_credentials=True)

# Initialize authentication (Google OAuth)
init_auth(app)

# Initialize clients
trading_client = AlpacaTradingClient()
portfolio_tracker = PortfolioTracker()
risk_manager = RiskManager()
data_aggregator = DataAggregator()


# Health check for Cloud Run
@app.route('/health')
def health_check():
    """Health check endpoint for Cloud Run."""
    return jsonify({'status': 'healthy', 'service': 'trading-api'}), 200


@app.route('/api/analyze', methods=['POST'])
def run_analysis():
    """Run trading analysis cycle - triggered by Cloud Scheduler."""
    try:
        from llm.analyst import TradingAnalyst
        from trading.order_manager import OrderManager
        from utils.slack import slack, notify_trade
        
        # Check if market is open
        if not trading_client.is_market_open():
            return jsonify({
                'status': 'skipped',
                'message': 'Market is closed'
            }), 200
        
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
            return jsonify({'status': 'no_response', 'message': 'No LLM response'}), 200
        
        # Filter and execute trades
        valid_trades = analyst.filter_by_confidence(response.trades)
        
        if not valid_trades:
            return jsonify({
                'status': 'no_trades',
                'message': 'No high-confidence trades',
                'analysis': response.analysis_summary
            }), 200
        
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
        
        return jsonify({
            'status': 'success',
            'trades_executed': len(executed),
            'trades': [{'symbol': t.symbol, 'action': t.action, 'quantity': t.quantity} for t in valid_trades],
            'analysis': response.analysis_summary
        }), 200
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/')
def index():
    """Render the main dashboard."""
    return render_template('index.html')


@app.route('/api/portfolio')
def get_portfolio():
    """Get current portfolio data."""
    try:
        account = trading_client.get_account()
        positions = trading_client.get_positions()
        
        if not account:
            return jsonify({'error': 'Failed to get account'}), 500
        
        # Calculate daily change
        daily_change = account['equity'] - account['last_equity']
        daily_change_pct = (daily_change / account['last_equity'] * 100) if account['last_equity'] > 0 else 0
        
        return jsonify({
            'account': {
                'cash': account['cash'],
                'portfolio_value': account['portfolio_value'],
                'equity': account['equity'],
                'buying_power': account['buying_power']
            },
            'performance': {
                'daily_change': daily_change,
                'daily_change_pct': daily_change_pct
            },
            'positions': positions,
            'positions_count': len(positions)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/risk')
def get_risk():
    """Get current risk status."""
    try:
        account = trading_client.get_account()
        if not account:
            return jsonify({'error': 'Failed to get account'}), 500
        
        risk_status = risk_manager.get_risk_status(account)
        return jsonify(risk_status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/market')
def get_market():
    """Get market status."""
    try:
        is_open = trading_client.is_market_open()
        hours = trading_client.get_market_hours()
        return jsonify({
            'is_open': is_open,
            'next_open': hours.get('next_open') if hours else None,
            'next_close': hours.get('next_close') if hours else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist')
def get_watchlist():
    """Get current prices for watchlist."""
    try:
        prices = data_aggregator.market_client.get_current_prices(config.trading.watchlist)
        watchlist = []
        for symbol in config.trading.watchlist:
            watchlist.append({
                'symbol': symbol,
                'price': prices.get(symbol, 0)
            })
        return jsonify({'watchlist': watchlist})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trades')
def get_trades():
    """Get recent trade history from Alpaca."""
    try:
        # Fetch order history directly from Alpaca API
        orders = trading_client.get_orders_history(limit=30)
        
        # Format for display
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
                'filled_at': order.get('filled_at')
            })
        
        return jsonify({'trades': trades})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config')
def get_config():
    """Get trading configuration."""
    return jsonify({
        'watchlist': config.trading.watchlist,
        'analysis_interval': config.trading.analysis_interval_minutes,
        'max_position_pct': config.trading.max_position_pct * 100,
        'max_daily_loss_pct': config.trading.max_daily_loss_pct * 100,
        'min_confidence': config.trading.min_confidence * 100,
        'stop_loss_pct': config.trading.default_stop_loss_pct * 100,
        'take_profit_pct': config.trading.default_take_profit_pct * 100
    })


@app.route('/api/indicators')
def get_indicators():
    """Get technical indicators for watchlist symbols."""
    try:
        indicators = []
        for symbol in config.trading.watchlist:
            try:
                # Get stock analysis which includes technical indicators
                data = data_aggregator.get_stock_analysis(symbol, days=30)
                if data and 'technical' in data:
                    tech = data['technical']
                    indicators.append({
                        'symbol': symbol,
                        'price': data.get('current_price', 0),
                        'change_pct': data.get('price_change_pct', 0),
                        'rsi': tech.get('rsi'),
                        'rsi_signal': tech.get('rsi_signal', 'NEUTRAL'),
                        'macd': tech.get('macd'),
                        'macd_signal': tech.get('macd_signal'),
                        'macd_histogram': tech.get('macd_histogram'),
                        'macd_trend': tech.get('macd_trend', 'NEUTRAL'),
                        'sma_20': tech.get('sma_20'),
                        'sma_50': tech.get('sma_50'),
                        'ema_12': tech.get('ema_12'),
                        'bb_upper': tech.get('bb_upper'),
                        'bb_middle': tech.get('bb_middle'),
                        'bb_lower': tech.get('bb_lower'),
                        'bb_signal': tech.get('bb_signal', 'NEUTRAL'),
                        'volume_signal': tech.get('volume_signal', 'NORMAL'),
                        'overall_signal': data.get('signals', {}).get('overall', 'NEUTRAL')
                    })
                else:
                    indicators.append({
                        'symbol': symbol,
                        'price': data.get('current_price', 0) if data else 0,
                        'rsi': None,
                        'rsi_signal': 'N/A',
                        'macd': None,
                        'macd_trend': 'N/A',
                        'overall_signal': 'NO DATA'
                    })
            except Exception as e:
                indicators.append({
                    'symbol': symbol,
                    'error': str(e)
                })
        
        return jsonify({'indicators': indicators})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("🚀 Starting Trading Dashboard...")
    print("📊 Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
