"""Trading API app configuration."""

from django.apps import AppConfig


class TradingApiConfig(AppConfig):
    """Trading API application configuration."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trading_api'
    verbose_name = 'LLM Trading Agent API'

    def ready(self):
        """Initialize app when Django starts."""
        # Import signals if any
        pass
