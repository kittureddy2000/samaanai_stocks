"""Technical indicators for stock analysis."""

from typing import Optional, Dict, Any
import pandas as pd
import pandas_ta as ta
from loguru import logger


class TechnicalIndicators:
    """Calculate technical indicators for trading analysis."""
    
    def __init__(self, df: pd.DataFrame):
        """Initialize with OHLCV DataFrame.
        
        Args:
            df: DataFrame with columns: open, high, low, close, volume
        """
        self.df = df.copy()
        
    def calculate_all(self) -> Dict[str, Any]:
        """Calculate all technical indicators.
        
        Returns:
            Dictionary with all indicator values
        """
        if len(self.df) < 14:
            logger.warning("Not enough data for technical analysis")
            return {}
        
        indicators = {}
        
        # RSI
        rsi = self.calculate_rsi()
        if rsi is not None:
            indicators['rsi'] = rsi
            indicators['rsi_signal'] = self._interpret_rsi(rsi)
        
        # MACD
        macd_data = self.calculate_macd()
        if macd_data:
            indicators.update(macd_data)
        
        # Moving Averages
        ma_data = self.calculate_moving_averages()
        if ma_data:
            indicators.update(ma_data)
        
        # Bollinger Bands
        bb_data = self.calculate_bollinger_bands()
        if bb_data:
            indicators.update(bb_data)
        
        # Volume analysis
        vol_data = self.calculate_volume_analysis()
        if vol_data:
            indicators.update(vol_data)
        
        # Price changes
        price_data = self.calculate_price_changes()
        if price_data:
            indicators.update(price_data)
        
        # === NEW CUSTOM INDICATORS ===
        
        # VWAP (Volume Weighted Average Price)
        vwap_data = self.calculate_vwap()
        if vwap_data:
            indicators.update(vwap_data)
        
        # ATR (Average True Range) - Volatility
        atr_data = self.calculate_atr()
        if atr_data:
            indicators.update(atr_data)
        
        # Stochastic Oscillator
        stoch_data = self.calculate_stochastic()
        if stoch_data:
            indicators.update(stoch_data)
        
        # OBV (On-Balance Volume)
        obv_data = self.calculate_obv()
        if obv_data:
            indicators.update(obv_data)
        
        # Fibonacci Retracements
        fib_data = self.calculate_fibonacci()
        if fib_data:
            indicators.update(fib_data)
        
        return indicators
    
    def calculate_rsi(self, period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index.
        
        Args:
            period: RSI period (default 14)
            
        Returns:
            Current RSI value (0-100)
        """
        try:
            rsi = ta.rsi(self.df['close'], length=period)
            if rsi is not None and len(rsi) > 0:
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
        """Calculate MACD indicator.
        
        Returns:
            Dictionary with MACD, signal, histogram values
        """
        try:
            macd = ta.macd(self.df['close'], fast=fast, slow=slow, signal=signal)
            
            if macd is not None and len(macd) > 0:
                macd_line = float(macd.iloc[-1, 0])  # MACD line
                signal_line = float(macd.iloc[-1, 1])  # Signal line
                histogram = float(macd.iloc[-1, 2])  # Histogram
                
                # Determine signal
                if macd_line > signal_line and histogram > 0:
                    macd_signal = "BULLISH"
                elif macd_line < signal_line and histogram < 0:
                    macd_signal = "BEARISH"
                else:
                    macd_signal = "NEUTRAL"
                
                # Check for crossover
                if len(macd) >= 2:
                    prev_macd = float(macd.iloc[-2, 0])
                    prev_signal = float(macd.iloc[-2, 1])
                    
                    if prev_macd <= prev_signal and macd_line > signal_line:
                        macd_signal = "BULLISH_CROSSOVER"
                    elif prev_macd >= prev_signal and macd_line < signal_line:
                        macd_signal = "BEARISH_CROSSOVER"
                
                return {
                    'macd': round(macd_line, 4),
                    'macd_signal_line': round(signal_line, 4),
                    'macd_histogram': round(histogram, 4),
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
            
            # Calculate SMAs
            sma_20 = ta.sma(self.df['close'], length=20)
            sma_50 = ta.sma(self.df['close'], length=50)
            
            result = {'current_price': round(current_price, 2)}
            
            if sma_20 is not None and len(sma_20) > 0:
                sma_20_val = float(sma_20.iloc[-1])
                result['sma_20'] = round(sma_20_val, 2)
                result['price_vs_sma20'] = "ABOVE" if current_price > sma_20_val else "BELOW"
            
            if sma_50 is not None and len(sma_50) > 0:
                sma_50_val = float(sma_50.iloc[-1])
                result['sma_50'] = round(sma_50_val, 2)
                result['price_vs_sma50'] = "ABOVE" if current_price > sma_50_val else "BELOW"
            
            # EMA 12 and 26 (short-term trends)
            ema_12 = ta.ema(self.df['close'], length=12)
            ema_26 = ta.ema(self.df['close'], length=26)
            
            if ema_12 is not None and ema_26 is not None:
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
        """Calculate Bollinger Bands.
        
        Returns:
            Dictionary with BB values and signals
        """
        try:
            bb = ta.bbands(self.df['close'], length=period, std=std)
            
            if bb is not None and len(bb) > 0:
                current_price = float(self.df['close'].iloc[-1])
                lower = float(bb.iloc[-1, 0])  # Lower band
                middle = float(bb.iloc[-1, 1])  # Middle (SMA)
                upper = float(bb.iloc[-1, 2])  # Upper band
                
                # Calculate %B (position within bands)
                pct_b = (current_price - lower) / (upper - lower) if upper != lower else 0.5
                
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
                    'bb_lower': round(lower, 2),
                    'bb_middle': round(middle, 2),
                    'bb_upper': round(upper, 2),
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
            
            # 52-week high/low (if we have enough data)
            if len(closes) >= 252:
                high_52w = float(closes.tail(252).max())
                low_52w = float(closes.tail(252).min())
                result['high_52w'] = round(high_52w, 2)
                result['low_52w'] = round(low_52w, 2)
                result['pct_from_52w_high'] = round(((current - high_52w) / high_52w) * 100, 2)
            
            return result
        except Exception as e:
            logger.error(f"Error calculating price changes: {e}")
        return {}

    # ==========================================
    # NEW CUSTOM INDICATORS FOR COMPETITIVE EDGE
    # ==========================================

    def calculate_vwap(self) -> Dict[str, Any]:
        """Calculate Volume Weighted Average Price (VWAP).
        
        VWAP is used by institutional traders as a benchmark.
        Price above VWAP = bullish, below = bearish.
        
        Returns:
            Dictionary with VWAP value and signal
        """
        try:
            if len(self.df) < 1:
                return {}
            
            # Calculate VWAP: cumsum(price * volume) / cumsum(volume)
            typical_price = (self.df['high'] + self.df['low'] + self.df['close']) / 3
            vwap = (typical_price * self.df['volume']).cumsum() / self.df['volume'].cumsum()
            
            current_price = float(self.df['close'].iloc[-1])
            current_vwap = float(vwap.iloc[-1])
            
            # Calculate % deviation from VWAP
            vwap_deviation = ((current_price - current_vwap) / current_vwap) * 100
            
            # Signal based on price vs VWAP
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
        
        Higher ATR = more volatile, useful for:
        - Dynamic stop-loss sizing
        - Position sizing based on volatility
        
        Returns:
            Dictionary with ATR value and volatility assessment
        """
        try:
            atr = ta.atr(self.df['high'], self.df['low'], self.df['close'], length=period)
            
            if atr is not None and len(atr) > 0:
                current_atr = float(atr.iloc[-1])
                current_price = float(self.df['close'].iloc[-1])
                
                # ATR as percentage of price
                atr_pct = (current_atr / current_price) * 100
                
                # Calculate ATR trend (is volatility increasing?)
                if len(atr) >= 5:
                    atr_5_ago = float(atr.iloc[-5])
                    atr_trend = "INCREASING" if current_atr > atr_5_ago else "DECREASING"
                else:
                    atr_trend = "STABLE"
                
                # Volatility classification
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
                    'atr_trend': atr_trend,
                    'volatility': volatility,
                    'suggested_stop_loss': round(current_price - (current_atr * 2), 2)
                }
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
        return {}

    def calculate_stochastic(self, k_period: int = 14, d_period: int = 3) -> Dict[str, Any]:
        """Calculate Stochastic Oscillator.
        
        Measures momentum - where price is relative to high/low range.
        Often catches reversals before RSI.
        
        Returns:
            Dictionary with %K, %D values and signals
        """
        try:
            stoch = ta.stoch(self.df['high'], self.df['low'], self.df['close'], 
                           k=k_period, d=d_period)
            
            if stoch is not None and len(stoch) > 0:
                stoch_k = float(stoch.iloc[-1, 0])  # %K (fast)
                stoch_d = float(stoch.iloc[-1, 1])  # %D (slow/signal)
                
                # Determine signal
                if stoch_k > 80 and stoch_d > 80:
                    stoch_signal = "OVERBOUGHT"
                elif stoch_k < 20 and stoch_d < 20:
                    stoch_signal = "OVERSOLD"
                elif stoch_k > stoch_d and stoch_k > 50:
                    stoch_signal = "BULLISH"
                elif stoch_k < stoch_d and stoch_k < 50:
                    stoch_signal = "BEARISH"
                else:
                    stoch_signal = "NEUTRAL"
                
                # Check for crossover
                if len(stoch) >= 2:
                    prev_k = float(stoch.iloc[-2, 0])
                    prev_d = float(stoch.iloc[-2, 1])
                    
                    if prev_k <= prev_d and stoch_k > stoch_d:
                        stoch_signal = "BULLISH_CROSS"
                    elif prev_k >= prev_d and stoch_k < stoch_d:
                        stoch_signal = "BEARISH_CROSS"
                
                return {
                    'stoch_k': round(stoch_k, 2),
                    'stoch_d': round(stoch_d, 2),
                    'stoch_signal': stoch_signal
                }
        except Exception as e:
            logger.error(f"Error calculating Stochastic: {e}")
        return {}

    def calculate_obv(self) -> Dict[str, Any]:
        """Calculate On-Balance Volume (OBV).
        
        OBV tracks volume flow to confirm price trends:
        - Rising OBV + rising price = strong uptrend
        - Falling OBV + rising price = weak uptrend (divergence)
        
        Returns:
            Dictionary with OBV trend and divergence detection
        """
        try:
            obv = ta.obv(self.df['close'], self.df['volume'])
            
            if obv is not None and len(obv) >= 20:
                current_obv = float(obv.iloc[-1])
                obv_20_ago = float(obv.iloc[-20])
                
                # OBV trend
                obv_change_pct = ((current_obv - obv_20_ago) / abs(obv_20_ago)) * 100 if obv_20_ago != 0 else 0
                
                if obv_change_pct > 10:
                    obv_trend = "STRONG_INFLOW"
                elif obv_change_pct > 0:
                    obv_trend = "INFLOW"
                elif obv_change_pct < -10:
                    obv_trend = "STRONG_OUTFLOW"
                else:
                    obv_trend = "OUTFLOW"
                
                # Check for divergence (OBV vs price moving opposite directions)
                price_now = float(self.df['close'].iloc[-1])
                price_20_ago = float(self.df['close'].iloc[-20])
                price_change_pct = ((price_now - price_20_ago) / price_20_ago) * 100
                
                divergence = "NONE"
                if obv_change_pct > 5 and price_change_pct < -5:
                    divergence = "BULLISH_DIVERGENCE"  # Volume accumulating while price falls
                elif obv_change_pct < -5 and price_change_pct > 5:
                    divergence = "BEARISH_DIVERGENCE"  # Volume leaving while price rises
                
                return {
                    'obv': int(current_obv),
                    'obv_change_pct': round(obv_change_pct, 2),
                    'obv_trend': obv_trend,
                    'obv_divergence': divergence
                }
        except Exception as e:
            logger.error(f"Error calculating OBV: {e}")
        return {}

    def calculate_fibonacci(self, period: int = 20) -> Dict[str, Any]:
        """Calculate Fibonacci Retracement Levels.
        
        Key levels: 23.6%, 38.2%, 50%, 61.8%, 78.6%
        Used to identify support/resistance and price targets.
        
        Returns:
            Dictionary with Fibonacci levels and current position
        """
        try:
            if len(self.df) < period:
                return {}
            
            # Get high/low of recent period
            recent_data = self.df.tail(period)
            high = float(recent_data['high'].max())
            low = float(recent_data['low'].min())
            diff = high - low
            
            if diff == 0:
                return {}
            
            current_price = float(self.df['close'].iloc[-1])
            
            # Calculate Fibonacci levels (from low to high)
            fib_levels = {
                'fib_0': round(low, 2),           # 0%
                'fib_236': round(low + diff * 0.236, 2),  # 23.6%
                'fib_382': round(low + diff * 0.382, 2),  # 38.2%
                'fib_500': round(low + diff * 0.5, 2),    # 50%
                'fib_618': round(low + diff * 0.618, 2),  # 61.8% (golden ratio)
                'fib_786': round(low + diff * 0.786, 2),  # 78.6%
                'fib_100': round(high, 2)         # 100%
            }
            
            # Determine which level price is near
            current_pct = (current_price - low) / diff
            
            if current_pct >= 0.95:
                fib_position = "AT_RESISTANCE"
            elif current_pct >= 0.786:
                fib_position = "NEAR_786"
            elif current_pct >= 0.618:
                fib_position = "NEAR_618"
            elif current_pct >= 0.5:
                fib_position = "NEAR_500"
            elif current_pct >= 0.382:
                fib_position = "NEAR_382"
            elif current_pct >= 0.236:
                fib_position = "NEAR_236"
            elif current_pct <= 0.05:
                fib_position = "AT_SUPPORT"
            else:
                fib_position = "BELOW_236"
            
            fib_levels['fib_position'] = fib_position
            fib_levels['fib_current_pct'] = round(current_pct * 100, 1)
            
            return fib_levels
        except Exception as e:
            logger.error(f"Error calculating Fibonacci: {e}")
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
