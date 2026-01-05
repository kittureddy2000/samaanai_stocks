"""Slack notification module for trade alerts."""

import os
import requests
from typing import Dict, Any, Optional
from loguru import logger


class SlackNotifier:
    """Send trade alerts and notifications to Slack."""
    
    def __init__(self):
        """Initialize Slack notifier with webhook URL."""
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)
        
        if not self.enabled:
            logger.warning("SLACK_WEBHOOK_URL not set. Slack notifications disabled.")
    
    def send_message(self, text: str, blocks: list = None) -> bool:
        """Send a message to Slack.
        
        Args:
            text: Fallback text for notifications
            blocks: Optional rich message blocks
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            payload = {"text": text}
            if blocks:
                payload["blocks"] = blocks
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
                return True
            else:
                logger.error(f"Slack notification failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False
    
    def notify_trade_executed(self, trade: Dict[str, Any]) -> bool:
        """Send notification for an executed trade.
        
        Args:
            trade: Trade details dictionary
            
        Returns:
            True if sent successfully
        """
        action = trade.get('action', 'UNKNOWN')
        symbol = trade.get('symbol', 'UNKNOWN')
        quantity = trade.get('quantity', 0)
        confidence = trade.get('confidence', 0) * 100
        reasoning = trade.get('reasoning', 'No reason provided')
        
        emoji = "📈" if action == "BUY" else "📉" if action == "SELL" else "⏸️"
        color = "#36a64f" if action == "BUY" else "#dc3545" if action == "SELL" else "#6c757d"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Trade Executed: {action} {quantity} {symbol}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Action:*\n{action}"},
                    {"type": "mrkdwn", "text": f"*Symbol:*\n{symbol}"},
                    {"type": "mrkdwn", "text": f"*Quantity:*\n{quantity}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence:.0f}%"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reasoning:*\n{reasoning[:200]}..."
                }
            },
            {"type": "divider"}
        ]
        
        return self.send_message(
            text=f"{emoji} {action} {quantity} {symbol} ({confidence:.0f}% confidence)",
            blocks=blocks
        )
    
    def notify_portfolio_summary(self, portfolio: Dict[str, Any]) -> bool:
        """Send daily portfolio summary.
        
        Args:
            portfolio: Portfolio details dictionary
            
        Returns:
            True if sent successfully
        """
        value = portfolio.get('portfolio_value', 0)
        daily_change = portfolio.get('daily_change', 0)
        daily_pct = portfolio.get('daily_change_pct', 0)
        positions = portfolio.get('positions_count', 0)
        
        change_emoji = "🟢" if daily_change >= 0 else "🔴"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Daily Portfolio Summary",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Portfolio Value:*\n${value:,.2f}"},
                    {"type": "mrkdwn", "text": f"*Daily Change:*\n{change_emoji} ${daily_change:+,.2f} ({daily_pct:+.2f}%)"},
                    {"type": "mrkdwn", "text": f"*Positions:*\n{positions}"},
                ]
            },
            {"type": "divider"}
        ]
        
        return self.send_message(
            text=f"📊 Portfolio: ${value:,.2f} ({change_emoji} {daily_pct:+.2f}%)",
            blocks=blocks
        )
    
    def notify_agent_started(self) -> bool:
        """Send notification that trading agent has started."""
        return self.send_message(
            text="🤖 Trading Agent Started",
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🤖 *Trading Agent Started*\nAnalyzing market during trading hours..."
                }
            }]
        )
    
    def notify_agent_stopped(self, reason: str = "Normal shutdown") -> bool:
        """Send notification that trading agent has stopped."""
        return self.send_message(
            text=f"⏹️ Trading Agent Stopped: {reason}",
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⏹️ *Trading Agent Stopped*\nReason: {reason}"
                }
            }]
        )
    
    def notify_error(self, error: str) -> bool:
        """Send error notification."""
        return self.send_message(
            text=f"❌ Trading Error: {error}",
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ *Trading Error*\n```{error}```"
                }
            }]
        )


# Global notifier instance
slack = SlackNotifier()


def notify_trade(trade: Dict[str, Any]) -> bool:
    """Convenience function to notify about a trade."""
    return slack.notify_trade_executed(trade)


def notify_portfolio(portfolio: Dict[str, Any]) -> bool:
    """Convenience function to notify about portfolio."""
    return slack.notify_portfolio_summary(portfolio)
