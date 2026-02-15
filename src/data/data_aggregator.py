"""Data aggregator to combine market data and technical indicators."""

from typing import Dict, List, Any
from datetime import datetime
import pandas as pd
from loguru import logger

from .market_data import MarketDataClient
from .technical_indicators import TechnicalIndicators

import sys
sys.path.append(str(__file__).rsplit("/", 3)[0])
from config import config


class DataAggregator:
    """Aggregates all market data and indicators for LLM consumption."""
    
    def __init__(self):
        """Initialize the data aggregator."""
        self.market_client = MarketDataClient()
    
    def get_stock_analysis(self, symbol: str, days: int = 60) -> Dict[str, Any]:
        """Get complete analysis for a single stock.
        
        Args:
            symbol: Stock ticker symbol
            days: Days of historical data to fetch
            
        Returns:
            Dictionary with all analysis data
        """
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'error': None
        }
        
        try:
            # Get historical data
            df = self.market_client.get_historical_bars(symbol, days=days)
            
            if df is None or len(df) == 0:
                analysis['error'] = f"No historical data available for {symbol}"
                return analysis
            
            # Get current price
            current_price = self.market_client.get_current_price(symbol)
            if current_price:
                analysis['current_price'] = current_price
            else:
                analysis['current_price'] = float(df['close'].iloc[-1])
            
            # Calculate technical indicators
            indicators = TechnicalIndicators(df)
            tech_data = indicators.calculate_all(config.trading.enabled_indicators)
            analysis['technical'] = tech_data
            
            # Generate summary signals
            analysis['signals'] = self._generate_signals(
                tech_data,
                config.trading.enabled_indicators
            )
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            analysis['error'] = str(e)
        
        return analysis
    
    def get_watchlist_analysis(self, symbols: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get analysis for all stocks in watchlist.
        
        Args:
            symbols: Optional list of symbols (uses config watchlist if not provided)
            
        Returns:
            Dictionary mapping symbol to analysis data
        """
        if symbols is None:
            symbols = config.trading.watchlist
        
        results = {}
        
        logger.info(f"Analyzing {len(symbols)} stocks: {', '.join(symbols)}")
        
        for symbol in symbols:
            results[symbol] = self.get_stock_analysis(symbol)
        
        return results
    
    def _generate_signals(
        self,
        tech_data: Dict[str, Any],
        enabled_indicators: Dict[str, bool] = None
    ) -> Dict[str, Any]:
        """Generate trading signals from technical data.
        
        Args:
            tech_data: Dictionary of technical indicators
            
        Returns:
            Dictionary with signal summary
        """
        signals = {
            'bullish_signals': [],
            'bearish_signals': [],
            'neutral_signals': [],
            'overall': 'NEUTRAL'
        }
        
        enabled = enabled_indicators or {}

        def is_enabled(key: str) -> bool:
            return enabled.get(key, True)

        # RSI signals
        if is_enabled('rsi'):
            rsi_signal = tech_data.get('rsi_signal', '')
            if rsi_signal == 'OVERSOLD':
                signals['bullish_signals'].append('RSI_OVERSOLD')
            elif rsi_signal == 'OVERBOUGHT':
                signals['bearish_signals'].append('RSI_OVERBOUGHT')
            elif rsi_signal == 'BULLISH':
                signals['bullish_signals'].append('RSI_BULLISH')
            elif rsi_signal == 'BEARISH':
                signals['bearish_signals'].append('RSI_BEARISH')
        
        # MACD signals
        if is_enabled('macd'):
            macd_signal = tech_data.get('macd_signal', '')
            if 'BULLISH' in macd_signal:
                signals['bullish_signals'].append(f'MACD_{macd_signal}')
            elif 'BEARISH' in macd_signal:
                signals['bearish_signals'].append(f'MACD_{macd_signal}')
        
        # Moving average signals
        if is_enabled('moving_averages'):
            if tech_data.get('price_vs_sma20') == 'ABOVE' and tech_data.get('price_vs_sma50') == 'ABOVE':
                signals['bullish_signals'].append('ABOVE_MOVING_AVERAGES')
            elif tech_data.get('price_vs_sma20') == 'BELOW' and tech_data.get('price_vs_sma50') == 'BELOW':
                signals['bearish_signals'].append('BELOW_MOVING_AVERAGES')

            # EMA trend
            ema_trend = tech_data.get('ema_trend', '')
            if ema_trend == 'BULLISH':
                signals['bullish_signals'].append('EMA_BULLISH')
            elif ema_trend == 'BEARISH':
                signals['bearish_signals'].append('EMA_BEARISH')
        
        # Bollinger Band signals
        if is_enabled('bollinger_bands'):
            bb_signal = tech_data.get('bb_signal', '')
            if bb_signal == 'OVERSOLD' or bb_signal == 'LOWER_BAND':
                signals['bullish_signals'].append('BB_OVERSOLD')
            elif bb_signal == 'OVERBOUGHT' or bb_signal == 'UPPER_BAND':
                signals['bearish_signals'].append('BB_OVERBOUGHT')
        
        # Volume signals
        if is_enabled('volume'):
            volume_signal = tech_data.get('volume_signal', '')
            if volume_signal in ['HIGH', 'VERY_HIGH']:
                # High volume confirms the trend
                if len(signals['bullish_signals']) > len(signals['bearish_signals']):
                    signals['bullish_signals'].append('HIGH_VOLUME_CONFIRM')
                elif len(signals['bearish_signals']) > len(signals['bullish_signals']):
                    signals['bearish_signals'].append('HIGH_VOLUME_CONFIRM')
        
        # Calculate overall signal
        bullish_count = len(signals['bullish_signals'])
        bearish_count = len(signals['bearish_signals'])
        
        if bullish_count > bearish_count + 1:
            signals['overall'] = 'BULLISH'
        elif bearish_count > bullish_count + 1:
            signals['overall'] = 'BEARISH'
        else:
            signals['overall'] = 'NEUTRAL'
        
        signals['bullish_count'] = bullish_count
        signals['bearish_count'] = bearish_count
        
        return signals
    
    def format_for_llm(self, analysis: Dict[str, Dict[str, Any]]) -> str:
        """Format analysis data for LLM consumption.
        
        Args:
            analysis: Dictionary of stock analyses
            
        Returns:
            Formatted string for LLM prompt
        """
        lines = []
        
        for symbol, data in analysis.items():
            if data.get('error'):
                lines.append(f"\n{symbol}: Error - {data['error']}")
                continue
            
            tech = data.get('technical', {})
            signals = data.get('signals', {})
            
            lines.append(f"\n{'='*50}")
            lines.append(f"📈 {symbol}")
            lines.append(f"{'='*50}")
            lines.append(f"Current Price: ${data.get('current_price', 'N/A')}")
            
            # Price changes
            if 'change_1d_pct' in tech:
                lines.append(f"1-Day Change: {tech['change_1d_pct']}")
            if 'change_5d' in tech:
                lines.append(f"5-Day Change: {tech['change_5d']:+.2f}%")
            
            lines.append("")
            lines.append("Technical Indicators:")
            
            # RSI
            if config.trading.enabled_indicators.get('rsi', True) and 'rsi' in tech:
                lines.append(f"  • RSI(14): {tech['rsi']} ({tech.get('rsi_signal', 'N/A')})")
            
            # MACD
            if config.trading.enabled_indicators.get('macd', True) and 'macd_signal' in tech:
                lines.append(f"  • MACD: {tech['macd_signal']}")
            
            # Moving Averages
            if config.trading.enabled_indicators.get('moving_averages', True) and 'sma_20' in tech:
                lines.append(f"  • SMA(20): ${tech['sma_20']} (Price {tech.get('price_vs_sma20', 'N/A')})")
            if config.trading.enabled_indicators.get('moving_averages', True) and 'sma_50' in tech:
                lines.append(f"  • SMA(50): ${tech['sma_50']} (Price {tech.get('price_vs_sma50', 'N/A')})")
            
            # EMA trend
            if config.trading.enabled_indicators.get('moving_averages', True) and 'ema_trend' in tech:
                lines.append(f"  • EMA Trend: {tech['ema_trend']}")
            
            # Bollinger Bands
            if config.trading.enabled_indicators.get('bollinger_bands', True) and 'bb_signal' in tech:
                lines.append(f"  • Bollinger Bands: {tech['bb_signal']} (%B: {tech.get('bb_pct_b', 'N/A')})")
            
            # Volume
            if config.trading.enabled_indicators.get('volume', True) and 'volume_signal' in tech:
                lines.append(f"  • Volume: {tech['volume_signal']} ({tech.get('volume_ratio', 'N/A')}x average)")
            
            lines.append("")
            lines.append("Signal Summary:")
            lines.append(f"  • Overall Signal: {signals.get('overall', 'N/A')}")
            lines.append(f"  • Bullish Signals ({signals.get('bullish_count', 0)}): {', '.join(signals.get('bullish_signals', [])) or 'None'}")
            lines.append(f"  • Bearish Signals ({signals.get('bearish_count', 0)}): {', '.join(signals.get('bearish_signals', [])) or 'None'}")
        
        return '\n'.join(lines)
