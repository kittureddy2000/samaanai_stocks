"""Broker abstraction layer for multi-broker support.

Provides a standardized interface for trading operations that can be
implemented by the IBKR broker.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AccountInfo:
    """Standardized account information."""
    id: str
    cash: float
    buying_power: float
    portfolio_value: float
    equity: float
    last_equity: float


@dataclass
class Position:
    """Standardized position information."""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float


@dataclass
class Order:
    """Standardized order information."""
    id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    qty: float
    order_type: str  # 'market', 'limit'
    status: str
    limit_price: Optional[float] = None
    filled_qty: float = 0
    filled_price: Optional[float] = None
    created_at: Optional[datetime] = None


class BaseBroker(ABC):
    """Abstract base class for broker implementations.
    
    The IBKR broker implementation must implement this interface
    to ensure consistent behavior across the trading system.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the broker name."""
        pass
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the broker.
        
        Returns:
            True if connection successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test the broker connection.
        
        Returns:
            True if connection is working, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_account(self) -> Optional[AccountInfo]:
        """Get account information.
        
        Returns:
            AccountInfo object or None if error.
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Get all open positions.
        
        Returns:
            List of Position objects.
        """
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol.
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            Position object or None if not found.
        """
        pass
    
    @abstractmethod
    def place_market_order(self, symbol: str, qty: int, side: str) -> Optional[Order]:
        """Place a market order.
        
        Args:
            symbol: Stock ticker symbol.
            qty: Number of shares.
            side: 'buy' or 'sell'.
            
        Returns:
            Order object or None if error.
        """
        pass
    
    @abstractmethod
    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Optional[Order]:
        """Place a limit order.
        
        Args:
            symbol: Stock ticker symbol.
            qty: Number of shares.
            side: 'buy' or 'sell'.
            limit_price: Limit price for the order.
            
        Returns:
            Order object or None if error.
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order status by ID.
        
        Args:
            order_id: The order identifier.
            
        Returns:
            Order object or None if not found.
        """
        pass
    
    @abstractmethod
    def get_orders_history(self, limit: int = 50) -> List[Order]:
        """Get recent order history.
        
        Args:
            limit: Maximum number of orders to return.
            
        Returns:
            List of Order objects.
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: The order identifier.
            
        Returns:
            True if cancelled successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def is_market_open(self) -> bool:
        """Check if market is currently open.
        
        Returns:
            True if market is open, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_market_hours(self) -> dict:
        """Get market hours information.
        
        Returns:
            Dictionary with 'is_open', 'next_open', 'next_close' keys.
        """
        pass
