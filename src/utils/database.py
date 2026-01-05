"""Database for storing trade history and analysis."""

from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from loguru import logger
import json

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

Base = declarative_base()


class Trade(Base):
    """Trade record model."""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)  # BUY, SELL
    quantity = Column(Integer, nullable=False)
    order_type = Column(String(10))  # market, limit
    limit_price = Column(Float, nullable=True)
    executed_price = Column(Float, nullable=True)
    confidence = Column(Float)
    reasoning = Column(Text)
    order_id = Column(String(100))
    status = Column(String(20))  # FILLED, REJECTED, etc.
    llm_analysis = Column(Text)  # Full LLM response as JSON


class PortfolioSnapshot(Base):
    """Portfolio snapshot model."""
    __tablename__ = 'portfolio_snapshots'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    portfolio_value = Column(Float)
    cash = Column(Float)
    equity = Column(Float)
    positions_count = Column(Integer)
    unrealized_pl = Column(Float)
    daily_change = Column(Float)
    daily_change_pct = Column(Float)


class Analysis(Base):
    """Market analysis record."""
    __tablename__ = 'analyses'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    watchlist = Column(Text)  # JSON list of symbols
    market_data = Column(Text)  # JSON of market data
    llm_response = Column(Text)  # Full LLM response as JSON
    trades_recommended = Column(Integer)
    trades_executed = Column(Integer)


class Database:
    """Database manager for trade history."""
    
    def __init__(self):
        """Initialize database connection."""
        db_url = f"sqlite:///{config.db_path}"
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        logger.debug(f"Database initialized: {config.db_path}")
    
    def record_trade(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = 'market',
        limit_price: Optional[float] = None,
        executed_price: Optional[float] = None,
        confidence: float = 0,
        reasoning: str = '',
        order_id: str = '',
        status: str = '',
        llm_analysis: Dict = None
    ) -> int:
        """Record a trade to the database.
        
        Returns:
            Trade ID
        """
        trade = Trade(
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            executed_price=executed_price,
            confidence=confidence,
            reasoning=reasoning,
            order_id=order_id,
            status=status,
            llm_analysis=json.dumps(llm_analysis) if llm_analysis else None
        )
        
        self.session.add(trade)
        self.session.commit()
        
        logger.info(f"TRADE recorded: {action} {quantity} {symbol} (ID: {trade.id})")
        return trade.id
    
    def record_portfolio_snapshot(
        self,
        portfolio_value: float,
        cash: float,
        equity: float,
        positions_count: int,
        unrealized_pl: float,
        daily_change: float,
        daily_change_pct: float
    ) -> int:
        """Record a portfolio snapshot.
        
        Returns:
            Snapshot ID
        """
        snapshot = PortfolioSnapshot(
            portfolio_value=portfolio_value,
            cash=cash,
            equity=equity,
            positions_count=positions_count,
            unrealized_pl=unrealized_pl,
            daily_change=daily_change,
            daily_change_pct=daily_change_pct
        )
        
        self.session.add(snapshot)
        self.session.commit()
        
        return snapshot.id
    
    def record_analysis(
        self,
        watchlist: List[str],
        market_data: Dict,
        llm_response: Dict,
        trades_recommended: int,
        trades_executed: int
    ) -> int:
        """Record a market analysis.
        
        Returns:
            Analysis ID
        """
        analysis = Analysis(
            watchlist=json.dumps(watchlist),
            market_data=json.dumps(market_data),
            llm_response=json.dumps(llm_response),
            trades_recommended=trades_recommended,
            trades_executed=trades_executed
        )
        
        self.session.add(analysis)
        self.session.commit()
        
        return analysis.id
    
    def get_recent_trades(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent trades.
        
        Args:
            limit: Maximum number of trades to return
            
        Returns:
            List of trade dictionaries
        """
        trades = self.session.query(Trade).order_by(Trade.timestamp.desc()).limit(limit).all()
        
        return [
            {
                'id': t.id,
                'timestamp': t.timestamp.isoformat() if t.timestamp else None,
                'symbol': t.symbol,
                'action': t.action,
                'quantity': t.quantity,
                'order_type': t.order_type,
                'limit_price': t.limit_price,
                'executed_price': t.executed_price,
                'confidence': t.confidence,
                'reasoning': t.reasoning,
                'status': t.status
            }
            for t in trades
        ]
    
    def get_portfolio_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get portfolio history.
        
        Args:
            limit: Maximum number of snapshots
            
        Returns:
            List of snapshot dictionaries
        """
        snapshots = self.session.query(PortfolioSnapshot).order_by(
            PortfolioSnapshot.timestamp.desc()
        ).limit(limit).all()
        
        return [
            {
                'id': s.id,
                'timestamp': s.timestamp.isoformat() if s.timestamp else None,
                'portfolio_value': s.portfolio_value,
                'cash': s.cash,
                'equity': s.equity,
                'positions_count': s.positions_count,
                'unrealized_pl': s.unrealized_pl,
                'daily_change': s.daily_change,
                'daily_change_pct': s.daily_change_pct
            }
            for s in snapshots
        ]
    
    def get_trade_stats(self) -> Dict[str, Any]:
        """Get trading statistics.
        
        Returns:
            Dictionary of stats
        """
        total_trades = self.session.query(Trade).count()
        buy_trades = self.session.query(Trade).filter(Trade.action == 'BUY').count()
        sell_trades = self.session.query(Trade).filter(Trade.action == 'SELL').count()
        
        return {
            'total_trades': total_trades,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades
        }
    
    def close(self):
        """Close the database session."""
        self.session.close()


# Global database instance
db = Database()
