"""Market data client for fetching stock data from Alpaca."""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config import config


class MarketDataClient:
    """Client for fetching market data from Alpaca."""
    
    def __init__(self):
        """Initialize the Alpaca data client."""
        self.client = StockHistoricalDataClient(
            api_key=config.alpaca.api_key,
            secret_key=config.alpaca.secret_key
        )
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get the current price for a symbol.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')
            
        Returns:
            Current price or None if unavailable
        """
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self.client.get_stock_latest_quote(request)
            
            if symbol in quotes:
                quote = quotes[symbol]
                # Use ask price, or bid if ask unavailable
                price = quote.ask_price if quote.ask_price > 0 else quote.bid_price
                return float(price)
            return None
            
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None
    
    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get current prices for multiple symbols.
        
        Args:
            symbols: List of stock ticker symbols
            
        Returns:
            Dictionary mapping symbol to price
        """
        prices = {}
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbols)
            quotes = self.client.get_stock_latest_quote(request)
            
            for symbol in symbols:
                if symbol in quotes:
                    quote = quotes[symbol]
                    price = quote.ask_price if quote.ask_price > 0 else quote.bid_price
                    if price > 0:
                        prices[symbol] = float(price)
                        
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            
        return prices
    
    def get_historical_bars(
        self, 
        symbol: str, 
        days: int = 30,
        timeframe: TimeFrame = TimeFrame.Day
    ) -> Optional[pd.DataFrame]:
        """Get historical price bars for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            days: Number of days of history
            timeframe: Bar timeframe (Day, Hour, Minute)
            
        Returns:
            DataFrame with OHLCV data or None
        """
        # Try Alpaca IEX first
        try:
            end = datetime.now()
            start = end - timedelta(days=days)
            
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start,
                end=end
            )
            
            # Use IEX feed (free) instead of SIP (paid subscription)
            from alpaca.data.enums import DataFeed
            bars = self.client.get_stock_bars(request, feed=DataFeed.IEX)
            
            if symbol in bars.data and len(bars.data[symbol]) > 0:
                # Convert to DataFrame
                data = []
                for bar in bars.data[symbol]:
                    data.append({
                        'timestamp': bar.timestamp,
                        'open': float(bar.open),
                        'high': float(bar.high),
                        'low': float(bar.low),
                        'close': float(bar.close),
                        'volume': int(bar.volume)
                    })
                
                df = pd.DataFrame(data)
                df.set_index('timestamp', inplace=True)
                logger.debug(f"Got {len(df)} bars from Alpaca IEX for {symbol}")
                return df
            
        except Exception as e:
            logger.warning(f"Alpaca IEX failed for {symbol}: {e}")
        
        # Fallback to yfinance
        try:
            import yfinance as yf
            logger.info(f"Falling back to yfinance for {symbol}")
            
            ticker = yf.Ticker(symbol)
            period = "3mo" if days <= 90 else "1y"
            df = ticker.history(period=period)
            
            if df is not None and len(df) > 0:
                # Normalize column names to lowercase
                df.columns = [c.lower() for c in df.columns]
                logger.debug(f"Got {len(df)} bars from yfinance for {symbol}")
                return df
                
        except Exception as e:
            logger.error(f"yfinance also failed for {symbol}: {e}")
        
        return None
    
    def get_historical_bars_multi(
        self,
        symbols: List[str],
        days: int = 30,
        timeframe: TimeFrame = TimeFrame.Day
    ) -> Dict[str, pd.DataFrame]:
        """Get historical bars for multiple symbols.
        
        Args:
            symbols: List of stock ticker symbols
            days: Number of days of history
            timeframe: Bar timeframe
            
        Returns:
            Dictionary mapping symbol to DataFrame
        """
        results = {}
        
        try:
            end = datetime.now()
            start = end - timedelta(days=days)
            
            request = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=timeframe,
                start=start,
                end=end
            )
            
            # Use IEX feed (free) instead of SIP (paid subscription)
            from alpaca.data.enums import DataFeed
            bars = self.client.get_stock_bars(request, feed=DataFeed.IEX)
            
            for symbol in symbols:
                if symbol in bars.data:
                    data = []
                    for bar in bars.data[symbol]:
                        data.append({
                            'timestamp': bar.timestamp,
                            'open': float(bar.open),
                            'high': float(bar.high),
                            'low': float(bar.low),
                            'close': float(bar.close),
                            'volume': int(bar.volume)
                        })
                    
                    if data:
                        df = pd.DataFrame(data)
                        df.set_index('timestamp', inplace=True)
                        results[symbol] = df
                        
        except Exception as e:
            logger.error(f"Error fetching historical bars: {e}")
            
        return results


# Convenience function for quick price lookup
def get_price(symbol: str) -> Optional[float]:
    """Quick helper to get current price."""
    client = MarketDataClient()
    return client.get_current_price(symbol)
