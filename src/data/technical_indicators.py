"""Technical indicators for stock analysis.

Pure pandas implementation - no external dependencies like pandas_ta.
"""

from typing import Optional, Dict, Any
import pandas as pd
import numpy as np
from loguru import logger


class TechnicalIndicators:
    """Calculate technical indicators for trading analysis."""
    
    def __init__(self, df: pd.DataFrame):
        """Initialize with OHLCV DataFrame.
        
        Args:
            df: DataFrame with columns: open, high, low, close, volume
                (handles both lowercase and capitalized column names)
        """
        self.df = df.copy()
        
        # Normalize column names to lowercase for consistency
        self.df.columns = [c.lower() for c in self.df.columns]
        
    def calculate_all(self, enabled_indicators: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
        """Calculate all technical indicators.
        
        Returns:
            Dictionary with all indicator values
        """
        if len(self.df) < 14:
            logger.warning("Not enough data for technical analysis")
            return {}
        
        indicators = {}
        
        enabled = enabled_indicators or {}

        def is_enabled(key: str) -> bool:
            return enabled.get(key, True)

        # RSI
        if is_enabled('rsi'):
            rsi = self.calculate_rsi()
            if rsi is not None:
                indicators['rsi'] = rsi
                indicators['rsi_signal'] = self._interpret_rsi(rsi)
        
        # MACD
        if is_enabled('macd'):
            macd_data = self.calculate_macd()
            if macd_data:
                indicators.update(macd_data)
        
        # Moving Averages
        if is_enabled('moving_averages'):
            ma_data = self.calculate_moving_averages()
            if ma_data:
                indicators.update(ma_data)
        
        # Bollinger Bands
        if is_enabled('bollinger_bands'):
            bb_data = self.calculate_bollinger_bands()
            if bb_data:
                indicators.update(bb_data)
        
        # Volume analysis
        if is_enabled('volume'):
            vol_data = self.calculate_volume_analysis()
            if vol_data:
                indicators.update(vol_data)
        
        # Price changes
        if is_enabled('price_action'):
            price_data = self.calculate_price_changes()
            if price_data:
                indicators.update(price_data)
        
        # VWAP
        if is_enabled('vwap'):
            vwap_data = self.calculate_vwap()
            if vwap_data:
                indicators.update(vwap_data)
        
        # ATR
        if is_enabled('atr'):
            atr_data = self.calculate_atr()
            if atr_data:
                indicators.update(atr_data)
        
        return indicators
    
    def _ema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()
    
    def _sma(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average."""
        return series.rolling(window=period).mean()
    
    def calculate_rsi(self, period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index using native pandas.
        
        Args:
            period: RSI period (default 14)
            
        Returns:
            Current RSI value (0-100)
        """
        try:
            delta = self.df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]):
                return round(float(rsi.iloc[-1]), 2)
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
        return None
    
    def _interpret_rsi(self, rsi: float) -> str:
        """Interpret RSI value."""
        if rsi >= 70:
            return "OVERBOUGHT"
        elif rsi <= 30:
            return "OVERSOLD"
        elif rsi >= 60:
            return "BULLISH"
        elif rsi <= 40:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Any]:
        """Calculate MACD indicator using native pandas.
        
        Returns:
            Dictionary with MACD, signal, histogram values
        """
        try:
            ema_fast = self._ema(self.df['close'], fast)
            ema_slow = self._ema(self.df['close'], slow)
            macd_line = ema_fast - ema_slow
            signal_line = self._ema(macd_line, signal)
            histogram = macd_line - signal_line
            
            if len(macd_line) > 0:
                macd_val = float(macd_line.iloc[-1])
                signal_val = float(signal_line.iloc[-1])
                hist_val = float(histogram.iloc[-1])
                
                # Determine signal
                if macd_val > signal_val and hist_val > 0:
                    macd_signal = "BULLISH"
                elif macd_val < signal_val and hist_val < 0:
                    macd_signal = "BEARISH"
                else:
                    macd_signal = "NEUTRAL"
                
                return {
                    'macd': round(macd_val, 4),
                    'macd_signal_line': round(signal_val, 4),
                    'macd_histogram': round(hist_val, 4),
                    'macd_signal': macd_signal
                }
        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
        return {}
    
    def calculate_moving_averages(self) -> Dict[str, Any]:
        """Calculate Simple and Exponential Moving Averages.
        
        Returns:
            Dictionary with MA values and signals
        """
        try:
            current_price = float(self.df['close'].iloc[-1])
            
            result = {'current_price': round(current_price, 2)}
            
            # SMA 20
            if len(self.df) >= 20:
                sma_20 = self._sma(self.df['close'], 20)
                sma_20_val = float(sma_20.iloc[-1])
                result['sma_20'] = round(sma_20_val, 2)
                result['price_vs_sma20'] = "ABOVE" if current_price > sma_20_val else "BELOW"
            
            # SMA 50
            if len(self.df) >= 50:
                sma_50 = self._sma(self.df['close'], 50)
                sma_50_val = float(sma_50.iloc[-1])
                result['sma_50'] = round(sma_50_val, 2)
                result['price_vs_sma50'] = "ABOVE" if current_price > sma_50_val else "BELOW"
            
            # EMA 12 and 26
            ema_12 = self._ema(self.df['close'], 12)
            ema_26 = self._ema(self.df['close'], 26)
            
            if len(ema_12) > 0 and len(ema_26) > 0:
                ema_12_val = float(ema_12.iloc[-1])
                ema_26_val = float(ema_26.iloc[-1])
                result['ema_12'] = round(ema_12_val, 2)
                result['ema_26'] = round(ema_26_val, 2)
                result['ema_trend'] = "BULLISH" if ema_12_val > ema_26_val else "BEARISH"
            
            return result
        except Exception as e:
            logger.error(f"Error calculating moving averages: {e}")
        return {}
    
    def calculate_bollinger_bands(self, period: int = 20, std: float = 2.0) -> Dict[str, Any]:
        """Calculate Bollinger Bands using native pandas.
        
        Returns:
            Dictionary with BB values and signals
        """
        try:
            sma = self._sma(self.df['close'], period)
            std_dev = self.df['close'].rolling(window=period).std()
            
            upper = sma + (std_dev * std)
            lower = sma - (std_dev * std)
            
            if len(sma) > 0:
                current_price = float(self.df['close'].iloc[-1])
                lower_val = float(lower.iloc[-1])
                middle_val = float(sma.iloc[-1])
                upper_val = float(upper.iloc[-1])
                
                # Calculate %B
                pct_b = (current_price - lower_val) / (upper_val - lower_val) if upper_val != lower_val else 0.5
                
                # Determine signal
                if pct_b >= 1:
                    bb_signal = "OVERBOUGHT"
                elif pct_b <= 0:
                    bb_signal = "OVERSOLD"
                elif pct_b > 0.8:
                    bb_signal = "UPPER_BAND"
                elif pct_b < 0.2:
                    bb_signal = "LOWER_BAND"
                else:
                    bb_signal = "NEUTRAL"
                
                return {
                    'bb_lower': round(lower_val, 2),
                    'bb_middle': round(middle_val, 2),
                    'bb_upper': round(upper_val, 2),
                    'bb_pct_b': round(pct_b, 4),
                    'bb_signal': bb_signal
                }
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
        return {}
    
    def calculate_volume_analysis(self) -> Dict[str, Any]:
        """Analyze volume patterns.
        
        Returns:
            Dictionary with volume analysis
        """
        try:
            if len(self.df) < 20:
                return {}
            
            current_volume = int(self.df['volume'].iloc[-1])
            avg_volume_20 = float(self.df['volume'].tail(20).mean())
            
            volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1
            
            if volume_ratio > 2:
                volume_signal = "VERY_HIGH"
            elif volume_ratio > 1.5:
                volume_signal = "HIGH"
            elif volume_ratio < 0.5:
                volume_signal = "LOW"
            else:
                volume_signal = "NORMAL"
            
            return {
                'current_volume': current_volume,
                'avg_volume_20d': int(avg_volume_20),
                'volume_ratio': round(volume_ratio, 2),
                'volume_signal': volume_signal
            }
        except Exception as e:
            logger.error(f"Error analyzing volume: {e}")
        return {}
    
    def calculate_price_changes(self) -> Dict[str, Any]:
        """Calculate price changes over various periods.
        
        Returns:
            Dictionary with price change data
        """
        try:
            closes = self.df['close']
            current = float(closes.iloc[-1])
            
            result = {}
            
            # 1 day change
            if len(closes) >= 2:
                prev = float(closes.iloc[-2])
                change = ((current - prev) / prev) * 100
                result['change_1d'] = round(change, 2)
                result['change_1d_pct'] = f"{'+' if change >= 0 else ''}{round(change, 2)}%"
            
            # 5 day change
            if len(closes) >= 6:
                prev = float(closes.iloc[-6])
                change = ((current - prev) / prev) * 100
                result['change_5d'] = round(change, 2)
            
            # 20 day change
            if len(closes) >= 21:
                prev = float(closes.iloc[-21])
                change = ((current - prev) / prev) * 100
                result['change_20d'] = round(change, 2)
            
            return result
        except Exception as e:
            logger.error(f"Error calculating price changes: {e}")
        return {}

    def calculate_vwap(self) -> Dict[str, Any]:
        """Calculate Volume Weighted Average Price (VWAP).
        
        Returns:
            Dictionary with VWAP value and signal
        """
        try:
            if len(self.df) < 1:
                return {}
            
            typical_price = (self.df['high'] + self.df['low'] + self.df['close']) / 3
            vwap = (typical_price * self.df['volume']).cumsum() / self.df['volume'].cumsum()
            
            current_price = float(self.df['close'].iloc[-1])
            current_vwap = float(vwap.iloc[-1])
            
            vwap_deviation = ((current_price - current_vwap) / current_vwap) * 100
            
            if vwap_deviation > 2:
                vwap_signal = "ABOVE_VWAP_STRONG"
            elif vwap_deviation > 0:
                vwap_signal = "ABOVE_VWAP"
            elif vwap_deviation < -2:
                vwap_signal = "BELOW_VWAP_STRONG"
            else:
                vwap_signal = "BELOW_VWAP"
            
            return {
                'vwap': round(current_vwap, 2),
                'vwap_deviation_pct': round(vwap_deviation, 2),
                'vwap_signal': vwap_signal
            }
        except Exception as e:
            logger.error(f"Error calculating VWAP: {e}")
        return {}

    def calculate_atr(self, period: int = 14) -> Dict[str, Any]:
        """Calculate Average True Range (ATR) - measures volatility.
        
        Returns:
            Dictionary with ATR value and volatility assessment
        """
        try:
            high = self.df['high']
            low = self.df['low']
            close = self.df['close']
            
            # True Range calculation
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            atr = tr.rolling(window=period).mean()
            
            if len(atr) > 0 and not pd.isna(atr.iloc[-1]):
                current_atr = float(atr.iloc[-1])
                current_price = float(close.iloc[-1])
                
                atr_pct = (current_atr / current_price) * 100
                
                if atr_pct > 5:
                    volatility = "VERY_HIGH"
                elif atr_pct > 3:
                    volatility = "HIGH"
                elif atr_pct > 1.5:
                    volatility = "MODERATE"
                else:
                    volatility = "LOW"
                
                return {
                    'atr': round(current_atr, 2),
                    'atr_pct': round(atr_pct, 2),
                    'volatility': volatility,
                    'suggested_stop_loss': round(current_price - (current_atr * 2), 2)
                }
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
        return {}


def analyze_stock(df: pd.DataFrame) -> Dict[str, Any]:
    """Convenience function to analyze a stock.
    
    Args:
        df: OHLCV DataFrame
        
    Returns:
        Dictionary with all technical indicators
    """
    indicators = TechnicalIndicators(df)
    return indicators.calculate_all()
