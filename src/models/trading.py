"""Complete trading data models for the stock trading application.

This module contains all database models for:
- Positions (current and historical)
- Orders (placed and executed)
- Watchlists (user watchlists)
- Analysis logs (LLM analysis history)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON
from sqlalchemy.sql import func
from utils.database_sql import Base


class Position(Base):
    """Current and historical positions."""
    
    __tablename__ = 'positions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Position details
    symbol = Column(String(20), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)
    
    # P&L
    cost_basis = Column(Float, nullable=True)
    unrealized_pl = Column(Float, nullable=True)
    unrealized_pl_pct = Column(Float, nullable=True)
    realized_pl = Column(Float, nullable=True)
    
    # Status
    is_open = Column(Boolean, default=True)
    side = Column(String(10), default='long')  # long, short
    
    # Timestamps
    opened_at = Column(DateTime, server_default=func.now())
    closed_at = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Position {self.quantity} {self.symbol} @ ${self.avg_entry_price}>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'quantity': self.quantity,
            'avg_entry_price': self.avg_entry_price,
            'current_price': self.current_price,
            'market_value': self.market_value,
            'cost_basis': self.cost_basis,
            'unrealized_pl': self.unrealized_pl,
            'unrealized_pl_pct': self.unrealized_pl_pct,
            'realized_pl': self.realized_pl,
            'is_open': self.is_open,
            'side': self.side,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
        }


class Order(Base):
    """Order history - all orders placed through the system."""
    
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Order identification
    order_id = Column(String(100), unique=True, nullable=True)  # Alpaca order ID
    client_order_id = Column(String(100), nullable=True)
    
    # Order details
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # buy, sell
    order_type = Column(String(20), default='market')  # market, limit, stop, stop_limit
    time_in_force = Column(String(10), default='day')  # day, gtc, ioc, fok
    
    # Quantities
    qty = Column(Integer, nullable=False)
    filled_qty = Column(Integer, default=0)
    
    # Prices
    limit_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    filled_avg_price = Column(Float, nullable=True)
    
    # Status
    status = Column(String(20), default='pending')  # pending, accepted, filled, canceled, rejected
    
    # LLM reasoning
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    submitted_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Order {self.side.upper()} {self.qty} {self.symbol} ({self.status})>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type,
            'qty': self.qty,
            'filled_qty': self.filled_qty,
            'limit_price': self.limit_price,
            'stop_price': self.stop_price,
            'filled_avg_price': self.filled_avg_price,
            'status': self.status,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
        }


class Watchlist(Base):
    """User watchlists for tracking stocks."""
    
    __tablename__ = 'watchlists'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Watchlist details
    name = Column(String(100), default='Default')
    symbols = Column(JSON, nullable=False)  # List of symbols
    
    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Watchlist {self.name} ({len(self.symbols or [])} symbols)>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'symbols': self.symbols,
            'is_active': self.is_active,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AnalysisLog(Base):
    """Log of LLM analysis runs."""
    
    __tablename__ = 'analysis_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Analysis details
    strategy = Column(String(50), default='balanced')
    symbols_analyzed = Column(JSON, nullable=True)  # List of symbols
    
    # Results
    analysis_summary = Column(Text, nullable=True)
    risk_assessment = Column(String(20), nullable=True)
    trades_recommended = Column(Integer, default=0)
    trades_executed = Column(Integer, default=0)
    
    # LLM details
    model_used = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    
    # Raw data
    raw_response = Column(JSON, nullable=True)
    
    # Status
    status = Column(String(20), default='completed')  # pending, completed, failed
    error_message = Column(Text, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, server_default=func.now())
    
    def __repr__(self):
        return f"<AnalysisLog {self.strategy} @ {self.created_at}>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'strategy': self.strategy,
            'symbols_analyzed': self.symbols_analyzed,
            'analysis_summary': self.analysis_summary,
            'risk_assessment': self.risk_assessment,
            'trades_recommended': self.trades_recommended,
            'trades_executed': self.trades_executed,
            'model_used': self.model_used,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TradingConfig(Base):
    """User-specific trading configuration."""
    
    __tablename__ = 'trading_configs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, unique=True)
    
    # Trading parameters
    strategy = Column(String(50), default='balanced')
    max_position_pct = Column(Float, default=0.10)
    max_daily_loss_pct = Column(Float, default=0.03)
    min_confidence = Column(Float, default=0.70)
    stop_loss_pct = Column(Float, default=0.05)
    take_profit_pct = Column(Float, default=0.10)
    
    # Trading controls
    trading_enabled = Column(Boolean, default=True)
    auto_trade = Column(Boolean, default=True)
    paper_trading = Column(Boolean, default=True)
    
    # Analysis settings
    analysis_interval_minutes = Column(Integer, default=30)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<TradingConfig {self.strategy} (user_id={self.user_id})>"
    
    def to_dict(self):
        return {
            'strategy': self.strategy,
            'max_position_pct': self.max_position_pct,
            'max_daily_loss_pct': self.max_daily_loss_pct,
            'min_confidence': self.min_confidence,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'trading_enabled': self.trading_enabled,
            'auto_trade': self.auto_trade,
            'paper_trading': self.paper_trading,
            'analysis_interval_minutes': self.analysis_interval_minutes,
        }
