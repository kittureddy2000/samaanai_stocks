"""Sentiment analysis module for alternative data integration.

Integrates:
- Financial news sentiment (via NewsAPI or scraping)
- Reddit sentiment (WSB, stocks subreddits)  
- Fear & Greed Index
- Social media buzz metrics
"""

import os
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from loguru import logger
import re

# Try to import BeautifulSoup for web scraping
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logger.warning("BeautifulSoup not installed. Some features disabled. Run: pip install beautifulsoup4")


class SentimentAnalyzer:
    """Analyze market sentiment from various sources."""
    
    def __init__(self):
        """Initialize sentiment analyzer with API keys."""
        self.news_api_key = os.getenv("NEWS_API_KEY", "")
        
    def get_all_sentiment(self, symbol: str = None) -> Dict[str, Any]:
        """Get sentiment from all available sources.
        
        Args:
            symbol: Optional stock symbol for targeted sentiment
            
        Returns:
            Dictionary with all sentiment data
        """
        result = {
            'timestamp': datetime.now().isoformat(),
            'overall_sentiment': 'NEUTRAL',
            'sentiment_score': 0
        }
        
        # Fear & Greed Index (always available)
        fg_data = self.get_fear_greed_index()
        if fg_data:
            result['fear_greed'] = fg_data
        
        # News sentiment if API key available
        if self.news_api_key and symbol:
            news_data = self.get_news_sentiment(symbol)
            if news_data:
                result['news'] = news_data
        
        # Calculate overall sentiment
        scores = []
        if 'fear_greed' in result:
            # Fear & Greed: 0-100, normalize to -1 to 1
            fg_score = (result['fear_greed'].get('value', 50) - 50) / 50
            scores.append(fg_score)
        
        if 'news' in result:
            news_score = result['news'].get('sentiment_score', 0)
            scores.append(news_score)
        
        if scores:
            avg_score = sum(scores) / len(scores)
            result['sentiment_score'] = round(avg_score, 2)
            
            if avg_score > 0.3:
                result['overall_sentiment'] = 'VERY_BULLISH'
            elif avg_score > 0.1:
                result['overall_sentiment'] = 'BULLISH'
            elif avg_score < -0.3:
                result['overall_sentiment'] = 'VERY_BEARISH'
            elif avg_score < -0.1:
                result['overall_sentiment'] = 'BEARISH'
            else:
                result['overall_sentiment'] = 'NEUTRAL'
        
        return result

    def get_fear_greed_index(self) -> Dict[str, Any]:
        """Get CNN Fear & Greed Index.
        
        The Fear & Greed Index measures market sentiment on a 0-100 scale:
        - 0-25: Extreme Fear (buy opportunity)
        - 25-45: Fear
        - 45-55: Neutral
        - 55-75: Greed
        - 75-100: Extreme Greed (sell signal)
        
        Returns:
            Dictionary with Fear & Greed data
        """
        try:
            # Use Alternative.me API (public, no key needed)
            url = "https://api.alternative.me/fng/?limit=1"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and len(data['data']) > 0:
                    fng = data['data'][0]
                    value = int(fng.get('value', 50))
                    
                    # Classify the sentiment
                    if value <= 25:
                        classification = "EXTREME_FEAR"
                        signal = "STRONG_BUY"
                    elif value <= 45:
                        classification = "FEAR"
                        signal = "BUY"
                    elif value <= 55:
                        classification = "NEUTRAL"
                        signal = "HOLD"
                    elif value <= 75:
                        classification = "GREED"
                        signal = "CAUTION"
                    else:
                        classification = "EXTREME_GREED"
                        signal = "STRONG_SELL"
                    
                    return {
                        'value': value,
                        'classification': classification,
                        'signal': signal,
                        'timestamp': fng.get('timestamp', ''),
                        'description': f"Fear & Greed Index at {value} ({classification})"
                    }
        except Exception as e:
            logger.error(f"Error fetching Fear & Greed Index: {e}")
        
        return {}

    def get_news_sentiment(self, symbol: str, days: int = 3) -> Dict[str, Any]:
        """Get news sentiment for a stock symbol.
        
        Args:
            symbol: Stock ticker symbol
            days: Number of days to look back
            
        Returns:
            Dictionary with news sentiment analysis
        """
        if not self.news_api_key:
            logger.warning("NEWS_API_KEY not set. Skipping news sentiment.")
            return {}
        
        try:
            # NewsAPI query
            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': f"{symbol} stock",
                'from': from_date,
                'sortBy': 'relevancy',
                'language': 'en',
                'pageSize': 20,
                'apiKey': self.news_api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
                if not articles:
                    return {'article_count': 0, 'sentiment_score': 0}
                
                # Simple sentiment analysis based on keywords
                positive_words = ['surge', 'jump', 'gain', 'profit', 'bullish', 'up', 'high', 
                                'growth', 'beat', 'exceed', 'record', 'buy', 'upgrade']
                negative_words = ['drop', 'fall', 'loss', 'bearish', 'down', 'low', 'miss',
                                'fail', 'sell', 'downgrade', 'concern', 'risk', 'decline']
                
                positive_count = 0
                negative_count = 0
                headlines = []
                
                for article in articles[:10]:  # Analyze top 10
                    title = (article.get('title', '') or '').lower()
                    description = (article.get('description', '') or '').lower()
                    text = f"{title} {description}"
                    
                    for word in positive_words:
                        if word in text:
                            positive_count += 1
                    
                    for word in negative_words:
                        if word in text:
                            negative_count += 1
                    
                    headlines.append(article.get('title', '')[:100])
                
                # Calculate sentiment score (-1 to 1)
                total = positive_count + negative_count
                if total > 0:
                    sentiment_score = (positive_count - negative_count) / total
                else:
                    sentiment_score = 0
                
                # Classify
                if sentiment_score > 0.3:
                    news_sentiment = "VERY_POSITIVE"
                elif sentiment_score > 0:
                    news_sentiment = "POSITIVE"
                elif sentiment_score < -0.3:
                    news_sentiment = "VERY_NEGATIVE"
                elif sentiment_score < 0:
                    news_sentiment = "NEGATIVE"
                else:
                    news_sentiment = "NEUTRAL"
                
                return {
                    'article_count': len(articles),
                    'analyzed_count': min(10, len(articles)),
                    'positive_signals': positive_count,
                    'negative_signals': negative_count,
                    'sentiment_score': round(sentiment_score, 2),
                    'sentiment': news_sentiment,
                    'recent_headlines': headlines[:3]
                }
            else:
                logger.error(f"NewsAPI error: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching news sentiment: {e}")
        
        return {}

    def get_reddit_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get Reddit sentiment from r/wallstreetbets and r/stocks.
        
        Note: Requires PRAW library and Reddit API credentials.
        For now, returns a placeholder - can be expanded with proper Reddit API.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Dictionary with Reddit sentiment data
        """
        # Reddit API requires OAuth setup - placeholder implementation
        # To enable: pip install praw, create Reddit app, add credentials
        
        logger.info(f"Reddit sentiment not configured for {symbol}")
        return {
            'status': 'disabled',
            'message': 'Reddit API not configured. Add REDDIT_CLIENT_ID, REDDIT_SECRET to enable.'
        }

    def get_market_buzz(self, symbols: List[str]) -> Dict[str, Any]:
        """Get overall market buzz/chatter metrics.
        
        Args:
            symbols: List of stock symbols to analyze
            
        Returns:
            Dictionary with market buzz metrics
        """
        results = {}
        
        for symbol in symbols[:5]:  # Limit to 5 to avoid rate limits
            sentiment = self.get_all_sentiment(symbol)
            results[symbol] = {
                'sentiment': sentiment.get('overall_sentiment', 'NEUTRAL'),
                'score': sentiment.get('sentiment_score', 0)
            }
        
        # Calculate market-wide sentiment
        if results:
            avg_score = sum(r['score'] for r in results.values()) / len(results)
            return {
                'symbols_analyzed': list(results.keys()),
                'individual_sentiment': results,
                'market_sentiment_score': round(avg_score, 2),
                'market_mood': 'BULLISH' if avg_score > 0.1 else ('BEARISH' if avg_score < -0.1 else 'NEUTRAL')
            }
        
        return {}


# Convenience function
def get_sentiment(symbol: str = None) -> Dict[str, Any]:
    """Get market sentiment for a symbol.
    
    Args:
        symbol: Optional stock symbol
        
    Returns:
        Dictionary with sentiment data
    """
    analyzer = SentimentAnalyzer()
    return analyzer.get_all_sentiment(symbol)


def get_fear_greed() -> Dict[str, Any]:
    """Get Fear & Greed Index.
    
    Returns:
        Dictionary with Fear & Greed data
    """
    analyzer = SentimentAnalyzer()
    return analyzer.get_fear_greed_index()
