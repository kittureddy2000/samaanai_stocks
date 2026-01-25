"""Main entry point for the LLM Trading Agent."""

import argparse
import time
from datetime import datetime
import schedule
from loguru import logger

# Setup paths
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config, validate_config
from utils.logger import setup_logger
from utils.database import db
from utils.slack import slack, notify_trade
from llm.analyst import TradingAnalyst
from trading.broker_factory import get_broker, BrokerConnectionError
from trading.order_manager import OrderManager
from trading.portfolio import PortfolioTracker
from trading.risk_controls import RiskManager


class TradingAgent:
    """Main trading agent that orchestrates the entire system."""

    def __init__(self):
        """Initialize the trading agent."""
        logger.info("=" * 60)
        logger.info("🤖 LLM TRADING AGENT STARTING")
        logger.info("=" * 60)

        self.analyst = TradingAnalyst()
        self.broker = get_broker()  # Uses IBKR broker
        self.order_manager = OrderManager()
        self.portfolio_tracker = PortfolioTracker()
        self.risk_manager = RiskManager()

        self.running = False
        self.analysis_count = 0

    def test_connections(self) -> bool:
        """Test all API connections.

        Returns:
            True if all connections successful
        """
        logger.info("Testing connections...")

        # Test IBKR connection
        if not self.broker.test_connection():
            return False

        # Test Gemini LLM
        if not self.analyst.test_connection():
            return False

        logger.info("✅ All connections successful!")
        return True

    def run_analysis_cycle(self):
        """Run a single analysis and trading cycle."""
        self.analysis_count += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 ANALYSIS CYCLE #{self.analysis_count}")
        logger.info(f"{'='*60}")

        try:
            # Check if market is open
            if not self.broker.is_market_open():
                market_hours = self.broker.get_market_hours()
                logger.info(f"Market is closed. Next open: {market_hours.get('next_open', 'Unknown')}")
                return

            # Get account info
            account = self.broker.get_account()
            if not account:
                logger.error("Failed to get account info")
                return

            # Get current positions
            positions = self.broker.get_positions()

            # Display current portfolio
            logger.info(self.portfolio_tracker.format_portfolio_display())

            # Display risk status
            logger.info(self.risk_manager.format_risk_display(account))

            # Run LLM analysis
            logger.info("\n🧠 Running LLM Analysis...")
            response = self.analyst.analyze_and_recommend(
                cash=account.cash,
                portfolio_value=account.portfolio_value,
                positions=[{
                    'symbol': p.symbol,
                    'qty': p.qty,
                    'avg_entry_price': p.avg_entry_price,
                    'current_price': p.current_price,
                    'market_value': p.market_value,
                    'unrealized_pl': p.unrealized_pl,
                    'unrealized_plpc': p.unrealized_plpc
                } for p in positions]
            )

            if not response:
                logger.warning("No response from LLM")
                return

            # Log the analysis
            logger.info(f"\n📝 Analysis Summary: {response.analysis_summary}")
            logger.info(f"🎯 Risk Assessment: {response.risk_assessment}")
            logger.info(f"💡 Recommendation: {response.portfolio_recommendation}")

            # Filter trades by confidence
            valid_trades = self.analyst.filter_by_confidence(response.trades)

            if not valid_trades:
                logger.info("No high-confidence trades recommended")

                # Record analysis to database
                db.record_analysis(
                    watchlist=config.trading.watchlist,
                    market_data={},
                    llm_response={
                        'analysis_summary': response.analysis_summary,
                        'risk_assessment': response.risk_assessment,
                        'portfolio_recommendation': response.portfolio_recommendation,
                        'trades': []
                    },
                    trades_recommended=len(response.trades),
                    trades_executed=0
                )
                return

            # Execute trades
            logger.info(f"\n🚀 Executing {len(valid_trades)} trade(s)...")
            executed = self.order_manager.execute_trades(valid_trades)

            # Send Slack notifications for each trade
            for trade in valid_trades:
                notify_trade({
                    'action': trade.action,
                    'symbol': trade.symbol,
                    'quantity': trade.quantity,
                    'confidence': trade.confidence,
                    'reasoning': trade.reasoning
                })

            # Record trades to database
            for i, trade in enumerate(valid_trades):
                order_info = executed[i] if i < len(executed) else None
                db.record_trade(
                    symbol=trade.symbol,
                    action=trade.action,
                    quantity=trade.quantity,
                    order_type=trade.order_type,
                    limit_price=trade.limit_price,
                    confidence=trade.confidence,
                    reasoning=trade.reasoning,
                    order_id=order_info.get('id', '') if order_info else '',
                    status=order_info.get('status', 'UNKNOWN') if order_info else 'FAILED',
                    llm_analysis={
                        'analysis_summary': response.analysis_summary,
                        'risk_assessment': response.risk_assessment
                    }
                )

            # Record analysis
            db.record_analysis(
                watchlist=config.trading.watchlist,
                market_data={},
                llm_response={
                    'analysis_summary': response.analysis_summary,
                    'risk_assessment': response.risk_assessment,
                    'trades': [
                        {
                            'symbol': t.symbol,
                            'action': t.action,
                            'quantity': t.quantity,
                            'confidence': t.confidence
                        }
                        for t in valid_trades
                    ]
                },
                trades_recommended=len(response.trades),
                trades_executed=len(executed)
            )

            logger.info(f"✅ Cycle complete: {len(executed)}/{len(valid_trades)} trades executed")

        except Exception as e:
            logger.exception(f"Error in analysis cycle: {e}")

    def run_single(self):
        """Run a single analysis cycle (for testing)."""
        self.run_analysis_cycle()

    def start(self):
        """Start the trading agent with scheduling."""
        logger.info(f"Starting scheduled trading (every {config.trading.analysis_interval_minutes} minutes)")

        self.running = True

        # Notify Slack that agent started
        slack.notify_agent_started()

        # Schedule the analysis
        schedule.every(config.trading.analysis_interval_minutes).minutes.do(self.run_analysis_cycle)

        # Run immediately on start
        self.run_analysis_cycle()

        # Keep running
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def stop(self, reason: str = "Normal shutdown"):
        """Stop the trading agent."""
        logger.info("Stopping trading agent...")
        self.running = False
        if self.broker:
            self.broker.disconnect()
        slack.notify_agent_stopped(reason)
        logger.info("Trading agent stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='LLM Trading Agent')
    parser.add_argument('--test-connection', action='store_true', help='Test API connections')
    parser.add_argument('--single-run', action='store_true', help='Run a single analysis cycle')
    parser.add_argument('--portfolio', action='store_true', help='Display current portfolio')
    parser.add_argument('--history', action='store_true', help='Show recent trade history')

    args = parser.parse_args()

    # Validate configuration
    if not validate_config():
        logger.error("Configuration validation failed. Please check your .env file.")
        sys.exit(1)

    try:
        agent = TradingAgent()
    except BrokerConnectionError as e:
        logger.error(f"❌ Failed to connect to IBKR: {e}")
        sys.exit(1)

    if args.test_connection:
        success = agent.test_connections()
        sys.exit(0 if success else 1)

    if args.portfolio:
        print(agent.portfolio_tracker.format_portfolio_display())
        account = agent.broker.get_account()
        if account:
            print(agent.risk_manager.format_risk_display(account))
        sys.exit(0)

    if args.history:
        trades = db.get_recent_trades(10)
        print("\n📜 Recent Trades:")
        print("=" * 60)
        if not trades:
            print("No trades recorded yet")
        else:
            for t in trades:
                print(f"  {t['timestamp'][:19]} | {t['action']:4} {t['quantity']:3} {t['symbol']:5} | {t['status']}")
        print("=" * 60)
        sys.exit(0)

    if args.single_run:
        agent.run_single()
        sys.exit(0)

    # Default: run the agent with scheduling
    try:
        agent.start()
    except KeyboardInterrupt:
        logger.info("\n⚠️ Keyboard interrupt received")
        agent.stop()


if __name__ == "__main__":
    main()
