"""Trade and position models for storing trade history and position snapshots.

Migrated from SQLAlchemy to Django ORM.
"""

from django.db import models
from django.conf import settings


class Trade(models.Model):
    """Trade model for recording executed trades."""

    ORDER_TYPE_CHOICES = [
        ('market', 'Market'),
        ('limit', 'Limit'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('filled', 'Filled'),
        ('executed', 'Executed'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
        ('inactive', 'Inactive'),
    ]

    ACTION_CHOICES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trades'
    )

    # Trade details
    symbol = models.CharField(max_length=20, db_index=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=15, decimal_places=4)
    total_value = models.DecimalField(max_digits=15, decimal_places=2)

    # Order details
    order_id = models.CharField(max_length=100, blank=True, null=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='market')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='executed')

    # Fill details (synced from IBKR)
    filled_qty = models.IntegerField(null=True, blank=True)
    filled_avg_price = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    limit_price = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)

    # Risk management
    stop_loss = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)

    # LLM analysis
    confidence = models.FloatField(null=True, blank=True)
    reasoning = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'trades'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['symbol', 'created_at']),
            models.Index(fields=['order_id']),
        ]

    def __str__(self):
        return f"{self.action} {self.quantity} {self.symbol} @ ${self.price}"


class PortfolioSnapshot(models.Model):
    """Portfolio snapshot for tracking portfolio value over time."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portfolio_snapshots'
    )

    # Portfolio values
    portfolio_value = models.DecimalField(max_digits=15, decimal_places=2)
    cash = models.DecimalField(max_digits=15, decimal_places=2)
    equity = models.DecimalField(max_digits=15, decimal_places=2)

    # Performance
    daily_change = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    daily_change_pct = models.FloatField(null=True, blank=True)

    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'portfolio_snapshots'
        ordering = ['-timestamp']

    def __str__(self):
        return f"${self.portfolio_value} @ {self.timestamp}"


class PositionSnapshot(models.Model):
    """Snapshot of a single position at a point in time.

    Created whenever positions are fetched from IBKR,
    providing historical position data that survives gateway restarts.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='position_snapshots'
    )

    # Position details
    symbol = models.CharField(max_length=20, db_index=True)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    avg_entry_price = models.DecimalField(max_digits=15, decimal_places=4)
    current_price = models.DecimalField(max_digits=15, decimal_places=4)
    market_value = models.DecimalField(max_digits=15, decimal_places=2)
    unrealized_pl = models.DecimalField(max_digits=15, decimal_places=2)
    unrealized_plpc = models.FloatField()

    # Link to the portfolio snapshot this belongs to
    portfolio_snapshot = models.ForeignKey(
        PortfolioSnapshot,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='positions'
    )

    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'position_snapshots'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['symbol', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.symbol}: {self.qty} shares @ {self.timestamp}"


class AgentRunLog(models.Model):
    """Operational audit log for scheduled runs and recommendation events."""

    RUN_TYPE_CHOICES = [
        ('analyze', 'Analyze'),
        ('option_chain', 'Option Chain'),
        ('daily_summary', 'Daily Summary'),
    ]

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('no_trades', 'No Trades'),
        ('no_response', 'No Response'),
        ('skipped', 'Skipped'),
        ('fallback', 'Fallback'),
        ('error', 'Error'),
    ]

    run_type = models.CharField(max_length=32, choices=RUN_TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, db_index=True)
    message = models.TextField(blank=True)

    # Execution diagnostics
    duration_ms = models.IntegerField(null=True, blank=True)
    market_open = models.BooleanField(null=True, blank=True)
    llm_ok = models.BooleanField(null=True, blank=True, db_index=True)
    llm_error = models.TextField(blank=True)

    # Trading diagnostics
    trades_recommended = models.IntegerField(null=True, blank=True)
    trades_executed = models.IntegerField(null=True, blank=True)

    # Option recommendation diagnostics
    symbol = models.CharField(max_length=20, null=True, blank=True)
    option_type = models.CharField(max_length=10, null=True, blank=True)
    strike = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    recommendation_source = models.CharField(max_length=32, null=True, blank=True)
    recommendation_candidates = models.IntegerField(null=True, blank=True)

    # Extra context (small JSON payload)
    details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'agent_run_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['run_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.run_type}:{self.status} @ {self.created_at}"
