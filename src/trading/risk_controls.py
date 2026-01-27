"""Risk management controls for the trading agent."""

from typing import Dict, Any, List, Optional
from datetime import datetime, date
from loguru import logger

import sys
sys.path.append(str(__file__).rsplit("/", 3)[0])
from config import config
from llm.llm_client import TradeDecision


class RiskManager:
    """Manages risk controls and validates trades."""
    
    def __init__(self):
        """Initialize risk manager."""
        self.daily_loss: float = 0.0
        self.daily_trades: int = 0
        self.last_reset_date: date = date.today()
        self.kill_switch_active: bool = False
    
    def _reset_daily_counters(self):
        """Reset daily counters if it's a new day."""
        today = date.today()
        if today > self.last_reset_date:
            self.daily_loss = 0.0
            self.daily_trades = 0
            self.last_reset_date = today
            logger.info("Daily risk counters reset")
    
    def check_trade(
        self,
        decision: TradeDecision,
        account,
        current_positions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Validate a trade against risk controls.

        Args:
            decision: The trade decision to validate
            account: Current account info (dict or AccountInfo dataclass)
            current_positions: List of current positions

        Returns:
            Dictionary with 'approved' boolean and 'reason' string
        """
        self._reset_daily_counters()

        # Check kill switch
        if self.kill_switch_active:
            return {
                'approved': False,
                'reason': 'Kill switch is active - all trading halted'
            }

        # Handle both dict and dataclass account types
        if hasattr(account, 'portfolio_value'):
            # AccountInfo dataclass
            portfolio_value = account.portfolio_value
            cash = account.cash
        else:
            # Dict
            portfolio_value = account.get('portfolio_value', 0)
            cash = account.get('cash', 0)
        
        # Check 1: Confidence threshold
        if decision.confidence < config.trading.min_confidence:
            return {
                'approved': False,
                'reason': f'Confidence {decision.confidence:.0%} below threshold {config.trading.min_confidence:.0%}'
            }
        
        # Check 2: Daily loss limit
        max_daily_loss = portfolio_value * config.trading.max_daily_loss_pct
        if self.daily_loss >= max_daily_loss:
            return {
                'approved': False,
                'reason': f'Daily loss limit reached: ${self.daily_loss:.2f} >= ${max_daily_loss:.2f}'
            }
        
        # Check 3: Position size limit (for BUY orders)
        if decision.action == 'BUY':
            max_position_value = portfolio_value * config.trading.max_position_pct
            
            # Estimate trade value
            estimated_price = decision.limit_price if decision.limit_price else self._get_estimated_price(decision.symbol, current_positions)
            if estimated_price:
                trade_value = decision.quantity * estimated_price
                
                if trade_value > max_position_value:
                    return {
                        'approved': False,
                        'reason': f'Trade value ${trade_value:.2f} exceeds max position size ${max_position_value:.2f}'
                    }
                
                if trade_value > cash:
                    return {
                        'approved': False,
                        'reason': f'Insufficient cash: need ${trade_value:.2f}, have ${cash:.2f}'
                    }
        
        # Check 4: Can't sell what you don't have
        if decision.action == 'SELL':
            held_qty = self._get_position_quantity(decision.symbol, current_positions)
            if held_qty <= 0:
                return {
                    'approved': False,
                    'reason': f'No position in {decision.symbol} to sell'
                }
            if decision.quantity > held_qty:
                return {
                    'approved': False,
                    'reason': f'Cannot sell {decision.quantity} shares of {decision.symbol}, only hold {held_qty}'
                }
        
        # Check 5: Pattern Day Trading warning (not blocking, just logging)
        # Note: IBKR AccountInfo doesn't provide PDT info, so we check if it's a dict
        if isinstance(account, dict):
            daytrade_count = account.get('daytrade_count', 0)
            if daytrade_count >= 3:
                logger.warning(
                    f"PDT Warning: {daytrade_count} day trades this week. "
                    f"PDT flag: {account.get('pattern_day_trader', False)}"
                )
        
        # All checks passed
        return {
            'approved': True,
            'reason': 'All risk checks passed'
        }
    
    def _get_estimated_price(
        self, 
        symbol: str, 
        positions: List[Dict[str, Any]]
    ) -> Optional[float]:
        """Get estimated price from positions or return None.
        
        Args:
            symbol: Stock symbol
            positions: List of current positions
            
        Returns:
            Current price if in positions, else None
        """
        for pos in positions:
            if pos['symbol'] == symbol:
                return pos.get('current_price')
        return None
    
    def _get_position_quantity(
        self,
        symbol: str,
        positions: List[Dict[str, Any]]
    ) -> float:
        """Get quantity held for a symbol.
        
        Args:
            symbol: Stock symbol
            positions: List of current positions
            
        Returns:
            Quantity held (0 if no position)
        """
        for pos in positions:
            if pos['symbol'] == symbol:
                return pos.get('qty', 0)
        return 0
    
    def record_trade_result(self, realized_pl: float):
        """Record the result of a trade for daily tracking.
        
        Args:
            realized_pl: Realized profit/loss from the trade
        """
        self._reset_daily_counters()
        self.daily_trades += 1
        
        if realized_pl < 0:
            self.daily_loss += abs(realized_pl)
            logger.info(f"Daily loss updated: ${self.daily_loss:.2f}")
    
    def activate_kill_switch(self, reason: str = "Manual activation"):
        """Activate the kill switch to halt all trading.
        
        Args:
            reason: Reason for activation
        """
        self.kill_switch_active = True
        logger.warning(f"🛑 KILL SWITCH ACTIVATED: {reason}")
    
    def deactivate_kill_switch(self):
        """Deactivate the kill switch."""
        self.kill_switch_active = False
        logger.info("✅ Kill switch deactivated - trading resumed")
    
    def get_risk_status(self, account) -> Dict[str, Any]:
        """Get current risk status.

        Args:
            account: Current account info (dict or AccountInfo dataclass)

        Returns:
            Risk status dictionary
        """
        self._reset_daily_counters()

        # Handle both dict and dataclass account types
        if hasattr(account, 'portfolio_value'):
            portfolio_value = account.portfolio_value
        else:
            portfolio_value = account.get('portfolio_value', 0)
        max_daily_loss = portfolio_value * config.trading.max_daily_loss_pct
        daily_loss_pct = (self.daily_loss / portfolio_value * 100) if portfolio_value > 0 else 0
        
        # Calculate risk level
        if self.kill_switch_active:
            risk_level = 'HALTED'
        elif daily_loss_pct >= (config.trading.max_daily_loss_pct * 100 * 0.8):  # 80% of limit
            risk_level = 'HIGH'
        elif daily_loss_pct >= (config.trading.max_daily_loss_pct * 100 * 0.5):  # 50% of limit
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
        
        return {
            'kill_switch_active': self.kill_switch_active,
            'daily_trades': self.daily_trades,
            'daily_loss': self.daily_loss,
            'daily_loss_pct': daily_loss_pct,
            'max_daily_loss': max_daily_loss,
            'daily_loss_remaining': max_daily_loss - self.daily_loss,
            'risk_level': risk_level,
            'max_position_value': portfolio_value * config.trading.max_position_pct,
            'min_confidence': config.trading.min_confidence
        }
    
    def format_risk_display(self, account) -> str:
        """Format risk status for display.

        Args:
            account: Current account info (dict or AccountInfo dataclass)

        Returns:
            Formatted string
        """
        status = self.get_risk_status(account)
        
        risk_emoji = {
            'LOW': '🟢',
            'MEDIUM': '🟡',
            'HIGH': '🔴',
            'HALTED': '⛔'
        }
        
        lines = [
            "=" * 40,
            "🛡️ RISK STATUS",
            "=" * 40,
            f"Risk Level: {risk_emoji.get(status['risk_level'], '⚪')} {status['risk_level']}",
            f"Kill Switch: {'ACTIVE ⛔' if status['kill_switch_active'] else 'Inactive ✅'}",
            "",
            f"Daily Trades: {status['daily_trades']}",
            f"Daily Loss: ${status['daily_loss']:.2f} ({status['daily_loss_pct']:.2f}%)",
            f"Loss Limit: ${status['max_daily_loss']:.2f} ({config.trading.max_daily_loss_pct*100:.1f}%)",
            f"Remaining: ${status['daily_loss_remaining']:.2f}",
            "",
            f"Max Position Size: ${status['max_position_value']:.2f}",
            f"Min Confidence: {status['min_confidence']:.0%}",
            "=" * 40
        ]
        
        return "\n".join(lines)
