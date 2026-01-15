"""Trade model for storing trade history in the database."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from utils.database_sql import Base


class Trade(Base):
    """Trade model for recording executed trades."""
    
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # Optional: link to user
    
    # Trade details
    symbol = Column(String(20), nullable=False, index=True)
    action = Column(String(10), nullable=False)  # BUY, SELL
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    total_value = Column(Float, nullable=False)
    
    # Order details
    order_id = Column(String(100), nullable=True)
    order_type = Column(String(20), default='market')  # market, limit
    status = Column(String(20), default='executed')
    
    # Risk management
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    # LLM analysis
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    executed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Trade {self.action} {self.quantity} {self.symbol} @ ${self.price}>"
    
    def to_dict(self):
        """Convert trade to dictionary for API responses."""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'action': self.action,
            'quantity': self.quantity,
            'price': self.price,
            'total_value': self.total_value,
            'order_id': self.order_id,
            'order_type': self.order_type,
            'status': self.status,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
        }


class PortfolioSnapshot(Base):
    """Portfolio snapshot for tracking portfolio value over time."""
    
    __tablename__ = 'portfolio_snapshots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Portfolio values
    portfolio_value = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    
    # Performance
    daily_change = Column(Float, nullable=True)
    daily_change_pct = Column(Float, nullable=True)
    
    # Timestamp
    timestamp = Column(DateTime, server_default=func.now())
    
    def __repr__(self):
        return f"<PortfolioSnapshot ${self.portfolio_value} @ {self.timestamp}>"
    
    def to_dict(self):
        """Convert snapshot to dictionary."""
        return {
            'portfolio_value': self.portfolio_value,
            'cash': self.cash,
            'equity': self.equity,
            'daily_change': self.daily_change,
            'daily_change_pct': self.daily_change_pct,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }
