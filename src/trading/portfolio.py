"""Portfolio tracker for monitoring positions and P&L."""

from typing import Dict, Any, List, Optional
from datetime import datetime, date
from loguru import logger

from .broker_factory import get_broker


class PortfolioTracker:
    """Tracks portfolio performance and positions."""

    def __init__(self):
        """Initialize the portfolio tracker."""
        self.broker = get_broker()
        self.daily_snapshots: List[Dict[str, Any]] = []
        self.starting_value: Optional[float] = None
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get current portfolio summary.
        
        Returns:
            Portfolio summary dictionary
        """
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        
        if not account:
            return {'error': 'Failed to get account info'}
        
        # Calculate totals
        total_unrealized_pl = sum(p['unrealized_pl'] for p in positions)
        total_unrealized_plpc = (
            (total_unrealized_pl / account['portfolio_value']) * 100
            if account['portfolio_value'] > 0 else 0
        )
        
        # Calculate daily change
        daily_change = account['equity'] - account['last_equity']
        daily_change_pct = (
            (daily_change / account['last_equity']) * 100
            if account['last_equity'] > 0 else 0
        )
        
        return {
            'timestamp': datetime.now().isoformat(),
            'account': {
                'cash': account['cash'],
                'portfolio_value': account['portfolio_value'],
                'equity': account['equity'],
                'buying_power': account['buying_power'],
                'daytrade_count': account['daytrade_count']
            },
            'performance': {
                'daily_change': daily_change,
                'daily_change_pct': daily_change_pct,
                'unrealized_pl': total_unrealized_pl,
                'unrealized_pl_pct': total_unrealized_plpc
            },
            'positions': {
                'count': len(positions),
                'total_market_value': sum(p['market_value'] for p in positions),
                'details': positions
            }
        }
    
    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all positions.
        
        Returns:
            List of position summaries
        """
        positions = self.broker.get_positions()
        
        summaries = []
        for pos in positions:
            pnl_sign = '+' if pos['unrealized_pl'] >= 0 else ''
            summaries.append({
                'symbol': pos['symbol'],
                'quantity': pos['qty'],
                'entry_price': pos['avg_entry_price'],
                'current_price': pos['current_price'],
                'market_value': pos['market_value'],
                'pnl': pos['unrealized_pl'],
                'pnl_pct': pos['unrealized_plpc'] * 100,
                'pnl_display': f"{pnl_sign}${pos['unrealized_pl']:.2f} ({pnl_sign}{pos['unrealized_plpc']*100:.2f}%)"
            })
        
        return summaries
    
    def record_snapshot(self) -> Dict[str, Any]:
        """Record a snapshot of current portfolio state.
        
        Returns:
            Snapshot data
        """
        summary = self.get_portfolio_summary()
        
        snapshot = {
            'date': date.today().isoformat(),
            'timestamp': datetime.now().isoformat(),
            'portfolio_value': summary['account']['portfolio_value'],
            'cash': summary['account']['cash'],
            'equity': summary['account']['equity'],
            'positions_count': summary['positions']['count'],
            'unrealized_pl': summary['performance']['unrealized_pl']
        }
        
        self.daily_snapshots.append(snapshot)
        
        # Set starting value if not set
        if self.starting_value is None:
            self.starting_value = summary['account']['portfolio_value']
        
        return snapshot
    
    def get_total_return(self) -> Dict[str, Any]:
        """Calculate total return since tracking started.
        
        Returns:
            Return statistics
        """
        if self.starting_value is None:
            self.record_snapshot()
        
        account = self.broker.get_account()
        if not account:
            return {'error': 'Failed to get account'}
        
        current_value = account['portfolio_value']
        total_return = current_value - self.starting_value
        total_return_pct = (
            (total_return / self.starting_value) * 100
            if self.starting_value > 0 else 0
        )
        
        return {
            'starting_value': self.starting_value,
            'current_value': current_value,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'snapshots_count': len(self.daily_snapshots)
        }
    
    def format_portfolio_display(self) -> str:
        """Format portfolio for display.
        
        Returns:
            Formatted string
        """
        summary = self.get_portfolio_summary()
        
        if 'error' in summary:
            return f"Error: {summary['error']}"
        
        lines = [
            "=" * 50,
            "📊 PORTFOLIO SUMMARY",
            "=" * 50,
            "",
            "💰 Account:",
            f"   Cash: ${summary['account']['cash']:,.2f}",
            f"   Portfolio Value: ${summary['account']['portfolio_value']:,.2f}",
            f"   Buying Power: ${summary['account']['buying_power']:,.2f}",
            "",
            "📈 Performance:",
            f"   Daily Change: ${summary['performance']['daily_change']:+,.2f} ({summary['performance']['daily_change_pct']:+.2f}%)",
            f"   Unrealized P&L: ${summary['performance']['unrealized_pl']:+,.2f} ({summary['performance']['unrealized_pl_pct']:+.2f}%)",
            ""
        ]
        
        if summary['positions']['count'] > 0:
            lines.append(f"📋 Positions ({summary['positions']['count']}):")
            for pos in summary['positions']['details']:
                pnl_sign = '+' if pos['unrealized_pl'] >= 0 else ''
                lines.append(
                    f"   {pos['symbol']}: {pos['qty']:.0f} shares @ ${pos['avg_entry_price']:.2f} "
                    f"→ ${pos['current_price']:.2f} ({pnl_sign}${pos['unrealized_pl']:.2f})"
                )
        else:
            lines.append("📋 Positions: None (100% cash)")
        
        lines.append("")
        lines.append("=" * 50)
        
        return "\n".join(lines)
