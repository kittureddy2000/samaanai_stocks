"""Persistent application settings for agent behavior and indicator toggles."""

from django.db import models


def default_indicator_settings():
    """Default enabled indicator set used by LLM analysis."""
    return {
        'rsi': True,
        'macd': True,
        'moving_averages': True,
        'bollinger_bands': True,
        'volume': True,
        'price_action': True,
        'vwap': True,
        'atr': True,
    }


class AgentSettings(models.Model):
    """Singleton settings row used to control agent behavior at runtime."""

    singleton_key = models.CharField(max_length=32, unique=True, default='default')

    analysis_interval_minutes = models.IntegerField(default=15)
    max_position_pct = models.FloatField(default=0.10)
    max_daily_loss_pct = models.FloatField(default=0.03)
    min_confidence = models.FloatField(default=0.70)
    stop_loss_pct = models.FloatField(default=0.05)
    take_profit_pct = models.FloatField(default=0.10)

    indicator_settings = models.JSONField(default=default_indicator_settings, blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'agent_settings'

    def __str__(self):
        return f"AgentSettings<{self.singleton_key}>"
