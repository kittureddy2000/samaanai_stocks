"""Order manager for executing trades based on LLM decisions."""

from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

from .broker_factory import get_broker
from .risk_controls import RiskManager

import sys
sys.path.append(str(__file__).rsplit("/", 3)[0])
from llm.llm_client import TradeDecision


class OrderManager:
    """Manages order execution and tracking."""

    def __init__(self):
        """Initialize the order manager."""
        self.broker = get_broker()
        self.risk_manager = RiskManager()
        self.executed_orders: List[Dict[str, Any]] = []
    
    def execute_trade(self, decision: TradeDecision) -> Optional[Dict[str, Any]]:
        """Execute a single trade based on LLM decision.
        
        Args:
            decision: TradeDecision from the LLM
            
        Returns:
            Order info dictionary or None if failed/rejected
        """
        # Skip HOLD decisions
        if decision.action == 'HOLD':
            logger.info(f"Holding {decision.symbol} - no action taken")
            return None
        
        # Get current account status for risk checks
        account = self.broker.get_account()
        if not account:
            logger.error("Cannot execute trade: failed to get account info")
            return None
        
        # Risk check
        risk_result = self.risk_manager.check_trade(
            decision=decision,
            account=account,
            current_positions=self.broker.get_positions()
        )
        
        if not risk_result['approved']:
            logger.warning(f"Trade rejected by risk manager: {risk_result['reason']}")
            return {
                'status': 'REJECTED',
                'symbol': decision.symbol,
                'action': decision.action,
                'reason': risk_result['reason']
            }
        
        # Execute the order
        order = None
        
        if decision.order_type == 'limit' and decision.limit_price:
            order = self.broker.place_limit_order(
                symbol=decision.symbol,
                qty=decision.quantity,
                side=decision.action.lower(),
                limit_price=decision.limit_price
            )
        else:
            order = self.broker.place_market_order(
                symbol=decision.symbol,
                qty=decision.quantity,
                side=decision.action.lower()
            )
        
        if order:
            # Record the executed order
            execution_record = {
                'timestamp': datetime.now().isoformat(),
                'decision': {
                    'action': decision.action,
                    'symbol': decision.symbol,
                    'quantity': decision.quantity,
                    'confidence': decision.confidence,
                    'reasoning': decision.reasoning
                },
                'order': order
            }
            self.executed_orders.append(execution_record)
            
            logger.info(f"✅ Order executed: {decision.action} {decision.quantity} {decision.symbol}")
            logger.info(f"   Order ID: {order['id']}")
            logger.info(f"   Status: {order['status']}")
            
        return order
    
    def execute_trades(self, decisions: List[TradeDecision]) -> List[Dict[str, Any]]:
        """Execute multiple trades.
        
        Args:
            decisions: List of TradeDecision objects
            
        Returns:
            List of order results
        """
        results = []
        
        for decision in decisions:
            result = self.execute_trade(decision)
            if result:
                results.append(result)
        
        logger.info(f"Executed {len(results)}/{len(decisions)} trades")
        return results
    
    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get history of executed orders.
        
        Returns:
            List of execution records
        """
        return self.executed_orders.copy()
    
    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Check the status of an order.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Order info or None
        """
        return self.broker.get_order(order_id)
    
    def cancel_pending_orders(self) -> bool:
        """Cancel all pending orders.
        
        Returns:
            True if successful
        """
        return self.broker.cancel_all_orders()
