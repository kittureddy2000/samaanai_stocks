"""Trading analyst that orchestrates data gathering and LLM analysis."""

from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

from .llm_client import LLMClient, LLMResponse, TradeDecision
from .prompts import get_system_prompt, build_analysis_prompt

import sys
sys.path.append(str(__file__).rsplit("/", 3)[0])
from config import config
from data.data_aggregator import DataAggregator


class TradingAnalyst:
    """Orchestrates market analysis and trade decision making."""
    
    def __init__(self):
        """Initialize the trading analyst."""
        self.llm_client = LLMClient()
        self.data_aggregator = DataAggregator()
    
    def analyze_and_recommend(
        self,
        cash: float,
        portfolio_value: float,
        positions: List[Dict[str, Any]],
        watchlist: List[str] = None
    ) -> Optional[LLMResponse]:
        """Perform full analysis and get trade recommendations.
        
        Args:
            cash: Available cash to trade
            portfolio_value: Total portfolio value
            positions: List of current positions
            watchlist: Optional list of symbols (uses config if not provided)
            
        Returns:
            LLMResponse with trade recommendations
        """
        if watchlist is None:
            watchlist = config.trading.watchlist
        
        logger.info("Starting market analysis...")
        
        # Step 1: Gather market data
        logger.info("Step 1: Fetching market data...")
        analysis = self.data_aggregator.get_watchlist_analysis(watchlist)
        
        # Step 2: Format data for LLM
        logger.info("Step 2: Formatting data for LLM...")
        market_analysis = self.data_aggregator.format_for_llm(analysis)
        
        # Step 3: Build prompt
        logger.info("Step 3: Building analysis prompt...")
        user_prompt = build_analysis_prompt(
            timestamp=datetime.now().isoformat(),
            cash=cash,
            portfolio_value=portfolio_value,
            positions=positions,
            market_analysis=market_analysis,
            max_position_pct=config.trading.max_position_pct * 100,
            min_confidence=config.trading.min_confidence * 100,
            stop_loss_pct=config.trading.default_stop_loss_pct * 100,
            take_profit_pct=config.trading.default_take_profit_pct * 100
        )
        
        # Step 4: Get LLM analysis with strategy-specific prompt
        logger.info(f"Step 4: Requesting LLM analysis (strategy: {config.trading.strategy})...")
        system_prompt = get_system_prompt(config.trading.strategy)
        response = self.llm_client.analyze_market(system_prompt, user_prompt)
        
        if response:
            logger.info(f"Analysis complete: {response.analysis_summary}")
            logger.info(f"Risk assessment: {response.risk_assessment}")
            logger.info(f"Recommendations: {len(response.trades)} trade(s)")
        else:
            logger.error("Failed to get LLM analysis")
        
        return response
    
    def filter_by_confidence(
        self, 
        trades: List[TradeDecision],
        min_confidence: float = None
    ) -> List[TradeDecision]:
        """Filter trades by minimum confidence threshold.
        
        Args:
            trades: List of trade decisions
            min_confidence: Minimum confidence (uses config if not provided)
            
        Returns:
            Filtered list of trades
        """
        if min_confidence is None:
            min_confidence = config.trading.min_confidence
        
        filtered = [t for t in trades if t.confidence >= min_confidence]
        
        if len(filtered) < len(trades):
            logger.info(
                f"Filtered {len(trades) - len(filtered)} trade(s) "
                f"below {min_confidence:.0%} confidence threshold"
            )
        
        return filtered
    
    def validate_trades(
        self,
        trades: List[TradeDecision],
        cash: float,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> List[TradeDecision]:
        """Validate and adjust trades based on constraints.
        
        Args:
            trades: List of trade decisions
            cash: Available cash
            portfolio_value: Total portfolio value
            current_positions: Dict of symbol -> quantity held
            
        Returns:
            Validated list of trades
        """
        validated = []
        remaining_cash = cash
        max_position_value = portfolio_value * config.trading.max_position_pct
        
        for trade in trades:
            # Skip invalid actions
            if trade.action not in ['BUY', 'SELL']:
                continue
            
            # For SELL, verify we have the position
            if trade.action == 'SELL':
                held = current_positions.get(trade.symbol, 0)
                if held <= 0:
                    logger.warning(f"Cannot sell {trade.symbol}: no position held")
                    continue
                # Adjust quantity if trying to sell more than held
                if trade.quantity > held:
                    logger.info(f"Adjusting sell quantity for {trade.symbol}: {trade.quantity} -> {held}")
                    trade.quantity = int(held)
            
            # For BUY, verify we have enough cash
            if trade.action == 'BUY':
                # Estimate cost (we'd need current price, but we can use limit_price or fetch)
                estimated_cost = trade.quantity * (trade.limit_price or 0)
                
                if estimated_cost > remaining_cash:
                    logger.warning(
                        f"Insufficient cash for {trade.symbol}: "
                        f"need ${estimated_cost:.2f}, have ${remaining_cash:.2f}"
                    )
                    continue
                
                if estimated_cost > max_position_value:
                    logger.warning(
                        f"Trade exceeds max position size for {trade.symbol}: "
                        f"${estimated_cost:.2f} > ${max_position_value:.2f}"
                    )
                    continue
                
                remaining_cash -= estimated_cost
            
            validated.append(trade)
        
        logger.info(f"Validated {len(validated)}/{len(trades)} trades")
        return validated
    
    def test_connection(self) -> bool:
        """Test all connections (Alpaca data + OpenAI).
        
        Returns:
            True if all connections successful
        """
        logger.info("Testing connections...")
        
        # Test Alpaca data
        try:
            price = self.data_aggregator.market_client.get_current_price("AAPL")
            if price:
                logger.info(f"✅ Alpaca data connection OK (AAPL: ${price})")
            else:
                logger.error("❌ Alpaca data connection failed")
                return False
        except Exception as e:
            logger.error(f"❌ Alpaca data connection failed: {e}")
            return False
        
        # Test OpenAI
        if self.llm_client.test_connection():
            logger.info("✅ OpenAI connection OK")
        else:
            logger.error("❌ OpenAI connection failed")
            return False
        
        return True
