"""LLM client for making API calls to Google Gemini."""

import json
from typing import Optional, Dict, Any
from google import genai
from google.genai import types
from pydantic import BaseModel
from loguru import logger

import sys
sys.path.append(str(__file__).rsplit("/", 3)[0])
from config import config


class TradeDecision(BaseModel):
    """A single trade decision from the LLM."""
    action: str  # BUY, SELL, HOLD
    symbol: str
    quantity: int
    order_type: str  # market, limit
    limit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    confidence: float
    reasoning: str


class LLMResponse(BaseModel):
    """Structured response from the LLM."""
    analysis_summary: str
    trades: list[TradeDecision]
    portfolio_recommendation: str
    risk_assessment: str


class LLMClient:
    """Client for interacting with Google Gemini API."""
    
    def __init__(self):
        """Initialize the Gemini client."""
        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model = config.gemini.model
        self.temperature = config.gemini.temperature
        self.last_error: Optional[str] = None
    
    def analyze_market(
        self, 
        system_prompt: str, 
        user_prompt: str,
        max_retries: int = 3
    ) -> Optional[LLMResponse]:
        """Send analysis request to the LLM with retry logic.
        
        Args:
            system_prompt: System role prompt
            user_prompt: User message with market data
            max_retries: Maximum number of retry attempts for transient errors
            
        Returns:
            Parsed LLMResponse or None if failed
        """
        import time
        
        # Combine system and user prompts
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        last_error = None
        for attempt in range(max_retries):
            try:
                self.last_error = None
                if attempt > 0:
                    # Exponential backoff: 5s, 15s, 45s
                    wait_time = 5 * (3 ** attempt)
                    logger.info(f"Retry attempt {attempt + 1}/{max_retries} after {wait_time}s delay...")
                    time.sleep(wait_time)
                
                logger.info(f"Sending request to Gemini ({self.model})...")
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.temperature,
                        response_mime_type="application/json"
                    )
                )
                
                # Extract the response content
                content = response.text
                logger.debug(f"Raw LLM response: {content}")
                
                # Parse JSON
                data = json.loads(content)
                
                # Validate and convert to our response model
                parsed = self._parse_response(data)
                
                if parsed:
                    logger.info(f"LLM analysis complete: {len(parsed.trades)} trade(s) recommended")
                    for trade in parsed.trades:
                        logger.info(f"  → {trade.action} {trade.quantity} {trade.symbol} (confidence: {trade.confidence:.0%})")

                return parsed
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                return None  # Don't retry JSON errors - they won't fix themselves
                
            except Exception as e:
                last_error = e
                self.last_error = str(e)
                error_str = str(e)
                
                # Check if it's a retryable error (503, 429, rate limit)
                is_retryable = any(code in error_str for code in ['503', '429', 'UNAVAILABLE', 'overloaded', 'quota', 'RESOURCE_EXHAUSTED'])
                
                if is_retryable and attempt < max_retries - 1:
                    logger.warning(f"Retryable error on attempt {attempt + 1}: {e}")
                    continue
                else:
                    logger.error(f"Error calling LLM API (attempt {attempt + 1}): {e}")
                    if not is_retryable:
                        return None  # Don't retry non-retryable errors
        
        logger.error(f"All {max_retries} retry attempts failed. Last error: {last_error}")
        self.last_error = str(last_error) if last_error else "Unknown LLM error"
        return None
    
    def _parse_response(self, data: Dict[str, Any]) -> Optional[LLMResponse]:
        """Parse the raw JSON response into our model.
        
        Args:
            data: Raw JSON dictionary
            
        Returns:
            LLMResponse or None if parsing fails
        """
        try:
            trades = []
            for trade_data in data.get('trades', []):
                trade = TradeDecision(
                    action=trade_data.get('action', 'HOLD').upper(),
                    symbol=trade_data.get('symbol', '').upper(),
                    quantity=int(trade_data.get('quantity', 0)),
                    order_type=trade_data.get('order_type', 'market').lower(),
                    limit_price=trade_data.get('limit_price'),
                    stop_loss_price=trade_data.get('stop_loss_price'),
                    take_profit_price=trade_data.get('take_profit_price'),
                    confidence=float(trade_data.get('confidence', 0)),
                    reasoning=trade_data.get('reasoning', '')
                )
                trades.append(trade)
            
            return LLMResponse(
                analysis_summary=data.get('analysis_summary', ''),
                trades=trades,
                portfolio_recommendation=data.get('portfolio_recommendation', ''),
                risk_assessment=data.get('risk_assessment', 'UNKNOWN')
            )
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test the API connection.
        
        Returns:
            True if connection successful
        """
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents="Say 'connected' in one word."
            )
            content = response.text.strip()
            logger.info(f"Gemini connection test: {content}")
            return True
            
        except Exception as e:
            logger.error(f"Gemini connection failed: {e}")
            return False

    def recommend_option_to_sell(
        self,
        symbol: str,
        current_price: float,
        candidates: list[Dict[str, Any]],
        max_retries: int = 2
    ) -> Optional[Dict[str, Any]]:
        """Recommend the best option contract to sell (call or put).

        Args:
            symbol: Underlying stock symbol
            current_price: Current underlying price
            candidates: Option candidates with liquidity/greeks/premium fields
            max_retries: Retry count for transient API errors

        Returns:
            Recommendation dict or None if analysis fails
        """
        import time

        if not candidates:
            return None

        # Keep prompt compact and deterministic
        ranked = sorted(
            candidates,
            key=lambda c: (
                float(c.get('open_interest', 0) or 0),
                float(c.get('volume', 0) or 0),
                float(c.get('premium', 0) or 0),
            ),
            reverse=True
        )[:30]

        prompt = (
            "You are an options income analyst. Pick ONE best option to SELL now.\n"
            "Goal: premium capture with reasonable assignment/risk balance.\n"
            "Allowed choice: CALL or PUT.\n"
            "Assume SELL CALL is covered-call style and SELL PUT is cash-secured.\n"
            "Prefer liquid contracts and avoid extreme risk.\n\n"
            f"Underlying: {symbol}\n"
            f"Current Price: {current_price}\n"
            f"Candidates JSON: {json.dumps(ranked)}\n\n"
            "Return strict JSON only with this schema:\n"
            "{\n"
            '  "option_type": "CALL" | "PUT",\n'
            '  "expiration": "YYYY-MM-DD",\n'
            '  "strike": <number>,\n'
            '  "premium": <number>,\n'
            '  "confidence": <0.0-1.0>,\n'
            '  "reasoning": "<short rationale>"\n'
            "}"
        )

        last_error = None
        for attempt in range(max_retries):
            try:
                self.last_error = None
                if attempt > 0:
                    wait_time = 4 * (2 ** attempt)
                    logger.info(
                        f"Retrying option recommendation ({attempt + 1}/{max_retries}) "
                        f"after {wait_time}s"
                    )
                    time.sleep(wait_time)

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json"
                    )
                )

                parsed = json.loads(response.text)
                option_type = str(parsed.get('option_type', '')).upper().strip()
                if option_type not in ('CALL', 'PUT'):
                    option_type = 'CALL'

                recommendation = {
                    'option_type': option_type,
                    'expiration': str(parsed.get('expiration', '')).strip(),
                    'strike': float(parsed.get('strike', 0) or 0),
                    'premium': float(parsed.get('premium', 0) or 0),
                    'confidence': float(parsed.get('confidence', 0) or 0),
                    'reasoning': str(parsed.get('reasoning', '')).strip(),
                }
                return recommendation
            except Exception as e:
                last_error = e
                self.last_error = str(e)
                logger.warning(f"Option recommendation failed on attempt {attempt + 1}: {e}")

        logger.error(f"Option recommendation failed after retries: {last_error}")
        self.last_error = str(last_error) if last_error else "Unknown option recommendation error"
        return None
