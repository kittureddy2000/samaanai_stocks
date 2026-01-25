"""Market data client for fetching stock data using yfinance."""

from typing import Dict, List, Optional
import pandas as pd
import yfinance as yf
from loguru import logger


class MarketDataClient:
    """Client for fetching market data using yfinance."""

    def __init__(self):
        """Initialize the market data client."""
        pass

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get the current price for a symbol.

        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            Current price or None if unavailable
        """
        try:
            ticker = yf.Ticker(symbol)
            # Try to get the current price from info
            info = ticker.info
            price = info.get('regularMarketPrice') or info.get('currentPrice')
            if price:
                return float(price)

            # Fallback to last close from history
            hist = ticker.history(period="1d")
            if len(hist) > 0:
                return float(hist['Close'].iloc[-1])

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
            # Batch download for efficiency
            tickers = yf.Tickers(' '.join(symbols))

            for symbol in symbols:
                try:
                    ticker = tickers.tickers.get(symbol)
                    if ticker:
                        info = ticker.info
                        price = info.get('regularMarketPrice') or info.get('currentPrice')
                        if price and price > 0:
                            prices[symbol] = float(price)
                except Exception as e:
                    logger.debug(f"Could not get price for {symbol}: {e}")

        except Exception as e:
            logger.error(f"Error fetching prices: {e}")

        return prices

    def get_historical_bars(
        self,
        symbol: str,
        days: int = 30,
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """Get historical price bars for a symbol.

        Args:
            symbol: Stock ticker symbol
            days: Number of days of history
            interval: Bar interval ('1d', '1h', '5m', etc.)

        Returns:
            DataFrame with OHLCV data or None
        """
        try:
            ticker = yf.Ticker(symbol)
            period = "3mo" if days <= 90 else "1y"
            df = ticker.history(period=period, interval=interval)

            if df is not None and len(df) > 0:
                # Normalize column names to lowercase
                df.columns = [c.lower() for c in df.columns]
                logger.debug(f"Got {len(df)} bars from yfinance for {symbol}")
                return df

        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")

        return None

    def get_historical_bars_multi(
        self,
        symbols: List[str],
        days: int = 30,
        interval: str = "1d"
    ) -> Dict[str, pd.DataFrame]:
        """Get historical bars for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            days: Number of days of history
            interval: Bar interval

        Returns:
            Dictionary mapping symbol to DataFrame
        """
        results = {}

        try:
            period = "3mo" if days <= 90 else "1y"

            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    df = ticker.history(period=period, interval=interval)

                    if df is not None and len(df) > 0:
                        df.columns = [c.lower() for c in df.columns]
                        results[symbol] = df

                except Exception as e:
                    logger.debug(f"Could not get history for {symbol}: {e}")

        except Exception as e:
            logger.error(f"Error fetching historical bars: {e}")

        return results


# Convenience function for quick price lookup
def get_price(symbol: str) -> Optional[float]:
    """Quick helper to get current price."""
    client = MarketDataClient()
    return client.get_current_price(symbol)
